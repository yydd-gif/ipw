import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export interface EngineFillReport {
  ok: boolean
  residual_keys: string[]
  filled_path: string
  preview_path: string
  message: string
}

export interface EngineStatus {
  python: boolean
  engine: boolean
  pythonBin: string
  enginePath: string
  message: string
}

function defaultEnginePath(): string {
  const fromEnv = process.env.ACCEPTANCE_FILL_ENGINE
  if (fromEnv) return fromEnv
  const here = dirname(fileURLToPath(import.meta.url))
  const candidates = [
    join(process.cwd(), 'engine', 'fill_engine.py'),
    join(here, '..', '..', 'engine', 'fill_engine.py'),
    join(here, '..', '..', '..', 'engine', 'fill_engine.py')
  ]
  return candidates.find((p) => existsSync(p)) ?? candidates[0]!
}

export function resolvePythonBin(override?: string): string {
  return override || process.env.ACCEPTANCE_PYTHON || process.env.PYTHON || 'python3'
}

export function resolveEnginePath(override?: string): string {
  return override || defaultEnginePath()
}

export function probeEngine(opts?: { pythonBin?: string; enginePath?: string }): EngineStatus {
  const pythonBin = resolvePythonBin(opts?.pythonBin)
  const enginePath = resolveEnginePath(opts?.enginePath)
  const engine = existsSync(enginePath)
  if (!engine) {
    return {
      python: false,
      engine: false,
      pythonBin,
      enginePath,
      message: `未找到离线填充引擎：${enginePath}。请确认仓库 engine/fill_engine.py 存在。`
    }
  }
  const bins = pythonBin === 'python3' ? [pythonBin, 'python'] : [pythonBin]
  for (const bin of bins) {
    const probe = spawnSync(bin, ['--version'], { encoding: 'utf8' })
    if (!probe.error && probe.status === 0) {
      return {
        python: true,
        engine: true,
        pythonBin: bin,
        enginePath,
        message: `${probe.stdout || probe.stderr}`.trim()
      }
    }
  }
  return {
    python: false,
    engine: true,
    pythonBin,
    enginePath,
    message: `未找到 Python（尝试 ${bins.join(' / ')}）。一键成册需要本机 Python 3。Win 便携包将在后续 PR 提供。`
  }
}

export function runFillEngine(args: {
  pythonBin?: string
  enginePath?: string
  template: string
  dataPath: string
  outPath: string
  previewPath: string
}): EngineFillReport {
  const status = probeEngine({ pythonBin: args.pythonBin, enginePath: args.enginePath })
  if (!status.python || !status.engine) {
    return {
      ok: false,
      residual_keys: [],
      filled_path: '',
      preview_path: '',
      message: status.message
    }
  }
  const result = spawnSync(
    status.pythonBin,
    [
      status.enginePath,
      'fill',
      '--template',
      args.template,
      '--data',
      args.dataPath,
      '--out',
      args.outPath,
      '--preview',
      args.previewPath
    ],
    { encoding: 'utf8' }
  )
  if (result.error) {
    return {
      ok: false,
      residual_keys: [],
      filled_path: '',
      preview_path: '',
      message: result.error.message
    }
  }
  const stdout = (result.stdout || '').trim()
  if (result.status !== 0) {
    return {
      ok: false,
      residual_keys: [],
      filled_path: '',
      preview_path: '',
      message: (result.stderr || stdout || `fill_engine 退出码 ${result.status}`).trim()
    }
  }
  try {
    return JSON.parse(stdout) as EngineFillReport
  } catch {
    return {
      ok: false,
      residual_keys: [],
      filled_path: args.outPath,
      preview_path: args.previewPath,
      message: `fill_engine 输出无法解析：${stdout.slice(0, 400)}`
    }
  }
}

export function scanMustaches(text: string): string[] {
  const keys = new Set<string>()
  const re = /\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    keys.add(m[1]!)
  }
  return [...keys].sort()
}
