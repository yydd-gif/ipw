import { resolve, relative, isAbsolute, sep } from 'node:path'
import type { Config } from './config'

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
function normalize(p: string, base: string): string {
  const abs = isAbsolute(p) ? resolve(p) : resolve(base, p)
  return process.platform === 'win32' ? abs.toLowerCase() : abs
}

/** 判断 target 是否落在受保护目录内（含目录本身） */
export function isProtected(target: string, config: Config): boolean {
  if (config.allowWriteToTemplates) return false
  const safe = normalize(target, config.workspaceRoot)
  return config.protectedPaths.some((raw) => {
    const guard = normalize(raw, config.workspaceRoot)
    if (safe === guard) return true
    return safe.startsWith(guard.endsWith(sep) ? guard : guard + sep)
  })
}

/** 命中受保护目录时的说明文本 */
function explain(target: string, config: Config): string {
  const rel = relative(config.workspaceRoot, isAbsolute(target) ? target : resolve(config.workspaceRoot, target))
  return [
    '已拦截一次对模板目录的写入。',
    `目标：${rel || target}`,
    `受保护：${config.protectedPaths.join('、')}`,
    '',
    '模板侧由工头手动维护，程序只读不写。',
    '若确实需要临时放开，在 profile 的 cordis.patch.yml 里把 allowWriteToTemplates 置为 true —— 改完记得改回来。',
  ].join('\n')
}

/** 写盘前的强制闸门。受保护则抛错。 */
export function assertWritable(target: string, config: Config): void {
  if (isProtected(target, config)) {
    const err = new Error(explain(target, config))
    err.name = 'TemplateProtectionError'
    throw err
  }
}

/** 批量校验：给一组路径，返回其中被拦下的 */
export function findBlocked(targets: string[], config: Config): string[] {
  return targets.filter((t) => isProtected(t, config))
}

/*
 * ── 全局钩子（待真机确认签名后启用） ──────────────────────────────
 *
 * dsh 架构文档「新行为的归属位置」一表记载：
 *   「拦截请求、工具或轮次 → 使用相应的 agent/* 或 tools/* 事件」
 * 且 tool-execution-pipeline 里 before 阶段是 waterfall 事件（须调用 next()）。
 *
 * 预期形态（签名待验证，勿直接启用）：
 *
 *   ctx.on('tools/pre-execute', async (call, next) => {
 *     const targets = collectPaths(call?.args ?? {})
 *     const blocked = findBlocked(targets, config)
 *     if (blocked.length) {
 *       return { block: true, reason: explain(blocked[0], config) }
 *     }
 *     return next()
 *   })
 *
 * 在装好 dsh 之后，先打印一次真实事件对象的结构再定稿：
 *   dsh --profile yanshou --patch ./probe.yml   # 探针插件里打印 call 的键
 */
