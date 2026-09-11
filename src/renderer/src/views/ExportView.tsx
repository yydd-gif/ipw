import {
  canOpenExportSaveDialog,
  exportBlockedMessage,
  formatConfirmReadyToast
} from '@shared/completeness'
import type { CatalogVolumeState, ExportCheck, Project } from '@shared/types'
import { StatusBadge } from '../components/StatusBadge'

export default function ExportView(props: {
  project: Project
  check: ExportCheck | null
  catalog: CatalogVolumeState[]
  onRefresh: () => Promise<ExportCheck | void> | void
  notify: (msg: string) => void
}) {
  const check = props.check
  return (
    <div className="grid-2">
      <section className="card">
        <h3 className="sec">导出验收资料包</h3>
        <p className="muted">
          整包 Zip 为下一轮能力。试用版主路径是左侧目录编辑 + 当前条目「导出 PDF / 打印预览 / 打印」。
        </p>
        {check ? (
          <p>
            必填 {check.required} 项，已确认 {check.confirmed}，免于提供 {check.waived}。
            {check.ok ? (
              <span className="badge confirmed">可以出包</span>
            ) : (
              <span className="badge empty">尚不能出包</span>
            )}
          </p>
        ) : null}
        {check && !check.ok ? (
          <div>
            <h4>未完成必填</h4>
            <ul>
              {check.blockers.map((b) => (
                <li className="blocker" key={b.code}>
                  {b.code} {b.title} — {b.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="actions">
          <button
            className="btn"
            onClick={async () => {
              // 雷神: confirmReady (batch n, incl. optional) → refresh catalog+ExportCheck → toast.
              // Header 「已确认」 stays required-only; toast never pretends n is that count.
              const n = await window.studio.confirmReady(props.project.id)
              const latest = (await props.onRefresh()) ?? (await window.studio.checkExport(props.project.id))
              props.notify(formatConfirmReadyToast(n, latest))
            }}
          >
            确认所有已有资料
          </button>
          <button
            className="btn primary"
            onClick={async () => {
              try {
                const latest = await window.studio.checkExport(props.project.id)
                if (!canOpenExportSaveDialog(latest)) {
                  props.notify(exportBlockedMessage(latest))
                  await props.onRefresh()
                  return
                }
                const result = await window.studio.exportZip(props.project.id)
                if (result) props.notify(`已导出：${result.path}`)
                await props.onRefresh()
              } catch (e) {
                props.notify(e instanceof Error ? e.message : String(e))
              }
            }}
          >
            导出验收资料包
          </button>
        </div>
        <div className="notice" style={{ marginTop: 16 }}>
          Word 使用系统默认程序打开。{/* GENOFFICE_EXTENSION_POINT */}后续可在主进程接入 GenOffice，不改变组卷流程。
        </div>
      </section>
      <section className="card">
        <h3 className="sec">分册完成情况</h3>
        {props.catalog.map((vol) => {
          const req = vol.items.filter((i) => i.item.required)
          const done = req.filter((i) => i.instance.status === 'confirmed' || i.instance.status === 'waived').length
          return (
            <div key={vol.volume.id} style={{ marginBottom: 14 }}>
              <strong>{vol.volume.title}</strong>
              <span className="muted"> 必填 {done}/{req.length}</span>
              <div>
                {vol.items
                  .filter((i) => i.item.required)
                  .map((i) => (
                    <div key={i.item.code} className="row" style={{ marginTop: 4 }}>
                      <span className="code">{i.item.code}</span>
                      <span>{i.item.title}</span>
                      <StatusBadge status={i.instance.status} />
                    </div>
                  ))}
              </div>
            </div>
          )
        })}
      </section>
    </div>
  )
}
