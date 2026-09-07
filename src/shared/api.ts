import type {
  DailyLog,
  DailyLogInput,
  ExportCheck,
  GenerateResult,
  ItemStatus,
  Project,
  ProjectInput,
  UploadRecord,
  WeeklyReportOptions,
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
}
