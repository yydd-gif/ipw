import Schema from '@deepseek-ai/schemastery'

/**
 * 插件配置。
 *
 * 遵循 Harness 约定：凡是不同部署可能取不同值的参数，一律做成配置字段，
 * 不在代码里硬编码。检验标准 —— 能否在不改代码的前提下于 cordis.yml 里改掉它？
 */
export interface Config {
  /** Python 解释器可执行文件路径。引擎层用 Python，插件层只负责接线。 */
  pythonBin: string
  /** 引擎脚本目录（绝对路径）。留空则回退到 <workspaceRoot>/.workbuddy/engine */
  engineRoot: string
  /** 工程根目录：存放 project.json 与各分册文档 */
  workspaceRoot: string
  /** 受保护目录（相对 workspaceRoot 或绝对路径）。这些路径一律拒绝写入。 */
  protectedPaths: string[]
  /** 逃生开关。默认 false —— 任何写模板的动作都会被拦下。 */
  allowWriteToTemplates: boolean
  /** 报告输出目录（相对 workspaceRoot） */
  reportDir: string
}

export const Config: Schema<Config> = Schema.object({
  pythonBin: Schema.string().default('python'),
  engineRoot: Schema.string().default(''),
  workspaceRoot: Schema.string().default('.'),
  protectedPaths: Schema.array(Schema.string()).default(['模版', '模版_原始备份']),
  allowWriteToTemplates: Schema.boolean().default(false),
  reportDir: Schema.string().default('_导出'),
})
