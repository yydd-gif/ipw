import type {
  CatalogVolumeState,
  ExportCheck,
  ExportResult,
  FilePreview,
  FillResult,
  FillVolumeResult,
  ItemEditorState,
  ItemRecord,
  PrintResult,
  PrintWarn,
  Project,
  ProjectInput,
  ProjectSummary
} from './types'

export interface StudioAPI {
  dataDir: () => Promise<string>
  listProjects: () => Promise<ProjectSummary[]>
  getProject: (id: string) => Promise<Project>
  createProject: (input: ProjectInput) => Promise<Project>
  updateProject: (id: string, patch: Partial<ProjectInput>) => Promise<Project>
  openProjectFile: () => Promise<Project | null>
  getCatalogState: (projectId: string) => Promise<CatalogVolumeState[]>
  getItemEditor: (projectId: string, itemCode: string) => Promise<ItemEditorState>
  saveItemFields: (
    projectId: string,
    itemCode: string,
    fields: Record<string, string>,
    as?: 'draft' | 'complete'
  ) => Promise<ItemRecord>
  uploadFiles: (projectId: string, itemCode: string) => Promise<ItemRecord>
  fillItem: (projectId: string, itemCode: string) => Promise<FillResult>
  fillVolume: (projectId: string) => Promise<FillVolumeResult>
  checkExport: (projectId: string, itemCode: string) => Promise<ExportCheck>
  exportItem: (projectId: string, itemCode: string) => Promise<ExportResult | null>
  printWarn: (projectId: string, itemCode: string) => Promise<PrintWarn>
  printPreview: (projectId: string, itemCode: string) => Promise<void>
  printItem: (projectId: string, itemCode: string) => Promise<PrintResult>
  previewFile: (storedPath: string) => Promise<FilePreview>
  revealInFolder: (filePath: string) => Promise<void>
  engineStatus: () => Promise<{ python: boolean; engine: boolean; message: string }>
}
