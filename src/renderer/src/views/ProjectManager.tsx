import { useEffect, useState } from 'react'
import type { Project, ProjectInput, ProjectSummary, ProjectType } from '@shared/types'
import { PROJECT_TYPE_LABELS } from '@shared/types'

const EMPTY: ProjectInput = {
  name: '',
  type: 'hybrid',
  owner: '',
  supervisor: '',
  contractor: '',
  contract_no: '',
  phase: '验收',
  doc_no: '',
  location: '',
  date: ''
}

function ProjectForm(props: {
  value: ProjectInput
  onChange: (next: ProjectInput) => void
  submitLabel: string
  onSubmit: () => void
}) {
  const v = props.value
  const set = (patch: Partial<ProjectInput>) => props.onChange({ ...v, ...patch })
  return (
    <div className="card">
      <div className="grid-2">
        <label className="field">
          项目名称
          <input
            value={v.name}
            onChange={(e) => set({ name: e.target.value })}
            placeholder="例如：某某政务云机房改造"
          />
        </label>
        <label className="field">
          项目类型
          <select value={v.type} onChange={(e) => set({ type: e.target.value as ProjectType })}>
            {(Object.keys(PROJECT_TYPE_LABELS) as ProjectType[]).map((k) => (
              <option key={k} value={k}>
                {PROJECT_TYPE_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          建设单位
          <input value={v.owner} onChange={(e) => set({ owner: e.target.value })} />
        </label>
        <label className="field">
          监理单位
          <input value={v.supervisor} onChange={(e) => set({ supervisor: e.target.value })} />
        </label>
        <label className="field">
          施工单位
          <input value={v.contractor} onChange={(e) => set({ contractor: e.target.value })} />
        </label>
        <label className="field">
          合同号
          <input value={v.contract_no} onChange={(e) => set({ contract_no: e.target.value })} />
        </label>
        <label className="field">
          阶段
          <input value={v.phase} onChange={(e) => set({ phase: e.target.value })} />
        </label>
        <label className="field">
          文号
          <input value={v.doc_no} onChange={(e) => set({ doc_no: e.target.value })} />
        </label>
      </div>
      <div className="actions">
        <button className="btn primary" onClick={props.onSubmit}>
          {props.submitLabel}
        </button>
      </div>
    </div>
  )
}

export default function ProjectManager(props: {
  recents: ProjectSummary[]
  current: Project | null
  onCreate: (input: ProjectInput) => void
  onOpenRecent: (id: string) => void
  onOpenFile: () => void
  onSave: (patch: Partial<ProjectInput>) => void
}) {
  const [draft, setDraft] = useState<ProjectInput>(EMPTY)
  const [edit, setEdit] = useState<ProjectInput | null>(null)

  useEffect(() => {
    setEdit(null)
  }, [props.current?.id])

  const currentEdit: ProjectInput | null = edit ??
    (props.current
      ? {
          name: props.current.name,
          type: props.current.type,
          owner: props.current.owner,
          supervisor: props.current.supervisor,
          contractor: props.current.contractor,
          contract_no: props.current.contract_no,
          phase: props.current.phase,
          doc_no: props.current.doc_no,
          location: props.current.location,
          date: props.current.date
        }
      : null)

  return (
    <div className="manager">
      <section>
        <div className="sec-row">
          <h3 className="sec">最近项目</h3>
          <button className="btn" onClick={props.onOpenFile}>
            打开 project.json
          </button>
        </div>
        <div className="project-list">
          {props.recents.length === 0 ? (
            <div className="card muted">还没有项目。右侧新建后会写入本机 userData。</div>
          ) : (
            props.recents.map((p) => (
              <div
                key={p.id}
                className={`project-item ${props.current?.id === p.id ? 'active' : ''}`}
                onClick={() => {
                  props.onOpenRecent(p.id)
                }}
              >
                <div>
                  <strong>{p.name}</strong>
                  <div className="muted">
                    {PROJECT_TYPE_LABELS[p.type]} · {p.contract_no || '无合同号'}
                  </div>
                </div>
                <span className="badge empty">打开</span>
              </div>
            ))
          )}
        </div>
        {props.current && currentEdit ? (
          <div style={{ marginTop: 18 }}>
            <h3 className="sec">当前项目主数据（写入 project.json）</h3>
            <ProjectForm
              value={currentEdit}
              onChange={setEdit}
              submitLabel="保存主数据"
              onSubmit={() => props.onSave(currentEdit)}
            />
          </div>
        ) : null}
      </section>
      <section>
        <h3 className="sec">新建项目</h3>
        <ProjectForm
          value={draft}
          onChange={setDraft}
          submitLabel="创建并进入编辑"
          onSubmit={() => {
            props.onCreate(draft)
            setDraft(EMPTY)
          }}
        />
        <p className="muted" style={{ marginTop: 12 }}>
          混合类型同时启用工程条目与政务信息化第 5 / 7 分册。项目落在 Electron userData，表单字段写入
          project.json，条目覆盖写入同文件 items。
        </p>
      </section>
    </div>
  )
}
