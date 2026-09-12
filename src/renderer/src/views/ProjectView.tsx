import { useState } from 'react'
import type { Project, ProjectInput, ProjectType } from '@shared/types'
import { PROJECT_TYPE_LABELS } from '@shared/types'

const EMPTY: ProjectInput = {
  name: '',
  type: 'hybrid',
  owner: '',
  supervisor: '',
  contractor: '',
  contract_no: '',
  phase: '',
  doc_no: ''
}

function Form(props: {
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
          <input value={v.name} onChange={(e) => set({ name: e.target.value })} placeholder="例如：某某政务云机房改造" />
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
          <input value={v.phase} onChange={(e) => set({ phase: e.target.value })} placeholder="施工 / 试运行 / 验收" />
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
      <p className="muted" style={{ marginTop: 12 }}>
        混合类型会同时启用工程类条目（2.1–2.5 开工报审/授权/施工组织方案等）与政务信息化条目（第 5、7 分册）。第 5 / 7 分册仅政务信息化与混合项目可见。
      </p>
    </div>
  )
}

export default function ProjectView(props: {
  projects: Project[]
  currentId: string | null
  current: Project | null
  onSelect: (id: string) => void
  onCreate: (input: ProjectInput) => void
  onSave: (patch: Partial<ProjectInput>) => void
}) {
  const [draft, setDraft] = useState<ProjectInput>(EMPTY)
  const [edit, setEdit] = useState<ProjectInput | null>(null)

  return (
    <div className="grid-2">
      <section>
        <h3 className="sec">项目列表</h3>
        <div className="project-list">
          {props.projects.length === 0 ? (
            <div className="card muted">还没有项目。右侧向导可新建混合型项目。</div>
          ) : (
            props.projects.map((p) => (
              <div
                key={p.id}
                className={`project-item ${p.id === props.currentId ? 'active' : ''}`}
                onClick={() => {
                  props.onSelect(p.id)
                  setEdit({
                    name: p.name,
                    type: p.type,
                    owner: p.owner,
                    supervisor: p.supervisor,
                    contractor: p.contractor,
                    contract_no: p.contract_no,
                    phase: p.phase,
                    doc_no: p.doc_no
                  })
                }}
              >
                <div>
                  <strong>{p.name}</strong>
                  <div className="muted">{PROJECT_TYPE_LABELS[p.type]} · {p.contract_no || '无合同号'}</div>
                </div>
                <span className="badge empty">{p.phase || '未填阶段'}</span>
              </div>
            ))
          )}
        </div>
        {props.current && edit ? (
          <div style={{ marginTop: 18 }}>
            <h3 className="sec">编辑当前项目</h3>
            <Form value={edit} onChange={setEdit} submitLabel="保存主数据" onSubmit={() => props.onSave(edit)} />
          </div>
        ) : null}
      </section>
      <section>
        <h3 className="sec">新建项目向导</h3>
        <Form
          value={draft}
          onChange={setDraft}
          submitLabel="创建项目"
          onSubmit={() => {
            props.onCreate(draft)
            setDraft(EMPTY)
          }}
        />
      </section>
    </div>
  )
}
