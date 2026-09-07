export type ViewId = 'projects' | 'catalog' | 'logs' | 'export'

const ITEMS: { id: ViewId; label: string; needProject?: boolean }[] = [
  { id: 'projects', label: '项目' },
  { id: 'catalog', label: '资料目录', needProject: true },
  { id: 'logs', label: '施工日志', needProject: true },
  { id: 'export', label: '出包', needProject: true }
]

export default function Sidebar(props: {
  view: ViewId
  onView: (id: ViewId) => void
  hasProject: boolean
  projectName?: string
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>验收到手</h1>
        <p>Acceptance Studio · M1</p>
      </div>
      <nav>
        {ITEMS.map((item) => (
          <button
            key={item.id}
            className={`nav-btn ${props.view === item.id ? 'active' : ''}`}
            disabled={item.needProject && !props.hasProject}
            onClick={() => props.onView(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="side-foot">
        {props.projectName ? `当前项目：${props.projectName}` : '请先创建项目'}
        <br />
        七卷目录组卷 · 本地 SQLite
      </div>
    </aside>
  )
}
