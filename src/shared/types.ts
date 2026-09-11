export type ProjectType = 'engineering' | 'gov_it' | 'hybrid'
export type ProduceType = 'upload' | 'template' | 'derived'
export type ItemStatus = 'empty' | 'draft' | 'confirmed' | 'waived'
export type EditStatus = 'empty' | 'draft' | 'ready'
export type PrintStatus = 'unprinted' | 'printed'
export type Importance = 'important' | 'normal' | 'general'

export const PROJECT_TYPE_LABELS: Record<ProjectType, string> = {
  engineering: '普通工程',
  gov_it: '政务信息化',
  hybrid: '混合（工程 + 政务信息化）'
}

export const STATUS_LABELS: Record<ItemStatus, string> = {
  empty: '未开始',
  draft: '草稿',
  confirmed: '已确认',
  waived: '免于提供'
}

export const EDIT_STATUS_LABELS: Record<EditStatus, string> = {
  empty: '空白',
  draft: '草稿',
  ready: '已齐'
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
  template: '模板填报',
  derived: '由日志派生'
}

export interface Project {
  id: string
  name: string
  type: ProjectType
  owner: string
  supervisor: string
  contractor: string
  contract_no: string
  phase: string
  doc_no: string
  created_at: string
  updated_at: string
}

export type ProjectInput = Omit<Project, 'id' | 'created_at' | 'updated_at'>

export interface DailyLog {
  id: string
  project_id: string
  date: string
  weather: string
  location: string
  work_done: string
  qs_check: string
  crew_count: number
  issues: string
  coordination: string
  created_at: string
}

export type DailyLogInput = Omit<DailyLog, 'id' | 'created_at'>

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
  /** Shown for later-auto-generated stubs such as 7.4 / 7.5 */
  stubNote?: string
  templateFile?: string
}

export interface DocCell {
  text: string
  bold?: boolean
  align?: 'left' | 'center' | 'right'
  colSpan?: number
}

export interface DocParagraph {
  text: string
  bold?: boolean
  align?: 'left' | 'center' | 'right'
}

export interface DocTable {
  rows: DocCell[][]
}

export interface TableDocument {
  title?: string
  paragraphs: DocParagraph[]
  tables: DocTable[]
}

export interface CatalogInstance {
  id: string
  project_id: string
  item_code: string
  status: ItemStatus
  editStatus: EditStatus
  printStatus: PrintStatus
  contentFingerprint: string
  lastPrintedAt: string | null
  lastPrintedFingerprint: string
  payload: Record<string, unknown>
  generated_path: string | null
  notes: string
  updated_at: string
}

export interface UploadRecord {
  id: string
  project_id: string
  item_code: string
  original_name: string
  stored_path: string
  created_at: string
}

export interface CatalogItemState {
  item: CatalogItem
  instance: CatalogInstance
  uploads: UploadRecord[]
  complete: boolean
}

export interface CatalogVolumeState {
  volume: CatalogVolume
  items: CatalogItemState[]
}

export type EditorPane = 'doc' | 'upload'

export interface EditorDocumentState {
  pane: EditorPane
  templateMissing: boolean
  document: TableDocument | null
  item: CatalogItem
  instance: CatalogInstance
  uploads: UploadRecord[]
  message?: string
}

export interface FilePreview {
  kind: 'image' | 'text' | 'pdf' | 'other'
  dataUrl?: string
  text?: string
  name: string
}

export interface ExportBlocker {
  code: string
  title: string
  reason: string
}

export interface ExportCheck {
  ok: boolean
  blockers: ExportBlocker[]
  confirmed: number
  required: number
  waived: number
}

export interface WeeklyReportOptions {
  period_start: string
  period_end: string
  undone?: string
  issues?: string
  plan?: string
}

export interface GenerateResult {
  path: string
  itemCode: string
  opened?: boolean
  paths?: string[]
}

export interface PdfExportResult {
  path: string
  htmlPath?: string
}

export interface PrintResult {
  printed: boolean
  reason?: string
}

export function editStatusFrom(status: ItemStatus): EditStatus {
  if (status === 'confirmed' || status === 'waived') return 'ready'
  if (status === 'draft') return 'draft'
  return 'empty'
}
