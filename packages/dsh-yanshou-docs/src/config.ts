import Schema from '@deepseek-ai/schemastery'

/**
 * 插件配置（双轨制）。
 *
 * 遵循 Harness 约定：凡是不同部署可能取不同值的参数，一律做成配置字段，
 * 不在代码里硬编码。检验标准 —— 能否在不改代码的前提下于 cordis.yml 里改掉它？
 */
export interface Config {
  /** 安装资产根（只读）：templates / spec / engine / runtime 都在这里 */
  installRoot: string
  /** 工程数据根（可读写，用户可整包拷走） */
  workspaceRoot: string
  /** 内嵌 Python 解释器。交付时由安装器写入；开发机可填 `python`。 */
  pythonBin: string
  /** 引擎脚本目录。留空 = <installRoot>/engine */
  engineRoot: string
  /** 默认工程（未指定时用哪个工程目录或 project.json） */
  activeProject: string
  /** 受保护路径（相对 installRoot 或绝对路径），一律拒绝写入 */
  protectedPaths: string[]
  /** 逃生开关，默认 false */
  allowWriteToTemplates: boolean
  /** 单次引擎调用的超时（毫秒） */
  engineTimeoutMs: number
}

export const Config = Schema.object({
  installRoot: Schema.string().required(),
  workspaceRoot: Schema.string().required(),
  pythonBin: Schema.string().default('python'),
  engineRoot: Schema.string().default(''),
  activeProject: Schema.string().default(''),
  protectedPaths: Schema.array(Schema.string()).default([
    'templates',
    'templates-backup',
    'templates_原始备份',
  ]),
  allowWriteToTemplates: Schema.boolean().default(false),
  engineTimeoutMs: Schema.number().default(600000),
})
