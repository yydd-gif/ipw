import { spawn } from 'node:child_process'
import { join } from 'node:path'
import { existsSync } from 'node:fs'
import type { Config } from './config'

/**
 * 引擎桥 —— A+ 架构的关键接缝。
 *
 * 设计取舍：五块确定性引擎已经用 Python 写好并验证过（填充引擎实测
 * 1 秒跑完 37 份、171/171 命中、100% 可复现）。为了「零重写」，
 * 插件层只做接线：把工具调用翻译成一次 Python 子进程调用，再把
 * stdout 回成工具结果。
 *
 * 为什么不把这些逻辑写进 TS？
 *   1. 已验证的代码不该为了换个运行时重写；
 *   2. 确定性批处理必须 100% 可复现，Python 侧已经做到；
 *   3. 插件层保持「薄如纸」，将来换掉 dsh 时这一层可以整片扔掉。
 */

export interface EngineResult {
  ok: boolean
  code: number
  stdout: string
  stderr: string
  /** 由 stdout 尾部截取的摘要，供工具 render 用 */
  summary: string
}

/** 解析引擎脚本目录 */
export function resolveEngineRoot(config: Config): string {
  if (config.engineRoot) return config.engineRoot
  return join(config.workspaceRoot, '.workbuddy', 'engine')
}

/** 执行一个引擎脚本 */
export function runEngine(
  config: Config,
  script: string,
  args: string[] = [],
  opts: { cwd?: string; timeoutMs?: number } = {},
): Promise<EngineResult> {
  const scriptPath = join(resolveEngineRoot(config), script)
  const cwd = opts.cwd ?? config.workspaceRoot
  const timeoutMs = opts.timeoutMs ?? 10 * 60 * 1000

  return new Promise<EngineResult>((resolve) => {
    if (!existsSync(scriptPath)) {
      resolve({
        ok: false,
        code: -2,
        stdout: '',
        stderr: `引擎脚本不存在：${scriptPath}`,
        summary: `引擎脚本不存在：${scriptPath}`,
      })
      return
    }

    const child = spawn(config.pythonBin, [scriptPath, ...args], {
      cwd,
      windowsHide: true,
      // 不继承 shell，避免命令行注入；参数一律走 argv
      shell: false,
    })

    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill()
      resolve({
        ok: false,
        code: -3,
        stdout,
        stderr,
        summary: `引擎执行超时（${Math.round(timeoutMs / 1000)}s）`,
      })
    }, timeoutMs)

    child.stdout.on('data', (d: Buffer) => {
      stdout += d.toString('utf8')
    })
    child.stderr.on('data', (d: Buffer) => {
      stderr += d.toString('utf8')
    })
    child.on('error', (err: Error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({
        ok: false,
        code: -1,
        stdout,
        stderr: `${stderr}\n${String(err)}`,
        summary: `无法启动 Python：${String(err)}`,
      })
    })
    child.on('close', (code: number | null) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      const rc = code ?? -1
      const tail = stdout.trim().split(/\r?\n/).slice(-8).join('\n')
      resolve({
        ok: rc === 0,
        code: rc,
        stdout,
        stderr,
        summary: tail || (rc === 0 ? '完成（无输出）' : `退出码 ${rc}`),
      })
    })
  })
}
