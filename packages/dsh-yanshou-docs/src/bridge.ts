import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { existsSync } from 'node:fs'
import type { Config } from './config'

/**
 * 引擎桥 —— A+ 架构的关键接缝。
 *
 * 插件层只做接线：把工具调用翻译成一次 Python 子进程调用，再把
 * stdout 最后一行契约 JSON 回成工具结果。
 */

export interface EngineResult {
  ok: boolean
  code: number
  stdout: string
  stderr: string
  /** 给人（模型）看的摘要：优先契约 JSON 的 summary/stats/errors */
  summary: string
  /** 解析出的契约 JSON；解析失败则为 null */
  contract: Record<string, unknown> | null
}

export function resolveEngineRoot(config: Config): string {
  if (config.engineRoot) return config.engineRoot
  return join(config.installRoot, 'engine')
}

export function resolveTemplatesDir(config: Config): string {
  return join(config.installRoot, 'templates')
}

export function resolveProjectFile(config: Config): string {
  const raw = (config.activeProject || config.workspaceRoot || '').trim()
  if (!raw) return join(config.workspaceRoot || '.', 'project.json')
  if (/project\.json$/i.test(raw)) return raw
  return join(raw, 'project.json')
}

export function resolveProjectDir(config: Config): string {
  return dirname(resolveProjectFile(config))
}

/** 解析引擎 stdout：必须取最后一行 JSON（数据与规则规格 §6）。失败才退回尾部文本。 */
export function parseContractStdout(stdout: string): {
  contract: Record<string, unknown> | null
  summary: string
} {
  const lines = stdout
    .trim()
    .split(/\r?\n/)
    .filter((l) => l.trim().length > 0)
  if (!lines.length) return { contract: null, summary: '完成（无输出）' }
  const last = lines[lines.length - 1]
  try {
    const obj = JSON.parse(last) as Record<string, unknown>
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      const looksLikeContract =
        'ok' in obj || 'engine' in obj || 'summary' in obj || 'stats' in obj
      if (looksLikeContract) {
        const bits: string[] = []
        if (obj.summary != null) bits.push(String(obj.summary))
        if (obj.stats != null) bits.push('stats ' + JSON.stringify(obj.stats))
        if (Array.isArray(obj.errors) && obj.errors.length) {
          bits.push('errors ' + JSON.stringify(obj.errors))
        }
        return { contract: obj, summary: bits.join('\n') || last }
      }
    }
  } catch {
    /* fall through to text summary */
  }
  return { contract: null, summary: lines.slice(-8).join('\n') }
}

/** 超时后杀掉整棵进程树：Windows 用 taskkill /T /F，POSIX 杀进程组。 */
export function killProcessTree(pid: number | undefined): void {
  if (pid == null || !Number.isFinite(pid) || pid <= 0) return
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(pid), '/T', '/F'], {
      windowsHide: true,
      stdio: 'ignore',
      shell: false,
    }).on('error', () => {
      try {
        process.kill(pid)
      } catch {
        /* already gone */
      }
    })
    return
  }
  try {
    process.kill(-pid, 'SIGKILL')
  } catch {
    try {
      process.kill(pid, 'SIGKILL')
    } catch {
      /* already gone */
    }
  }
}

export function runEngine(
  config: Config,
  script: string,
  args: string[] = [],
  opts: { cwd?: string; timeoutMs?: number } = {},
): Promise<EngineResult> {
  const scriptPath = join(resolveEngineRoot(config), script)
  const cwd = opts.cwd ?? config.workspaceRoot
  const timeoutMs = opts.timeoutMs ?? config.engineTimeoutMs ?? 10 * 60 * 1000

  return new Promise<EngineResult>((resolveResult) => {
    if (!existsSync(scriptPath)) {
      resolveResult({
        ok: false,
        code: -2,
        stdout: '',
        stderr: `引擎脚本不存在：${scriptPath}`,
        summary: `引擎脚本不存在：${scriptPath}`,
        contract: null,
      })
      return
    }

    const env = {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
    }

    const child = spawn(config.pythonBin, [scriptPath, ...args], {
      cwd,
      windowsHide: true,
      shell: false,
      env,
      // POSIX: 新进程组，便于超时后 kill(-pid)
      detached: process.platform !== 'win32',
    })

    let stdout = ''
    let stderr = ''
    let settled = false

    const finish = (result: EngineResult) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolveResult(result)
    }

    const timer = setTimeout(() => {
      killProcessTree(child.pid)
      const parsed = parseContractStdout(stdout)
      finish({
        ok: false,
        code: -3,
        stdout,
        stderr,
        summary: `引擎执行超时（${Math.round(timeoutMs / 1000)}s）`,
        contract: parsed.contract,
      })
    }, timeoutMs)

    child.stdout.on('data', (d: Buffer) => {
      stdout += d.toString('utf8')
    })
    child.stderr.on('data', (d: Buffer) => {
      stderr += d.toString('utf8')
    })
    child.on('error', (err: Error) => {
      finish({
        ok: false,
        code: -1,
        stdout,
        stderr: `${stderr}\n${String(err)}`.trim(),
        summary: `无法启动 Python：${String(err)}`,
        contract: null,
      })
    })
    child.on('close', (code: number | null) => {
      const rc = code ?? -1
      const parsed = parseContractStdout(stdout)
      const fallback = parsed.summary || (rc === 0 ? '完成（无输出）' : `退出码 ${rc}`)
      finish({
        ok: rc === 0,
        code: rc,
        stdout,
        stderr,
        summary: fallback,
        contract: parsed.contract,
      })
    })
  })
}
