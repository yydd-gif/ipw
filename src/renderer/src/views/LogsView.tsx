import { useEffect, useMemo, useState } from 'react'
import type { DailyLog, Project } from '@shared/types'

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

const EMPTY = {
  date: today(),
  weather: '晴',
  location: '',
  work_done: '',
  qs_check: '',
  crew_count: 8,
  issues: '',
  coordination: ''
}

export default function LogsView(props: {
  project: Project
  logs: DailyLog[]
  onRefresh: () => Promise<void> | void
  notify: (msg: string) => void
}) {
  const [form, setForm] = useState({ ...EMPTY, location: props.project.phase })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [weekly, setWeekly] = useState({
    period_start: props.logs[0]?.date || today(),
    period_end: props.logs[props.logs.length - 1]?.date || today(),
    undone: '',
    plan: '下周继续按计划施工并整理验收资料。'
  })

  useEffect(() => {
    if (!props.logs.length) return
    const start = props.logs[0]!.date
    const end = props.logs[props.logs.length - 1]!.date
    setWeekly((w) => {
      if (w.period_start <= start && w.period_end >= end) return w
      if (w.undone || (w.plan && w.plan !== '下周继续按计划施工并整理验收资料。')) {
        return { ...w, period_start: start < w.period_start ? start : w.period_start, period_end: end > w.period_end ? end : w.period_end }
      }
      return { ...w, period_start: start, period_end: end }
    })
  }, [props.logs])

  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })

  const save = async () => {
    try {
      await window.studio.saveLog({
        ...form,
        project_id: props.project.id,
        id: editingId ?? undefined,
        crew_count: Number(form.crew_count) || 0
      })
      props.notify(editingId ? '日志已更新' : '日志已保存')
      setEditingId(null)
      setForm({ ...EMPTY, location: form.location })
      await props.onRefresh()
    } catch (e) {
      props.notify(e instanceof Error ? e.message : String(e))
    }
  }

  const periodLogs = useMemo(
    () => props.logs.filter((l) => l.date >= weekly.period_start && l.date <= weekly.period_end),
    [props.logs, weekly]
  )

  return (
    <div className="split-logs">
      <section className="card">
        <h3 className="sec">{editingId ? '编辑施工日志' : '新建施工日志'}</h3>
        <div className="grid-2">
          <label className="field">日期<input type="date" value={form.date} onChange={(e) => set({ date: e.target.value })} /></label>
          <label className="field">天气<input value={form.weather} onChange={(e) => set({ weather: e.target.value })} /></label>
          <label className="field">地点<input value={form.location} onChange={(e) => set({ location: e.target.value })} /></label>
          <label className="field">作业人数<input type="number" value={form.crew_count} onChange={(e) => set({ crew_count: Number(e.target.value) })} /></label>
        </div>
        <label className="field">完成工作<textarea value={form.work_done} onChange={(e) => set({ work_done: e.target.value })} /></label>
        <label className="field">质检情况<textarea value={form.qs_check} onChange={(e) => set({ qs_check: e.target.value })} /></label>
        <label className="field">存在问题<textarea value={form.issues} onChange={(e) => set({ issues: e.target.value })} /></label>
        <label className="field">协调事项<textarea value={form.coordination} onChange={(e) => set({ coordination: e.target.value })} /></label>
        <div className="actions">
          <button className="btn primary" onClick={() => void save()}>保存日志</button>
          {editingId ? (
            <button className="btn" onClick={() => { setEditingId(null); setForm({ ...EMPTY, location: props.project.phase }) }}>取消编辑</button>
          ) : null}
        </div>

        <h3 className="sec" style={{ marginTop: 22 }}>已记录 {props.logs.length} 条</h3>
        <table className="data">
          <thead>
            <tr>
              <th>日期</th>
              <th>天气</th>
              <th>完成工作</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {props.logs.map((log) => (
              <tr key={log.id} className={editingId === log.id ? 'sel' : ''}>
                <td>{log.date}</td>
                <td>{log.weather}</td>
                <td>{log.work_done}</td>
                <td>
                  <button className="btn ghost" onClick={() => { setEditingId(log.id); setForm(log) }}>编辑</button>
                  <button
                    className="btn ghost"
                    onClick={async () => {
                      await window.studio.deleteLog(log.id)
                      await props.onRefresh()
                    }}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3 className="sec">由日志生成报告</h3>
        <p className="muted">演示路径：写入不少于 3 条施工日志 → 生成 2.12 项目周报 → 再生成 2.10 施工日志 Word。</p>
        <div className="grid-2">
          <label className="field">周期开始<input type="date" value={weekly.period_start} onChange={(e) => setWeekly({ ...weekly, period_start: e.target.value })} /></label>
          <label className="field">周期结束<input type="date" value={weekly.period_end} onChange={(e) => setWeekly({ ...weekly, period_end: e.target.value })} /></label>
        </div>
        <p className="muted">本周期日志 {periodLogs.length} 条，完成工作将自动汇总进周报/月报。</p>
        <label className="field">未完事项<textarea value={weekly.undone} onChange={(e) => setWeekly({ ...weekly, undone: e.target.value })} /></label>
        <label className="field">下期计划<textarea value={weekly.plan} onChange={(e) => setWeekly({ ...weekly, plan: e.target.value })} /></label>
        <div className="actions">
          <button
            className="btn primary"
            onClick={async () => {
              try {
                await window.studio.generateWeeklyReport(props.project.id, weekly)
                props.notify('已生成 2.12 项目周报')
                await props.onRefresh()
              } catch (e) {
                props.notify(e instanceof Error ? e.message : String(e))
              }
            }}
          >
            生成周报
          </button>
          <button
            className="btn"
            onClick={async () => {
              try {
                await window.studio.generateMonthlyReport(props.project.id, weekly)
                props.notify('已生成 2.11 项目月报')
                await props.onRefresh()
              } catch (e) {
                props.notify(e instanceof Error ? e.message : String(e))
              }
            }}
          >
            生成月报
          </button>
          <button
            className="btn good"
            onClick={async () => {
              try {
                await window.studio.generateDocument(props.project.id, '2.10')
                props.notify('已生成 2.10 施工日志 Word')
                await props.onRefresh()
              } catch (e) {
                props.notify(e instanceof Error ? e.message : String(e))
              }
            }}
          >
            导出 2.10 施工日志
          </button>
        </div>
      </section>
    </div>
  )
}
