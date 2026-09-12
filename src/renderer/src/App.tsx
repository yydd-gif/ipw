import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CatalogVolumeState, Project, ProjectInput, ProjectSummary } from '@shared/types'
import { PROJECT_TYPE_LABELS } from '@shared/types'
import ProjectManager from './views/ProjectManager'
import EditorShell from './editor/EditorShell'

type ViewId = 'manager' | 'editor'

export default function App() {
  const [view, setView] = useState<ViewId>('manager')
  const [recents, setRecents] = useState<ProjectSummary[]>([])
  const [current, setCurrent] = useState<Project | null>(null)
  const [catalog, setCatalog] = useState<CatalogVolumeState[]>([])
  const [toast, setToast] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const notify = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 4200)
  }

  const refreshRecents = useCallback(async () => {
    setRecents(await window.studio.listProjects())
  }, [])

  const openProject = useCallback(
    async (id: string, nextView: ViewId = 'editor') => {
      const project = await window.studio.getProject(id)
      const cat = await window.studio.getCatalogState(project.id)
      setCurrent(project)
      setCatalog(cat)
      setView(nextView)
      await refreshRecents()
    },
    [refreshRecents]
  )

  useEffect(() => {
    void refreshRecents()
  }, [refreshRecents])

  const createProject = async (input: ProjectInput) => {
    setBusy(true)
    try {
      const created = await window.studio.createProject(input)
      notify('项目已创建')
      await openProject(created.id, 'editor')
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const updateProject = async (patch: Partial<ProjectInput>) => {
    if (!current) return
    setBusy(true)
    try {
      const updated = await window.studio.updateProject(current.id, patch)
      setCurrent(updated)
      setCatalog(await window.studio.getCatalogState(updated.id))
      notify('项目信息已保存')
      await refreshRecents()
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const title = useMemo(() => {
    if (!current) return '项目台'
    return `${current.name} · ${PROJECT_TYPE_LABELS[current.type]}`
  }, [current])

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1>验收到手</h1>
          <p>备胎线 · 表单 + 只读预览</p>
        </div>
        <button className={`nav-btn ${view === 'manager' ? 'active' : ''}`} onClick={() => setView('manager')}>
          项目
        </button>
        <button
          className={`nav-btn ${view === 'editor' ? 'active' : ''}`}
          disabled={!current}
          onClick={() => setView('editor')}
        >
          资料编辑
        </button>
        <div className="side-foot">
          八册目录 · 离线 fill_engine
          <br />
          不是内嵌编辑 · 内核未就绪
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <h2>{title}</h2>
            <div className="muted">
              {current
                ? `合同 ${current.contract_no || '未填'} · ${current.owner || '建设单位未填'}`
                : '先新建或打开项目，再进入八册目录编辑'}
            </div>
          </div>
          <div className="muted">{busy ? '处理中…' : 'v1 · 不是内嵌编辑'}</div>
        </header>
        <main className={view === 'editor' ? 'content content-flush' : 'content'}>
          {view === 'manager' && (
            <ProjectManager
              recents={recents}
              current={current}
              onCreate={createProject}
              onOpenRecent={(id) => void openProject(id, 'editor')}
              onOpenFile={() => {
                void window.studio
                  .openProjectFile()
                  .then((project) => {
                    if (project) return openProject(project.id, 'editor')
                    return undefined
                  })
                  .catch((err: unknown) => notify(err instanceof Error ? err.message : String(err)))
              }}
              onSave={updateProject}
            />
          )}
          {view === 'editor' && current && (
            <EditorShell
              project={current}
              catalog={catalog}
              onRefresh={async () => {
                setCatalog(await window.studio.getCatalogState(current.id))
                setCurrent(await window.studio.getProject(current.id))
              }}
              notify={notify}
            />
          )}
        </main>
      </div>
      {toast ? <div className="toast">{toast}</div> : null}
    </div>
  )
}
