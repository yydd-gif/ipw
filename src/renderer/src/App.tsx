import { useCallback, useEffect, useMemo, useState } from 'react'
import type {
  CatalogVolumeState,
  DailyLog,
  ExportCheck,
  Project,
  ProjectInput,
  ProjectType
} from '@shared/types'
import { PROJECT_TYPE_LABELS } from '@shared/types'
import Sidebar, { type ViewId } from './components/Sidebar'
import ProjectView from './views/ProjectView'
import CatalogView from './views/CatalogView'
import LogsView from './views/LogsView'
import ExportView from './views/ExportView'

export default function App() {
  const [view, setView] = useState<ViewId>('projects')
  const [projects, setProjects] = useState<Project[]>([])
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [logs, setLogs] = useState<DailyLog[]>([])
  const [catalog, setCatalog] = useState<CatalogVolumeState[]>([])
  const [check, setCheck] = useState<ExportCheck | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const current = useMemo(
    () => projects.find((p) => p.id === currentId) ?? null,
    [projects, currentId]
  )

  const notify = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 4200)
  }

  const wrap = useCallback(async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> => {
    setBusy(true)
    try {
      const result = await fn()
      if (ok) notify(ok)
      return result
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err))
      return undefined
    } finally {
      setBusy(false)
    }
  }, [])

  const refreshProjects = useCallback(async () => {
    const list = await window.studio.listProjects()
    setProjects(list)
    setCurrentId((id) => id ?? list[0]?.id ?? null)
  }, [])

  const refreshProjectData = useCallback(async (projectId: string) => {
    const [logRows, cat, exp] = await Promise.all([
      window.studio.listLogs(projectId),
      window.studio.getCatalogState(projectId),
      window.studio.checkExport(projectId)
    ])
    setLogs(logRows)
    setCatalog(cat)
    setCheck(exp)
  }, [])

  useEffect(() => {
    void refreshProjects()
  }, [refreshProjects])

  useEffect(() => {
    if (currentId) void refreshProjectData(currentId)
    else {
      setLogs([])
      setCatalog([])
      setCheck(null)
    }
  }, [currentId, refreshProjectData])

  const createProject = async (input: ProjectInput) => {
    const created = await wrap(() => window.studio.createProject(input), '项目已创建')
    if (created) {
      await refreshProjects()
      setCurrentId(created.id)
      setView('catalog')
    }
  }

  const updateProject = async (patch: Partial<ProjectInput>) => {
    if (!currentId) return
    await wrap(() => window.studio.updateProject(currentId, patch), '项目信息已保存')
    await refreshProjects()
    await refreshProjectData(currentId)
  }

  const selectProject = (id: string) => {
    setCurrentId(id)
    setView('catalog')
  }

  return (
    <div className="app">
      <Sidebar
        view={view}
        onView={setView}
        hasProject={Boolean(current)}
        projectName={current?.name}
      />
      <div className="workspace">
        <header className="topbar">
          <div>
            <h2>
              {current ? current.name : '未选择项目'}
              {current ? (
                <span className="muted"> · {PROJECT_TYPE_LABELS[current.type as ProjectType]}</span>
              ) : null}
            </h2>
            <div className="muted">
              {current
                ? `合同 ${current.contract_no || '未填'} · ${current.owner || '建设单位未填'}`
                : '先新建或打开一个项目，再填写目录与施工日志'}
            </div>
          </div>
          <div className="muted">{busy ? '处理中…' : '本地组卷 · M1'}</div>
        </header>
        <main className="content">
          {view === 'projects' && (
            <ProjectView
              projects={projects}
              currentId={currentId}
              onSelect={selectProject}
              onCreate={createProject}
              current={current}
              onSave={updateProject}
            />
          )}
          {view === 'catalog' && current && (
            <CatalogView
              project={current}
              catalog={catalog}
              onRefresh={() => refreshProjectData(current.id)}
              notify={notify}
            />
          )}
          {view === 'logs' && current && (
            <LogsView
              project={current}
              logs={logs}
              onRefresh={() => refreshProjectData(current.id)}
              notify={notify}
            />
          )}
          {view === 'export' && current && (
            <ExportView
              project={current}
              check={check}
              catalog={catalog}
              onRefresh={() => refreshProjectData(current.id)}
              notify={notify}
            />
          )}
        </main>
      </div>
      {toast ? <div className="toast">{toast}</div> : null}
    </div>
  )
}
