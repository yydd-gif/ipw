export type ViewId = 'editor' | 'projects' | 'export' | 'logs'

const PRIMARY: { id: ViewId; label: string; needProject?: boolean }[] = [
  { id: 'editor', label: '资料编辑', needProject: true },
  { id: 'projects', label: '项目' }
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
        <p>试用版验收资料编辑器</p>
      </div>
      <nav>
        {PRIMARY.map((item) => (
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
        左树编辑 · 当前项打印
        <div className="next-round">下一轮</div>
        <button
          className={`nav-btn secondary ${props.view === 'export' ? 'active' : ''}`}
          disabled={!props.hasProject}
          onClick={() => props.onView('export')}
        >
          整包 zip
        </button>
        <button
          className={`nav-btn secondary ${props.view === 'logs' ? 'active' : ''}`}
          disabled={!props.hasProject}
          onClick={() => props.onView('logs')}
        >
          周月报 / 日志
        </button>
      </div>
    </aside>
  )
}
