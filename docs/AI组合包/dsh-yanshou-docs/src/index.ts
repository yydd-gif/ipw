import type { Context } from '@deepseek-ai/cordis'
import { Config } from './config'
import type { Config as YanshouConfig } from './config'
import { registerTools } from './tools'
import { resolveEngineRoot } from './bridge'

export { Config }
export type { YanshouConfig }

/** 插件名（Cordis 用它做日志与卸载定位） */
export const name = 'yanshou-docs'

/**
 * 声明依赖：Cordis 会等这些服务就绪后才调用 apply。
 * 我们只依赖工具注册表 —— 五块引擎全部以「面向模型的工具」形式暴露。
 */
export const inject = ['tools']

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
export function apply(ctx: Context, config: YanshouConfig) {
  registerTools(ctx, config)

  console.log(
    `[yanshou-docs] 已加载 | 引擎目录 ${resolveEngineRoot(config)} | ` +
      `模板保护 ${config.allowWriteToTemplates ? '已放开' : config.protectedPaths.join('、')}`,
  )

  // 任何通过 ctx 注册的东西（工具、事件、定时器）在插件卸载时自动清理，
  // 无需手写 removeListener。若将来引入需要手动释放的资源（如常驻子进程），
  // 用 ctx.effect(() => { ...; return () => cleanup() }) 声明。
}
