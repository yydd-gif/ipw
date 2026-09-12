import type {
  DailyLog,
  DailyLogInput,
  EditorDocumentState,
  ExportCheck,
  FilePreview,
  GenerateResult,
  ItemStatus,
  PdfExportResult,
  PrintResult,
  Project,
  ProjectInput,
  TableDocument,
  UploadRecord,
  WeeklyReportOptions,
  CatalogInstance,
  CatalogVolumeState
} from './types'

export interface StudioAPI {
  dataDir: () => Promise<string>
  listProjects: () => Promise<Project[]>
  getProject: (id: string) => Promise<Project>
  createProject: (input: ProjectInput) => Promise<Project>
  updateProject: (id: string, patch: Partial<ProjectInput>) => Promise<Project>
  listLogs: (projectId: string) => Promise<DailyLog[]>
  saveLog: (input: DailyLogInput & { id?: string }) => Promise<DailyLog>
  deleteLog: (id: string) => Promise<void>
  getCatalogState: (projectId: string) => Promise<CatalogVolumeState[]>
  setItemStatus: (
    projectId: string,
    itemCode: string,
    status: ItemStatus,
    notes?: string
  ) => Promise<unknown>
  updateItemPayload: (
    projectId: string,
    itemCode: string,
    payload: Record<string, unknown>
  ) => Promise<unknown>
  uploadFiles: (projectId: string, itemCode: string) => Promise<UploadRecord[]>
  generateDocument: (
    projectId: string,
    itemCode: string,
    extra?: { weekly?: WeeklyReportOptions }
  ) => Promise<GenerateResult>
  generateWeeklyReport: (
    projectId: string,
    options?: Partial<WeeklyReportOptions>
  ) => Promise<GenerateResult>
  generateMonthlyReport: (
    projectId: string,
    options?: Partial<WeeklyReportOptions>
  ) => Promise<GenerateResult>
  checkExport: (projectId: string) => Promise<ExportCheck>
  confirmReady: (projectId: string) => Promise<number>
  exportZip: (projectId: string) => Promise<{ path: string; check: ExportCheck } | null>
  openPath: (filePath: string) => Promise<void>
  revealInFolder: (filePath: string) => Promise<void>
  getEditorDocument: (projectId: string, itemCode: string) => Promise<EditorDocumentState>
  saveEditorDocument: (
    projectId: string,
    itemCode: string,
    document: TableDocument,
    as?: 'draft' | 'ready'
  ) => Promise<CatalogInstance>
  markItemPrinted: (projectId: string, itemCode: string, fingerprint?: string) => Promise<CatalogInstance>
  exportItemPdf: (
    projectId: string,
    itemCode: string,
    document?: TableDocument | null
  ) => Promise<PdfExportResult | null>
  printPreview: (projectId: string, itemCode: string, document?: TableDocument | null) => Promise<void>
  printItem: (
    projectId: string,
    itemCode: string,
    document?: TableDocument | null
  ) => Promise<PrintResult>
  previewUpload: (storedPath: string) => Promise<FilePreview>
}
