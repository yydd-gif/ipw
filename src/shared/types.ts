export type ProjectType = 'engineering' | 'gov_it' | 'hybrid'
export type ProduceType = 'upload' | 'template'
export type FillStatus = 'empty' | 'draft' | 'complete' | 'error'
export type PrintStatus = 'unprinted' | 'printed'
export type Importance = 'important' | 'normal' | 'general'
export type FieldScope = 'project' | 'item'
export type EditorKernel = 'form-preview' | 'onlyoffice'

/** ADR-5: v1 ships the fallback form+preview kernel. OnlyOffice is a swap stub. */
export const ACTIVE_EDITOR_KERNEL: EditorKernel = 'form-preview'

export const PROJECT_TYPE_LABELS: Record<ProjectType, string> = {
  engineering: '普通工程',
  gov_it: '政务信息化',
  hybrid: '混合（工程 + 政务信息化）'
}

export const FILL_STATUS_LABELS: Record<FillStatus, string> = {
  empty: '空白',
  draft: '草稿',
  complete: '已齐',
  error: '异常'
}

export const PRINT_STATUS_LABELS: Record<PrintStatus, string> = {
  unprinted: '未打印',
  printed: '已打印'
}

export const IMPORTANCE_LABELS: Record<Importance, string> = {
  important: '重要',
  normal: '普通',
  general: '一般'
}

export const PRODUCE_TYPE_LABELS: Record<ProduceType, string> = {
  upload: '上传',
  template: '模板填报'
}

export interface FieldDef {
  key: string
  label: string
  scope: FieldScope
  required?: boolean
  multiline?: boolean
  placeholder?: string
}

export interface ProjectInput {
  name: string
  type: ProjectType
  owner: string
  supervisor: string
  contractor: string
  contract_no: string
  phase: string
  doc_no: string
  location?: string
  date?: string
}

export interface Project extends ProjectInput {
  id: string
  fields: Record<string, string>
  createdAt: string
  updatedAt: string
  openedAt: string
  rootDir: string
}

export interface ProjectSummary {
  id: string
  name: string
  type: ProjectType
  contract_no: string
  openedAt: string
  updatedAt: string
  rootDir: string
}

export interface CatalogVolume {
  id: string
  code: string
  title: string
  folder: string
  appliesTo: ProjectType[]
}

export interface CatalogItem {
  code: string
  title: string
  volumeId: string
  produceType: ProduceType
  required: boolean
  appliesTo: ProjectType[]
  importance: Importance
  templateFile?: string
  fields?: FieldDef[]
  stubNote?: string
}

export interface UploadRecord {
  id: string
  originalName: string
  storedPath: string
  createdAt: string
}

export interface ItemRecord {
  editStatus: FillStatus
  printStatus: PrintStatus
  overrides: Record<string, string>
  contentFingerprint: string
  lastPrintedFingerprint: string
  lastPrintedAt: string | null
  residualKeys: string[]
  fillError: string | null
  filledPath: string | null
  previewPath: string | null
  uploads: UploadRecord[]
  notes: string
  updatedAt: string
}

export interface CatalogItemState {
  item: CatalogItem
  record: ItemRecord
}

export interface CatalogVolumeState {
  volume: CatalogVolume
  items: CatalogItemState[]
}

export interface ItemEditorState {
  pane: 'form' | 'upload'
  templateMissing: boolean
  item: CatalogItem
  record: ItemRecord
  mergedFields: Record<string, string>
  projectFields: Record<string, string>
  engineMessage?: string
}

export interface FillResult {
  ok: boolean
  itemCode: string
  filledPath?: string
  previewPath?: string
  residualKeys: string[]
  message: string
  engineMissing?: boolean
}

export interface FillVolumeResult {
  ok: boolean
  filled: number
  skipped: number
  failed: number
  results: FillResult[]
  message: string
}

export interface ExportCheck {
  ok: boolean
  blockers: Array<{ code: string; title: string; reason: string }>
  residualKeys: string[]
}

export interface ExportResult {
  path: string
  format: 'pdf' | 'docx'
  fallbackNote?: string
}

export interface PrintWarn {
  incomplete: boolean
  message?: string
}

export interface PrintResult {
  printed: boolean
  reason?: string
}

export interface FilePreview {
  kind: 'image' | 'text' | 'pdf' | 'other'
  dataUrl?: string
  text?: string
  name: string
}

export const FORM_MODE_BANNER = '当前为表单模式（编辑内核未就绪）'
