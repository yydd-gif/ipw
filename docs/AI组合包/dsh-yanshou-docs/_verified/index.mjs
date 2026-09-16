import Schema from "@deepseek-ai/schemastery";
import { defineTool } from "@deepseek-ai/dsh-tools";
import { spawn } from "node:child_process";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import { existsSync } from "node:fs";
//#region src/config.ts
const Config = Schema.object({
	pythonBin: Schema.string().default("python"),
	engineRoot: Schema.string().default(""),
	workspaceRoot: Schema.string().default("."),
	protectedPaths: Schema.array(Schema.string()).default(["模版", "模版_原始备份"]),
	allowWriteToTemplates: Schema.boolean().default(false),
	reportDir: Schema.string().default("_导出")
});
//#endregion
//#region src/bridge.ts
/** 解析引擎脚本目录 */
function resolveEngineRoot(config) {
	if (config.engineRoot) return config.engineRoot;
	return join(config.workspaceRoot, ".workbuddy", "engine");
}
/** 执行一个引擎脚本 */
function runEngine(config, script, args = [], opts = {}) {
	const scriptPath = join(resolveEngineRoot(config), script);
	const cwd = opts.cwd ?? config.workspaceRoot;
	const timeoutMs = opts.timeoutMs ?? 6e5;
	return new Promise((resolve) => {
		if (!existsSync(scriptPath)) {
			resolve({
				ok: false,
				code: -2,
				stdout: "",
				stderr: `引擎脚本不存在：${scriptPath}`,
				summary: `引擎脚本不存在：${scriptPath}`
			});
			return;
		}
		const child = spawn(config.pythonBin, [scriptPath, ...args], {
			cwd,
			windowsHide: true,
			shell: false
		});
		let stdout = "";
		let stderr = "";
		let settled = false;
		const timer = setTimeout(() => {
			if (settled) return;
			settled = true;
			child.kill();
			resolve({
				ok: false,
				code: -3,
				stdout,
				stderr,
				summary: `引擎执行超时（${Math.round(timeoutMs / 1e3)}s）`
			});
		}, timeoutMs);
		child.stdout.on("data", (d) => {
			stdout += d.toString("utf8");
		});
		child.stderr.on("data", (d) => {
			stderr += d.toString("utf8");
		});
		child.on("error", (err) => {
			if (settled) return;
			settled = true;
			clearTimeout(timer);
			resolve({
				ok: false,
				code: -1,
				stdout,
				stderr: `${stderr}\n${String(err)}`,
				summary: `无法启动 Python：${String(err)}`
			});
		});
		child.on("close", (code) => {
			if (settled) return;
			settled = true;
			clearTimeout(timer);
			const rc = code ?? -1;
			const tail = stdout.trim().split(/\r?\n/).slice(-8).join("\n");
			resolve({
				ok: rc === 0,
				code: rc,
				stdout,
				stderr,
				summary: tail || (rc === 0 ? "完成（无输出）" : `退出码 ${rc}`)
			});
		});
	});
}
//#endregion
//#region src/policy.ts
/**
* 模板保护策略。
*
* 为什么要有这个文件：
* 本项目有一条铁律 —— **AI 绝不写 `模版/` 下的 docx**。这条规矩曾经被破过一次
* （AI 越界把占位符注进了模板）。口头规矩靠不住，所以这里把它落成代码：
* 任何写入路径先过 assertWritable()，命中受保护目录直接抛错。
*
* 两个层次，双保险：
*   1. 本文件 —— 所有写盘工具在动手前调用 assertWritable()，不依赖任何框架事件契约，
*      这是确定性的一层。
*   2. `tools/pre-execute` 全局钩子（见文件末尾注释）—— 覆盖到别的插件注册的工具。
*      dsh 架构文档记载它是 waterfall 事件（监听器须调用 next() 才能委托下去），
*      但确切回调签名需在真机安装后用 `dsh --profile yanshou --dump-config` 配合
*      探针确认后再启用，避免凭猜测写出跑不通的钩子。
*/
/** 把任意路径规整成可比较的绝对形式 */
function normalize(p, base) {
	const abs = isAbsolute(p) ? resolve(p) : resolve(base, p);
	return process.platform === "win32" ? abs.toLowerCase() : abs;
}
/** 判断 target 是否落在受保护目录内（含目录本身） */
function isProtected(target, config) {
	if (config.allowWriteToTemplates) return false;
	const safe = normalize(target, config.workspaceRoot);
	return config.protectedPaths.some((raw) => {
		const guard = normalize(raw, config.workspaceRoot);
		if (safe === guard) return true;
		return safe.startsWith(guard.endsWith(sep) ? guard : guard + sep);
	});
}
/** 命中受保护目录时的说明文本 */
function explain(target, config) {
	return [
		"已拦截一次对模板目录的写入。",
		`目标：${relative(config.workspaceRoot, isAbsolute(target) ? target : resolve(config.workspaceRoot, target)) || target}`,
		`受保护：${config.protectedPaths.join("、")}`,
		"",
		"模板侧由工头手动维护，程序只读不写。",
		"若确实需要临时放开，在 profile 的 cordis.patch.yml 里把 allowWriteToTemplates 置为 true —— 改完记得改回来。"
	].join("\n");
}
/** 写盘前的强制闸门。受保护则抛错。 */
function assertWritable(target, config) {
	if (isProtected(target, config)) {
		const err = new Error(explain(target, config));
		err.name = "TemplateProtectionError";
		throw err;
	}
}
//#endregion
//#region src/tools.ts
/**
* 五块确定性引擎的工具化。
*
* 全部走 defineTool + ctx.tools.register 的官方注册方式，
* 每块引擎对应一个面向模型的工具，模型可以在轮次里直接调用。
*
* 注意分工：**确定性批处理本身不交给模型推理**。模型负责「决定调哪个工具、
* 传什么参数、怎么解读结果」；真正套模板填字段的活，是 Python 引擎在
* 一次子进程里跑完的，输入固定、输出唯一、100% 可复现。
*/
const textOutput = {
	schema: { type: "string" },
	render: (_args, value) => [{
		type: "text",
		text: value
	}]
};
function fmt(title, r) {
	const parts = [
		r.ok ? `【${title}】完成` : `【${title}】未通过（退出码 ${r.code}）`,
		"",
		r.summary
	];
	if (!r.ok && r.stderr.trim()) parts.push("", "── stderr ──", r.stderr.trim().slice(-1500));
	return parts.join("\n");
}
function registerTools(ctx, config) {
	ctx.tools.register(defineTool({
		name: "yanshou_fill",
		description: "按字段字典与 project.json 批量填充验收资料模板，逐份输出到工程目录。确定性批处理，不调用模型推理。缺值的占位符会原样保留 {{key}} 并记入报告，绝不填空。",
		parameters: {
			outDir: {
				type: "string",
				required: false,
				description: "输出目录（相对 workspaceRoot 或绝对路径）。默认为 _导出/工程"
			},
			projectFile: {
				type: "string",
				required: false,
				description: "project.json 路径，含项目级字段值与 _documents 文档级覆盖"
			}
		},
		output: textOutput,
		async execute(args) {
			const outDir = args?.outDir ?? config.reportDir;
			assertWritable(outDir, config);
			const argv = ["--out", outDir];
			if (args?.projectFile) argv.push("--project", args.projectFile);
			return fmt("一键成册 · 填充引擎", await runEngine(config, "fill_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_verify",
		description: "扫描指定目录，报告残留的 {{占位符}}、未在字典中定义的 key、以及日期字段是否被误填。用于导出前的最后一道查错。",
		parameters: { targetDir: {
			type: "string",
			required: false,
			description: "待校验目录，默认 _导出/工程"
		} },
		output: textOutput,
		async execute(args) {
			return fmt("导出前查错 · 残留校验", await runEngine(config, "verify_engine.py", ["--dir", args?.targetDir ?? `${config.reportDir}/工程`]));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_subtable",
		description: "识别文档中的清单型表格（软硬件配置清单、调试记录、试运行记录、评审评分表、文档移交清单等），按表头列名序列匹配后接管数据行：不足克隆、多余删除。模板侧不写 {{#rows:}} 标记。",
		parameters: {
			docPath: {
				type: "string",
				required: true,
				description: "目标文档路径"
			},
			tableKey: {
				type: "string",
				required: false,
				description: "子表 key（deviceList / softwareList / testItemList / trialRunList / expertScoreList / documentList / documentChecklist / volumeList）。留空则自动识别"
			},
			dataFile: {
				type: "string",
				required: false,
				description: "数据源 JSON/CSV 路径"
			}
		},
		output: textOutput,
		async execute(args) {
			assertWritable(args?.docPath ?? "", config);
			const argv = ["--doc", args?.docPath ?? ""];
			if (args?.tableKey) argv.push("--table", args.tableKey);
			if (args?.dataFile) argv.push("--data", args.dataFile);
			return fmt("清单表接管 · 子表识别引擎", await runEngine(config, "subtable_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_numbering",
		description: "为新增文档分配文档编号，格式 {合同编号}-{表名拼音缩写大写}-{流水号}，如 YY123-KGBSB-01。流水号在单个目录项内独立续排；无合同编号时用纯流水号。删除释放回本目录项编号池，恢复取回原号。",
		parameters: {
			catalogItem: {
				type: "string",
				required: true,
				description: "目录项名，如「开工报审表」"
			},
			count: {
				type: "number",
				required: false,
				description: "申请分配的编号个数，默认 1"
			},
			action: {
				type: "string",
				required: false,
				description: "allocate（默认）/ release（释放某个编号）/ restore（恢复）"
			},
			docNo: {
				type: "string",
				required: false,
				description: "release / restore 时的目标编号"
			}
		},
		output: textOutput,
		async execute(args) {
			const argv = [
				"--item",
				args?.catalogItem ?? "",
				"--action",
				args?.action ?? "allocate"
			];
			if (args?.count) argv.push("--count", String(args.count));
			if (args?.docNo) argv.push("--no", args.docNo);
			return fmt("文档编号 · 编号引擎", await runEngine(config, "numbering_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_aggregate",
		description: "把施工日志按周/月聚合生成项目周报与项目月报。这是典型的 AI 场景：模型负责把零散日志归纳成通顺的周报正文，引擎负责取数与写入文档。",
		parameters: {
			period: {
				type: "string",
				required: true,
				description: "周报填 week，月报填 month"
			},
			from: {
				type: "string",
				required: false,
				description: "起始日期 YYYY-MM-DD"
			},
			to: {
				type: "string",
				required: false,
				description: "截止日期 YYYY-MM-DD"
			},
			outDoc: {
				type: "string",
				required: false,
				description: "输出文档路径"
			}
		},
		output: textOutput,
		async execute(args) {
			if (args?.outDoc) assertWritable(args.outDoc, config);
			const argv = ["--period", args?.period ?? "week"];
			if (args?.from) argv.push("--from", args.from);
			if (args?.to) argv.push("--to", args.to);
			if (args?.outDoc) argv.push("--out", args.outDoc);
			return fmt("日志汇总 · 自动汇总引擎", await runEngine(config, "aggregate_engine.py", argv));
		}
	}));
}
//#endregion
//#region src/index.ts
/** 插件名（Cordis 用它做日志与卸载定位） */
const name = "yanshou-docs";
/**
* 声明依赖：Cordis 会等这些服务就绪后才调用 apply。
* 我们只依赖工具注册表 —— 五块引擎全部以「面向模型的工具」形式暴露。
*/
const inject = ["tools"];
/**
* 验收资料引擎插件。
*
* 定位：这是 A+ 架构里的「接线层」。
*   - 它不实现任何文档处理逻辑（那些在 Python 引擎里，已验证）
*   - 它不做 UI（UI 是我们自建的桌面壳，dsh 这里是 headless 后端）
*   - 它的唯一职责是：把五块引擎注册成工具，让模型的轮次能调用它们
*
* 因为薄，所以可替换：将来若不用 dsh，这一层整片扔掉即可，
* 底下的 Python 引擎与工程文件夹数据模型一行都不用改。
*/
function apply(ctx, config) {
	registerTools(ctx, config);
	console.log(`[yanshou-docs] 已加载 | 引擎目录 ${resolveEngineRoot(config)} | 模板保护 ${config.allowWriteToTemplates ? "已放开" : config.protectedPaths.join("、")}`);
}
//#endregion
export { Config, apply, inject, name };
