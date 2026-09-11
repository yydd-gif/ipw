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
import LogsView from './views/LogsView'
import ExportView from './views/ExportView'
import EditorShell from './editor/EditorShell'

export default function App() {
  const [view, setView] = useState<ViewId>('editor')
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

  const refreshProjectData = useCallback(async (projectId: string): Promise<ExportCheck> => {
    const [logRows, cat, exp] = await Promise.all([
      window.studio.listLogs(projectId),
      window.studio.getCatalogState(projectId),
      window.studio.checkExport(projectId)
    ])
    setLogs(logRows)
    setCatalog(cat)
    setCheck(exp)
    return exp
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
      setView('editor')
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
    setView('editor')
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
                : '先新建或打开一个项目，再在左侧目录中编辑条目'}
            </div>
          </div>
          <div className="muted">{busy ? '处理中…' : '试用 · 目录编辑 / 当前项打印'}</div>
        </header>
        <main className={view === 'editor' ? 'content content-flush' : 'content'}>
          {view === 'editor' && current && (
            <EditorShell
              project={current}
              catalog={catalog}
              onRefresh={async () => {
                await refreshProjectData(current.id)
              }}
              notify={notify}
            />
          )}
          {view === 'editor' && !current && (
            <div className="card">
              <h3 className="sec">开始验收资料编辑</h3>
              <p className="muted">还没有打开的项目。请到「项目」页新建或选择一个项目，应用会进入八册目录编辑器。</p>
              <div className="actions">
                <button className="btn primary" onClick={() => setView('projects')}>
                  前往项目
                </button>
              </div>
            </div>
          )}
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
          {view === 'logs' && current && (
            <LogsView
              project={current}
              logs={logs}
              onRefresh={async () => {
                await refreshProjectData(current.id)
              }}
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
