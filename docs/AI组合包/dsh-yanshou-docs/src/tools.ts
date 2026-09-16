import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { Config } from './config'
import { runEngine } from './bridge'
import { assertWritable } from './policy'

/**
 * 五块确定性引擎的工具化。
 *
 * 全部走 defineTool + ctx.tools.register 的官方注册方式，
 * 每块引擎对应一个面向模型的工具，模型可以在轮次里直接调用。
 *
 * 注意分工：**确定性批处理本身不交给模型推理**。模型负责「决定调哪个工具、
 * 传什么参数、怎么解读结果」；真正套模板填字段的活，是 Python 引擎在
 * 一次子进程里跑完的，输入固定、输出唯一、100% 可复现。
 */

const textOutput = {
  schema: { type: 'string' as const },
  render: (_args: unknown, value: string) => [{ type: 'text' as const, text: value }],
}

function fmt(title: string, r: { ok: boolean; code: number; stdout: string; stderr: string; summary: string }): string {
  const head = r.ok ? `【${title}】完成` : `【${title}】未通过（退出码 ${r.code}）`
  const parts = [head, '', r.summary]
  if (!r.ok && r.stderr.trim()) {
    parts.push('', '── stderr ──', r.stderr.trim().slice(-1500))
  }
  return parts.join('\n')
}

export function registerTools(ctx: Context, config: Config): void {
  // ── 1. 一键成册：按字典 + project.json 批量填充模板 ──────────────
  ctx.tools.register(
    defineTool({
      name: 'yanshou_fill',
      description:
        '按字段字典与 project.json 批量填充验收资料模板，逐份输出到工程目录。' +
        '确定性批处理，不调用模型推理。缺值的占位符会原样保留 {{key}} 并记入报告，绝不填空。',
      parameters: {
        outDir: {
          type: 'string',
          required: false,
          description: '输出目录（相对 workspaceRoot 或绝对路径）。默认为 _导出/工程',
        },
        projectFile: {
          type: 'string',
          required: false,
          description: 'project.json 路径，含项目级字段值与 _documents 文档级覆盖',
        },
      },
      output: textOutput,
      async execute(args: any) {
        const outDir: string = args?.outDir ?? config.reportDir
        // 输出目录若落在受保护范围内，直接拒绝
        assertWritable(outDir, config)
        const argv = ['--out', outDir]
        if (args?.projectFile) argv.push('--project', args.projectFile)
        const r = await runEngine(config, 'fill_engine.py', argv)
        return fmt('一键成册 · 填充引擎', r)
      },
    }),
  )

  // ── 2. 残留校验：扫输出目录还剩多少未填占位符 ───────────────────
  ctx.tools.register(
    defineTool({
      name: 'yanshou_verify',
      description:
        '扫描指定目录，报告残留的 {{占位符}}、未在字典中定义的 key、以及日期字段是否被误填。' +
        '用于导出前的最后一道查错。',
      parameters: {
        targetDir: {
          type: 'string',
          required: false,
          description: '待校验目录，默认 _导出/工程',
        },
      },
      output: textOutput,
      async execute(args: any) {
        const target = args?.targetDir ?? `${config.reportDir}/工程`
        const r = await runEngine(config, 'verify_engine.py', ['--dir', target])
        return fmt('导出前查错 · 残留校验', r)
      },
    }),
  )

  // ── 3. 子表识别：按表头列名接管数据行 ──────────────────────────
  ctx.tools.register(
    defineTool({
      name: 'yanshou_subtable',
      description:
        '识别文档中的清单型表格（软硬件配置清单、调试记录、试运行记录、评审评分表、文档移交清单等），' +
        '按表头列名序列匹配后接管数据行：不足克隆、多余删除。模板侧不写 {{#rows:}} 标记。',
      parameters: {
        docPath: { type: 'string', required: true, description: '目标文档路径' },
        tableKey: {
          type: 'string',
          required: false,
          description: '子表 key（deviceList / softwareList / testItemList / trialRunList / expertScoreList / documentList / documentChecklist / volumeList）。留空则自动识别',
        },
        dataFile: { type: 'string', required: false, description: '数据源 JSON/CSV 路径' },
      },
      output: textOutput,
      async execute(args: any) {
        assertWritable(args?.docPath ?? '', config)
        const argv = ['--doc', args?.docPath ?? '']
        if (args?.tableKey) argv.push('--table', args.tableKey)
        if (args?.dataFile) argv.push('--data', args.dataFile)
        const r = await runEngine(config, 'subtable_engine.py', argv)
        return fmt('清单表接管 · 子表识别引擎', r)
      },
    }),
  )

  // ── 4. 编号分配：{合同编号}-{表名缩写}-{流水号} ─────────────────
  ctx.tools.register(
    defineTool({
      name: 'yanshou_numbering',
      description:
        '为新增文档分配文档编号，格式 {合同编号}-{表名拼音缩写大写}-{流水号}，如 YY123-KGBSB-01。' +
        '流水号在单个目录项内独立续排；无合同编号时用纯流水号。删除释放回本目录项编号池，恢复取回原号。',
      parameters: {
        catalogItem: { type: 'string', required: true, description: '目录项名，如「开工报审表」' },
        count: { type: 'number', required: false, description: '申请分配的编号个数，默认 1' },
        action: {
          type: 'string',
          required: false,
          description: 'allocate（默认）/ release（释放某个编号）/ restore（恢复）',
        },
        docNo: { type: 'string', required: false, description: 'release / restore 时的目标编号' },
      },
      output: textOutput,
      async execute(args: any) {
        const argv = ['--item', args?.catalogItem ?? '', '--action', args?.action ?? 'allocate']
        if (args?.count) argv.push('--count', String(args.count))
        if (args?.docNo) argv.push('--no', args.docNo)
        const r = await runEngine(config, 'numbering_engine.py', argv)
        return fmt('文档编号 · 编号引擎', r)
      },
    }),
  )

  // ── 5. 自动汇总：施工日志 → 项目周报 → 项目月报 ──────────────────
  ctx.tools.register(
    defineTool({
      name: 'yanshou_aggregate',
      description:
        '把施工日志按周/月聚合生成项目周报与项目月报。这是典型的 AI 场景：模型负责把零散日志' +
        '归纳成通顺的周报正文，引擎负责取数与写入文档。',
      parameters: {
        period: { type: 'string', required: true, description: '周报填 week，月报填 month' },
        from: { type: 'string', required: false, description: '起始日期 YYYY-MM-DD' },
        to: { type: 'string', required: false, description: '截止日期 YYYY-MM-DD' },
        outDoc: { type: 'string', required: false, description: '输出文档路径' },
      },
      output: textOutput,
      async execute(args: any) {
        if (args?.outDoc) assertWritable(args.outDoc, config)
        const argv = ['--period', args?.period ?? 'week']
        if (args?.from) argv.push('--from', args.from)
        if (args?.to) argv.push('--to', args.to)
        if (args?.outDoc) argv.push('--out', args.outDoc)
        const r = await runEngine(config, 'aggregate_engine.py', argv)
        return fmt('日志汇总 · 自动汇总引擎', r)
      },
    }),
  )
}
