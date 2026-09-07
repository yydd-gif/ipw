import fs from 'node:fs'
import path from 'node:path'
import PizZip from 'pizzip'
import { itemFolderName } from '../shared/catalog'
import type { CatalogItem, CatalogVolumeState, ExportCheck, Project } from '../shared/types'
import { generatedDir, ensureDir, projectDir, sanitizeFilePart, zipRootName } from './paths'

export function renderIndexMarkdown(
  project: Project,
  check: ExportCheck,
  state: CatalogVolumeState[]
): string {
  const lines: string[] = [
    `# 验收资料包目录与校验报告`,
    ``,
    `- 项目名称：${project.name}`,
    `- 项目类型：${project.type}`,
    `- 建设单位：${project.owner}`,
    `- 监理单位：${project.supervisor}`,
    `- 施工单位：${project.contractor}`,
    `- 合同号：${project.contract_no}`,
    `- 阶段：${project.phase}`,
    `- 文号：${project.doc_no}`,
    `- 导出时间：${new Date().toISOString()}`,
    `- 必填条目：${check.required}（已确认 ${check.confirmed}，免于提供 ${check.waived}）`,
    `- 校验结果：${check.ok ? '通过' : '未通过'}`,
    ``,
    `## 资料目录`,
    ``
  ]
  for (const vol of state) {
    lines.push(`### ${vol.volume.folder} ${vol.volume.title}`)
    lines.push(``)
    lines.push(`| 编号 | 名称 | 类型 | 必填 | 状态 | 文件数 |`)
    lines.push(`| --- | --- | --- | --- | --- | --- |`)
    for (const entry of vol.items) {
      const files = (entry.instance.generated_path ? 1 : 0) + entry.uploads.length
      lines.push(
        `| ${entry.item.code} | ${entry.item.title} | ${entry.item.produceType} | ${
          entry.item.required ? '是' : '否'
        } | ${entry.instance.status} | ${files} |`
      )
    }
    lines.push(``)
  }
  lines.push(`> 生成本包的应用：验收到手 Acceptance Studio M1。Word 由本地模板填充；后续可接入 GenOffice。`)
  lines.push(``)
  return lines.join('\n')
}

export function packAcceptanceZip(args: {
  project: Project
  check: ExportCheck
  state: CatalogVolumeState[]
  dataDir: string
  destPath?: string
}): string {
  const root = zipRootName(args.project)
  const zip = new PizZip()
  zip.file(`${root}/00_目录与校验报告.md`, renderIndexMarkdown(args.project, args.check, args.state))

  for (const vol of args.state) {
    for (const entry of vol.items) {
      const folder = `${root}/${vol.volume.folder}/${itemFolderName(entry.item)}`
      let copied = 0
      const generated = generatedFilesForItem(args.dataDir, args.project.id, entry.item, entry.instance.generated_path)
      for (const filePath of generated) {
        zip.file(`${folder}/${path.basename(filePath)}`, fs.readFileSync(filePath))
        copied += 1
      }
      for (const upload of entry.uploads) {
        if (fs.existsSync(upload.stored_path)) {
          zip.file(`${folder}/${upload.original_name}`, fs.readFileSync(upload.stored_path))
          copied += 1
        }
      }
      if (copied === 0 && entry.instance.status === 'waived') {
        zip.file(
          `${folder}/免于提供说明.txt`,
          `条目 ${entry.item.code} ${entry.item.title} 免于提供。\n原因：${entry.instance.notes || '未填写'}\n`
        )
      }
    }
  }

  const out =
    args.destPath || path.join(projectDir(args.dataDir, args.project.id), `${root}.zip`)
  ensureDir(path.dirname(out))
  fs.writeFileSync(out, zip.generate({ type: 'nodebuffer', compression: 'DEFLATE' }) as Buffer)
  return out
}

function generatedFilesForItem(
  dataDir: string,
  projectId: string,
  item: CatalogItem,
  generatedPath: string | null
): string[] {
  const dir = generatedDir(dataDir, projectId)
  const prefix = sanitizeFilePart(`${item.code}_${item.title}`)
  const seen = new Set<string>()
  const files: string[] = []
  const add = (filePath: string): void => {
    const name = path.basename(filePath)
    if (seen.has(name) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) return
    seen.add(name)
    files.push(filePath)
  }
  if (fs.existsSync(dir)) {
    for (const name of fs.readdirSync(dir).sort()) {
      if (name.startsWith(prefix)) add(path.join(dir, name))
    }
  }
  if (generatedPath) add(generatedPath)
  return files
}
