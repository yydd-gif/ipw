import type { Context } from '@deepseek-ai/cordis'
import { Config } from './config'
import type { Config as YanshouConfig } from './config'
import { registerTools } from './tools'
import { resolveEngineRoot } from './bridge'

export { Config }
export type { YanshouConfig }
export { assertWritable, isProtected, findBlocked, explain, normalize } from './policy'

/** 插件名（Cordis 用它做日志与卸载定位） */
export const name = 'yanshou-docs'

/**
 * 声明依赖：Cordis 会等这些服务就绪后才调用 apply。
 * 只依赖工具注册表。不用 dsh.client / ui-* —— 编辑区由自建壳拥有。
 */
export const inject = ['tools']

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
export function apply(ctx: Context, config: YanshouConfig) {
  registerTools(ctx, config)

  console.log(
    `[yanshou-docs] 已加载 | 引擎目录 ${resolveEngineRoot(config)} | ` +
      `模板保护 ${config.allowWriteToTemplates ? '已放开' : config.protectedPaths.join('、')}`,
  )
}
