import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { realpathSync } from "node:fs";
//#region src/policy.ts
/**
* 模板保护策略。
*
* 铁律：**AI 绝不写 `assets/templates/` 下的 docx**。口头规矩靠不住，所以落成代码：
* 任何写入路径先过 assertWritable()，命中受保护目录直接抛 TemplateProtectionError。
*
* 路径基准是 installRoot（模板在资产侧），不是 workspaceRoot（工程数据侧）。
* 比较前用 realpathSync 解开符号链接 / Windows junction，防止绕过。
*
* 全局 `tools/pre-execute` 钩子本阶段不开：确切回调签名仍未确认（施工图 §3.8）。
*/
function tryRealpath(p) {
	try {
		return realpathSync(p);
	} catch {
		let cur = p;
		while (true) {
			const parent = dirname(cur);
			if (parent === cur) return p;
			try {
				const realParent = realpathSync(parent);
				return join(realParent, relative(parent, p));
			} catch {
				cur = parent;
			}
		}
	}
}
/** 把任意路径规整成可比较的绝对形式（解 symlink / junction） */
function normalize(p, base) {
	const real = tryRealpath(isAbsolute(p) ? resolve(p) : resolve(base, p));
	return process.platform === "win32" ? real.toLowerCase() : real;
}
/** 判断 target 是否落在受保护目录内（含目录本身） */
function isProtected(target, config) {
	if (config.allowWriteToTemplates) return false;
	const safe = normalize(target, config.installRoot);
	return config.protectedPaths.some((raw) => {
		const guard = normalize(raw, config.installRoot);
		if (safe === guard) return true;
		const prefix = guard.endsWith(sep) ? guard : guard + sep;
		return safe.startsWith(prefix);
	});
}
/** 命中受保护目录时的说明文本 */
function explain(target, config) {
	const abs = isAbsolute(target) ? target : resolve(config.installRoot, target);
	return [
		"TemplateProtectionError: 已拦截一次对模板目录的写入。",
		`目标：${relative(config.installRoot, abs) || target}`,
		`受保护：${config.protectedPaths.join("、")}`,
		"",
		"模板侧是冻结安装资产，程序只读不写。",
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
/** 批量校验：给一组路径，返回其中被拦下的 */
function findBlocked(targets, config) {
	return targets.filter((t) => isProtected(t, config));
}
//#endregion
export { assertWritable, explain, findBlocked, isProtected, normalize };
