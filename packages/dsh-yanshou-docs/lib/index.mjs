import { assertWritable, explain, findBlocked, isProtected, normalize } from "./policy.mjs";
import Schema from "@deepseek-ai/schemastery";
import { defineTool } from "@deepseek-ai/dsh-tools";
import { dirname, join } from "node:path";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
//#region src/config.ts
const Config = Schema.object({
	installRoot: Schema.string().required(),
	workspaceRoot: Schema.string().required(),
	pythonBin: Schema.string().default("python"),
	engineRoot: Schema.string().default(""),
	activeProject: Schema.string().default(""),
	protectedPaths: Schema.array(Schema.string()).default([
		"templates",
		"templates-backup",
		"templates_原始备份"
	]),
	allowWriteToTemplates: Schema.boolean().default(false),
	engineTimeoutMs: Schema.number().default(6e5)
});
//#endregion
//#region src/bridge.ts
function resolveEngineRoot(config) {
	if (config.engineRoot) return config.engineRoot;
	return join(config.installRoot, "engine");
}
function resolveTemplatesDir(config) {
	return join(config.installRoot, "templates");
}
function resolveProjectFile(config) {
	const raw = (config.activeProject || config.workspaceRoot || "").trim();
	if (!raw) return join(config.workspaceRoot || ".", "project.json");
	if (/project\.json$/i.test(raw)) return raw;
	return join(raw, "project.json");
}
function resolveProjectDir(config) {
	return dirname(resolveProjectFile(config));
}
/** 解析引擎 stdout：必须取最后一行 JSON（数据与规则规格 §6）。失败才退回尾部文本。 */
function parseContractStdout(stdout) {
	const lines = stdout.trim().split(/\r?\n/).filter((l) => l.trim().length > 0);
	if (!lines.length) return {
		contract: null,
		summary: "完成（无输出）"
	};
	const last = lines[lines.length - 1];
	try {
		const obj = JSON.parse(last);
		if (obj && typeof obj === "object" && !Array.isArray(obj)) {
			if ("ok" in obj || "engine" in obj || "summary" in obj || "stats" in obj) {
				const bits = [];
				if (obj.summary != null) bits.push(String(obj.summary));
				if (obj.stats != null) bits.push("stats " + JSON.stringify(obj.stats));
				if (Array.isArray(obj.errors) && obj.errors.length) bits.push("errors " + JSON.stringify(obj.errors));
				return {
					contract: obj,
					summary: bits.join("\n") || last
				};
			}
		}
	} catch {}
	return {
		contract: null,
		summary: lines.slice(-8).join("\n")
	};
}
/** 超时后杀掉整棵进程树：Windows 用 taskkill /T /F，POSIX 杀进程组。 */
function killProcessTree(pid) {
	if (pid == null || !Number.isFinite(pid) || pid <= 0) return;
	if (process.platform === "win32") {
		spawn("taskkill", [
			"/pid",
			String(pid),
			"/T",
			"/F"
		], {
			windowsHide: true,
			stdio: "ignore",
			shell: false
		}).on("error", () => {
			try {
				process.kill(pid);
			} catch {}
		});
		return;
	}
	try {
		process.kill(-pid, "SIGKILL");
	} catch {
		try {
			process.kill(pid, "SIGKILL");
		} catch {}
	}
}
function runEngine(config, script, args = [], opts = {}) {
	const scriptPath = join(resolveEngineRoot(config), script);
	const cwd = opts.cwd ?? config.workspaceRoot;
	const timeoutMs = opts.timeoutMs ?? config.engineTimeoutMs ?? 6e5;
	return new Promise((resolveResult) => {
		if (!existsSync(scriptPath)) {
			resolveResult({
				ok: false,
				code: -2,
				stdout: "",
				stderr: `引擎脚本不存在：${scriptPath}`,
				summary: `引擎脚本不存在：${scriptPath}`,
				contract: null
			});
			return;
		}
		const env = {
			...process.env,
			PYTHONIOENCODING: "utf-8",
			PYTHONUTF8: "1"
		};
		const child = spawn(config.pythonBin, [scriptPath, ...args], {
			cwd,
			windowsHide: true,
			shell: false,
			env,
			detached: process.platform !== "win32"
		});
		let stdout = "";
		let stderr = "";
		let settled = false;
		const finish = (result) => {
			if (settled) return;
			settled = true;
			clearTimeout(timer);
			resolveResult(result);
		};
		const timer = setTimeout(() => {
			killProcessTree(child.pid);
			const parsed = parseContractStdout(stdout);
			finish({
				ok: false,
				code: -3,
				stdout,
				stderr,
				summary: `引擎执行超时（${Math.round(timeoutMs / 1e3)}s）`,
				contract: parsed.contract
			});
		}, timeoutMs);
		child.stdout.on("data", (d) => {
			stdout += d.toString("utf8");
		});
		child.stderr.on("data", (d) => {
			stderr += d.toString("utf8");
		});
		child.on("error", (err) => {
			finish({
				ok: false,
				code: -1,
				stdout,
				stderr: `${stderr}\n${String(err)}`.trim(),
				summary: `无法启动 Python：${String(err)}`,
				contract: null
			});
		});
		child.on("close", (code) => {
			const rc = code ?? -1;
			const parsed = parseContractStdout(stdout);
			const fallback = parsed.summary || (rc === 0 ? "完成（无输出）" : `退出码 ${rc}`);
			finish({
				ok: rc === 0,
				code: rc,
				stdout,
				stderr,
				summary: fallback,
				contract: parsed.contract
			});
		});
	});
}
//#endregion
//#region src/tools.ts
/**
* 七块确定性引擎的工具化。
*
* 注册顺序（施工图 §4.8）：datafill → docgen → fill → numbering → verify → aggregate
* 再加 subtable（P5 已实现 8 张子表行克隆）。
*
* 分工：确定性批处理本身不交给模型推理。模型负责选工具、给参数、解读结果。
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
const TABLE_KEYS = [
	"deviceList",
	"softwareList",
	"testItemList",
	"trialRunList",
	"expertScoreList",
	"documentList",
	"documentChecklist",
	"volumeList"
];
function registerTools(ctx, config) {
	ctx.tools.register(defineTool({
		name: "yanshou_datafill",
		description: "按字段字典与填数规则，算出整册每个占位符该填什么值，产出 FillPlan 预览。只算不写盘，不会改动任何文档。用于在真正填充前让用户确认取值是否正确。确定性计算，不调用模型推理。缺值字段会标记为 missing 并保留 {{key}}。",
		parameters: {
			itemId: {
				type: "string",
				required: false,
				description: "只算某个目录项，如 二-01。留空则全部。映射 --only"
			},
			outPlan: {
				type: "string",
				required: false,
				description: "FillPlan 输出路径。默认 <工程>/_plan/fillplan.json"
			}
		},
		output: textOutput,
		async execute(args) {
			const outPlan = String(args?.outPlan ?? "") || join(resolveProjectDir(config), "_plan", "fillplan.json");
			assertWritable(outPlan, config);
			const argv = [
				"--project",
				resolveProjectFile(config),
				"--out",
				outPlan,
				"--json"
			];
			if (args?.itemId) argv.push("--only", String(args.itemId));
			return fmt("取值装配 · FillPlan", await runEngine(config, "datafill_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_docgen",
		description: "按目录清单生成文档：有模板的套模板，无模板的按 mode 三选一（template 选一个备用模板 / blank 建空白 / upload 占位等用户传 / skip 跳过）。默认跳过已存在的文档，保护用户的编辑成果。确定性批处理，不调用模型推理。",
		parameters: {
			itemId: {
				type: "string",
				required: true,
				description: "all 或具体 itemId（如 二-01）。映射 --item"
			},
			count: {
				type: "number",
				required: false,
				description: "生成份数，默认 1。映射 --count"
			},
			mode: {
				type: "string",
				required: false,
				description: "template / blank / upload / skip，默认 template。映射 --mode"
			},
			overwrite: {
				type: "boolean",
				required: false,
				description: "覆盖已存在文档，默认 false。映射 --overwrite"
			}
		},
		output: textOutput,
		async execute(args) {
			const outDir = resolveProjectDir(config);
			assertWritable(outDir, config);
			const argv = [
				"--project",
				resolveProjectFile(config),
				"--item",
				String(args?.itemId ?? ""),
				"--templates",
				resolveTemplatesDir(config),
				"--out",
				outDir,
				"--json"
			];
			if (args?.count != null) argv.push("--count", String(args.count));
			if (args?.mode) argv.push("--mode", String(args.mode));
			if (args?.overwrite) argv.push("--overwrite");
			return fmt("一键成册 · 文档生成", await runEngine(config, "docgen_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_fill",
		description: "按 FillPlan 把值填进模板生成文档，逐份输出到工程目录。确定性批处理，不调用模型推理。缺值的占位符原样保留 {{key}} 并记入报告，绝不填空字符串。若已用 yanshou_datafill 生成过计划，传 planPath 复用，保证与预览一致。",
		parameters: {
			outDir: {
				type: "string",
				required: false,
				description: "输出目录。默认当前工程目录。映射 --out"
			},
			planPath: {
				type: "string",
				required: false,
				description: "复用已有 FillPlan。留空则运行时重算。映射 --plan"
			},
			anchor: {
				type: "boolean",
				required: false,
				description: "写入 yz_ 书签 + customXml 锚点，默认 true。映射 --anchor on/off"
			}
		},
		output: textOutput,
		async execute(args) {
			const outDir = String(args?.outDir ?? "") || resolveProjectDir(config);
			assertWritable(outDir, config);
			const argv = [
				"--project",
				resolveProjectFile(config),
				"--out",
				outDir,
				"--templates",
				resolveTemplatesDir(config),
				"--json",
				"--anchor",
				args?.anchor === false ? "off" : "on"
			];
			if (args?.planPath) argv.push("--plan", String(args.planPath));
			return fmt("模板填充 · 填充引擎", await runEngine(config, "fill_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_numbering",
		description: "为文档分配/释放/恢复文档编号，格式 {合同编号}-{表名拼音缩写大写}-{流水号}，如 YYCZ-2026-0816-KGBSB-01。流水号在单个目录项内独立续排，删除只释放回本目录项的编号池，恢复取回原号。关键约束：编号在目录项内不重排 —— 删掉 02，03 仍然是 03。这是已打印纸质件的命根子。",
		parameters: {
			item: {
				type: "string",
				required: true,
				description: "目录项名或 itemId，优先 itemId。映射 --item"
			},
			action: {
				type: "string",
				required: false,
				description: "allocate（默认）/ release / restore。映射 --action"
			},
			count: {
				type: "number",
				required: false,
				description: "申请个数，默认 1。映射 --count"
			},
			docNo: {
				type: "string",
				required: false,
				description: "release / restore 时的目标编号。映射 --no"
			},
			docId: {
				type: "string",
				required: false,
				description: "restore 时的文档 id。映射 --doc-id"
			}
		},
		output: textOutput,
		async execute(args) {
			const project = resolveProjectFile(config);
			assertWritable(project, config);
			const argv = [
				"--project",
				project,
				"--item",
				String(args?.item ?? ""),
				"--action",
				String(args?.action ?? "allocate"),
				"--json"
			];
			if (args?.count != null) argv.push("--count", String(args.count));
			if (args?.docNo) argv.push("--no", String(args.docNo));
			if (args?.docId) argv.push("--doc-id", String(args.docId));
			return fmt("文档编号 · 编号引擎", await runEngine(config, "numbering_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_verify",
		description: "导出前最后一道查错：扫描残留占位符、字典里没有的 key、日期字段是否被误填。返回阻断项与警告项清单。有 block 级问题时不要继续导出，先让用户补齐。",
		parameters: {
			dir: {
				type: "string",
				required: false,
				description: "待校验目录，默认当前工程目录。映射 --dir"
			},
			level: {
				type: "string",
				required: false,
				description: "block（默认）或 all。映射 --level"
			}
		},
		output: textOutput,
		async execute(args) {
			const argv = [
				"--dir",
				String(args?.dir ?? "") || resolveProjectDir(config),
				"--project",
				resolveProjectFile(config),
				"--json"
			];
			if (args?.level) argv.push("--level", String(args.level));
			return fmt("导出前查错 · 校验闸门", await runEngine(config, "verify_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_aggregate",
		description: "把施工日志按周/月聚合生成项目周报与月报。窗口内没有源日志时直接失败，不生成空文档。确定性规则引擎（aggregate/statistic/count）取数与四栏写入，不调用模型、不编造事实。",
		parameters: {
			period: {
				type: "string",
				required: true,
				description: "week 或 month。映射 --period"
			},
			from: {
				type: "string",
				required: false,
				description: "起始日期 YYYY-MM-DD，默认上一自然周/月。映射 --from"
			},
			to: {
				type: "string",
				required: false,
				description: "截止日期 YYYY-MM-DD。映射 --to"
			},
			outDoc: {
				type: "string",
				required: false,
				description: "输出文档路径。映射 --out"
			}
		},
		output: textOutput,
		async execute(args) {
			if (args?.outDoc) assertWritable(String(args.outDoc), config);
			const argv = [
				"--period",
				String(args?.period ?? ""),
				"--project",
				resolveProjectFile(config),
				"--json"
			];
			if (args?.from) argv.push("--from", String(args.from));
			if (args?.to) argv.push("--to", String(args.to));
			if (args?.outDoc) argv.push("--out", String(args.outDoc));
			return fmt("日志汇总 · 自动汇总引擎", await runEngine(config, "aggregate_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_subtable",
		description: "识别文档中的清单型表格，按表头列名匹配后接管数据行：数据不足则克隆行，多余则删除行。模板侧不含任何子表标记，识别完全靠表头列名序列 —— 所以不要改模板表头文字。P5 已实现 8 张子表行克隆（不动 w:tblGrid；空数组保留静态表）。",
		parameters: {
			docPath: {
				type: "string",
				required: true,
				description: "目标文档路径。映射 --doc"
			},
			tableKey: {
				type: "string",
				required: false,
				description: "子表 key（" + TABLE_KEYS.join(" / ") + "）。留空则自动识别。映射 --table"
			},
			dataFile: {
				type: "string",
				required: false,
				description: "数据源 JSON/CSV。默认从 project.json._assets 取。映射 --data"
			}
		},
		output: textOutput,
		async execute(args) {
			assertWritable(String(args?.docPath ?? ""), config);
			const argv = [
				"--doc",
				String(args?.docPath ?? ""),
				"--json"
			];
			if (args?.tableKey) argv.push("--table", String(args.tableKey));
			if (args?.dataFile) argv.push("--data", String(args.dataFile));
			return fmt("清单表接管 · 子表识别引擎", await runEngine(config, "subtable_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_extract",
		description: "从一段自然语言或旧资料里抽取项目字段候选值（约 10 个）。抽取结果必须给人确认后才能回写，禁止静默落库。默认走字段字典别名规则（source=rules），不是伪造的模型回复。",
		parameters: {
			text: {
				type: "string",
				required: true,
				description: "待抽取的正文"
			}
		},
		output: textOutput,
		async execute(args) {
			const argv = [
				"--action",
				"extract",
				"--json",
				"--text",
				String(args?.text ?? "")
			];
			return fmt("智能填表 · 抽取候选", await runEngine(config, "ai_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_rewrite",
		description: "对正文做起草 / 润色 / 扩写。必须有 DEEPSEEK_API_KEY 且能访问 api.deepseek.com。无 Key 或断网时工具失败，不会编造一段假正文冒充模型。不得编造工程事实。",
		parameters: {
			mode: {
				type: "string",
				required: true,
				description: "draft / polish / expand"
			},
			text: {
				type: "string",
				required: true,
				description: "原文或要点"
			}
		},
		output: textOutput,
		async execute(args) {
			const mode = String(args?.mode ?? "polish");
			const argv = [
				"--action",
				mode,
				"--json",
				"--project",
				resolveProjectFile(config),
				"--text",
				String(args?.text ?? "")
			];
			return fmt("正文 " + mode, await runEngine(config, "ai_engine.py", argv));
		}
	}));
	ctx.tools.register(defineTool({
		name: "yanshou_qa",
		description: "查错问答：先跑 yanshou_verify 校验闸门，有模型时再解说。断网或无 Key 时失败（壳侧入口置灰），不会伪造问答。",
		parameters: {},
		output: textOutput,
		async execute() {
			const argv = [
				"--action",
				"qa",
				"--json",
				"--project",
				resolveProjectFile(config)
			];
			return fmt("查错问答", await runEngine(config, "ai_engine.py", argv));
		}
	}));
}
//#endregion
//#region src/index.ts
/** 插件名（Cordis 用它做日志与卸载定位） */
const name = "yanshou-docs";
/**
* 声明依赖：Cordis 会等这些服务就绪后才调用 apply。
* 只依赖工具注册表。不用 dsh.client / ui-* —— 编辑区由自建壳拥有。
*/
const inject = ["tools"];
/**
* 验收资料引擎插件。
*
* 定位：A+ 架构里的「接线层」。
*   - 不实现任何文档处理逻辑（那些在 Python 引擎里）
*   - 不做 UI（UI 是自建桌面壳；dsh 这里是 sdk/JSON-RPC 后端）
*   - 唯一职责：把七块引擎注册成工具
*
* 因为薄，所以可替换：将来若不用 dsh，这一层整片扔掉即可。
*/
function apply(ctx, config) {
	registerTools(ctx, config);
	console.log(`[yanshou-docs] 已加载 | 引擎目录 ${resolveEngineRoot(config)} | 模板保护 ${config.allowWriteToTemplates ? "已放开" : config.protectedPaths.join("、")}`);
}
//#endregion
export { Config, apply, assertWritable, explain, findBlocked, inject, isProtected, name, normalize };
