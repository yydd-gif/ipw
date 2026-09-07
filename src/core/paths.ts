import fs from 'node:fs'
import path from 'node:path'
import type { CatalogItem, Project } from '../shared/types'
import { itemFolderName } from '../shared/catalog'

export interface StudioDirs {
  dataDir: string
  templatesDir: string
}

export function projectDir(dataDir: string, projectId: string): string {
  return path.join(dataDir, 'projects', projectId)
}

export function generatedDir(dataDir: string, projectId: string): string {
  return path.join(projectDir(dataDir, projectId), 'generated')
}

export function uploadsDir(dataDir: string, projectId: string, item: CatalogItem): string {
  return path.join(projectDir(dataDir, projectId), 'uploads', itemFolderName(item))
}

export function exportStagingDir(dataDir: string, projectId: string): string {
  return path.join(projectDir(dataDir, projectId), 'export-staging')
}

export function ensureDir(dir: string): string {
  fs.mkdirSync(dir, { recursive: true })
  return dir
}

export function sanitizeFilePart(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim() || '未命名'
}

export function zipRootName(project: Project, date = new Date()): string {
  const y = date.toISOString().slice(0, 10).replace(/-/g, '')
  return `验收资料包_${sanitizeFilePart(project.name)}_${y}`
}

export function todayISO(d = new Date()): string {
  const tz = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return tz.toISOString().slice(0, 10)
}
