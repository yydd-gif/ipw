import { useMemo, useState } from 'react'
import type { CatalogItemState, CatalogVolumeState, ItemStatus, Project } from '@shared/types'
import { StatusBadge, ProduceBadge } from '../components/StatusBadge'

function PayloadForm(props: {
  item: CatalogItemState
  onSave: (payload: Record<string, unknown>) => void
}) {
  const code = props.item.item.code
  const [payload, setPayload] = useState<Record<string, unknown>>(props.item.instance.payload || {})
  const set = (key: string, value: unknown) => setPayload({ ...payload, [key]: value })

  if (!['2.7', '2.8', '6.2', '7.1', '7.2'].includes(code)) {
    return (
      <p className="muted">
        {props.item.item.produceType === 'template' || props.item.item.produceType === 'derived'
          ? '生成时将填入项目主数据。2.10 / 2.11 / 2.12 以施工日志为准。'
          : '本条目以上传归档为主。'}
      </p>
    )
  }

  if (code === '2.7') {
    return (
      <div className="grid-2">
        <label className="field">地点<input value={String(payload.location || '')} onChange={(e) => set('location', e.target.value)} /></label>
        <label className="field">序列号<input value={String(payload.serial || '')} onChange={(e) => set('serial', e.target.value)} /></label>
        <label className="field">设备名称<input value={String(payload.device_name || '')} onChange={(e) => set('device_name', e.target.value)} /></label>
        <label className="field">备注<input value={String(payload.remark || '')} onChange={(e) => set('remark', e.target.value)} /></label>
        {([
          ['packaging_ok', '包装完好'],
          ['appearance_ok', '外观无损'],
          ['accessories_ok', '配件齐全'],
          ['docs_ok', '资料齐全'],
          ['model_ok', '型号相符']
        ] as const).map(([k, label]) => (
          <label key={k} className="field">
            {label}
            <select value={payload[k] === false ? 'false' : 'true'} onChange={(e) => set(k, e.target.value === 'true')}>
              <option value="true">☑ 合格</option>
              <option value="false">☐ 不合格</option>
            </select>
          </label>
        ))}
        <div className="actions"><button className="btn" onClick={() => props.onSave(payload)}>保存字段</button></div>
      </div>
    )
  }

  if (code === '2.8') {
    const rows = (Array.isArray(payload.rows) ? payload.rows : [{}]) as Record<string, string>[]
    return (
      <div>
        {rows.map((row, i) => (
          <div className="grid-2" key={i} style={{ marginBottom: 8 }}>
            <label className="field">设备<input value={row.device_name || ''} onChange={(e) => {
              const next = rows.slice(); next[i] = { ...row, device_name: e.target.value }; set('rows', next)
            }} /></label>
            <label className="field">地点<input value={row.location || ''} onChange={(e) => {
              const next = rows.slice(); next[i] = { ...row, location: e.target.value }; set('rows', next)
            }} /></label>
            <label className="field">安装人<input value={row.installer || ''} onChange={(e) => {
              const next = rows.slice(); next[i] = { ...row, installer: e.target.value }; set('rows', next)
            }} /></label>
            <label className="field">日期<input value={row.date || ''} onChange={(e) => {
              const next = rows.slice(); next[i] = { ...row, date: e.target.value }; set('rows', next)
            }} /></label>
            <label className="field">结果<input value={row.result || ''} onChange={(e) => {
              const next = rows.slice(); next[i] = { ...row, result: e.target.value }; set('rows', next)
            }} /></label>
          </div>
        ))}
        <div className="actions">
          <button className="btn" onClick={() => set('rows', [...rows, {}])}>增加一行</button>
          <button className="btn primary" onClick={() => props.onSave({ rows })}>保存安装行</button>
        </div>
      </div>
    )
  }

  if (code === '6.2') {
    return (
      <div>
        <label className="field">基本信息<textarea value={String(payload.basic_info || '')} onChange={(e) => set('basic_info', e.target.value)} /></label>
        <label className="field">验收结论<textarea value={String(payload.conclusion || '')} onChange={(e) => set('conclusion', e.target.value)} /></label>
        <label className="field">质保条款<textarea value={String(payload.warranty || '')} onChange={(e) => set('warranty', e.target.value)} /></label>
        <div className="actions"><button className="btn primary" onClick={() => props.onSave(payload)}>保存</button></div>
      </div>
    )
  }

  if (code === '7.1') {
    return (
      <div>
        {([
          ['overview', '项目概况'],
          ['progress', '建设过程'],
          ['quality', '质量与安全'],
          ['issues', '问题与整改'],
          ['next', '运维与移交']
        ] as const).map(([k, label]) => (
          <label className="field" key={k}>
            {label}
            <textarea value={String(payload[k] || '')} onChange={(e) => set(k, e.target.value)} />
          </label>
        ))}
        <div className="actions"><button className="btn primary" onClick={() => props.onSave(payload)}>保存章节</button></div>
      </div>
    )
  }

  const hardware = (Array.isArray(payload.hardware)
    ? payload.hardware
    : [{ name: '', spec: '', brand: '', deploy: '', unit_price: '', qty: '1', total: '', note: '' }]) as Record<
    string,
    string
  >[]
  const software = (Array.isArray(payload.software)
    ? payload.software
    : [{ name: '', vendor: '', func: '', deploy: '', unit_price: '', qty: '1', total: '', note: '' }]) as Record<
    string,
    string
  >[]
  return (
    <div>
      <h4>硬件</h4>
      {hardware.map((row, i) => (
        <div className="grid-3" key={`h${i}`}>
          <input placeholder="名称" value={row.name || ''} onChange={(e) => { const n = hardware.slice(); n[i] = { ...row, name: e.target.value }; set('hardware', n) }} />
          <input placeholder="规格型号" value={row.spec || ''} onChange={(e) => { const n = hardware.slice(); n[i] = { ...row, spec: e.target.value }; set('hardware', n) }} />
          <input placeholder="品牌" value={row.brand || ''} onChange={(e) => { const n = hardware.slice(); n[i] = { ...row, brand: e.target.value }; set('hardware', n) }} />
          <input placeholder="部署位置" value={row.deploy || ''} onChange={(e) => { const n = hardware.slice(); n[i] = { ...row, deploy: e.target.value }; set('hardware', n) }} />
          <input placeholder="单价" value={row.unit_price || ''} onChange={(e) => { const n = hardware.slice(); n[i] = { ...row, unit_price: e.target.value }; set('hardware', n) }} />
          <input placeholder="数量" value={row.qty || ''} onChange={(e) => { const n = hardware.slice(); n[i] = { ...row, qty: e.target.value }; set('hardware', n) }} />
          <input placeholder="合计" value={row.total || ''} onChange={(e) => { const n = hardware.slice(); n[i] = { ...row, total: e.target.value }; set('hardware', n) }} />
          <input placeholder="备注" value={row.note || row.remark || ''} onChange={(e) => { const n = hardware.slice(); n[i] = { ...row, note: e.target.value }; set('hardware', n) }} />
        </div>
      ))}
      <button className="btn" onClick={() => set('hardware', [...hardware, { name: '', spec: '', brand: '', deploy: '', unit_price: '', qty: '1', total: '', note: '' }])}>增加硬件</button>
      <h4>软件</h4>
      {software.map((row, i) => (
        <div className="grid-3" key={`s${i}`}>
          <input placeholder="名称" value={row.name || ''} onChange={(e) => { const n = software.slice(); n[i] = { ...row, name: e.target.value }; set('software', n) }} />
          <input placeholder="厂商" value={row.vendor || row.version || ''} onChange={(e) => { const n = software.slice(); n[i] = { ...row, vendor: e.target.value }; set('software', n) }} />
          <input placeholder="功能" value={row.func || row.license || ''} onChange={(e) => { const n = software.slice(); n[i] = { ...row, func: e.target.value }; set('software', n) }} />
          <input placeholder="部署位置" value={row.deploy || ''} onChange={(e) => { const n = software.slice(); n[i] = { ...row, deploy: e.target.value }; set('software', n) }} />
          <input placeholder="单价" value={row.unit_price || ''} onChange={(e) => { const n = software.slice(); n[i] = { ...row, unit_price: e.target.value }; set('software', n) }} />
          <input placeholder="数量" value={row.qty || ''} onChange={(e) => { const n = software.slice(); n[i] = { ...row, qty: e.target.value }; set('software', n) }} />
          <input placeholder="备注" value={row.note || row.remark || ''} onChange={(e) => { const n = software.slice(); n[i] = { ...row, note: e.target.value }; set('software', n) }} />
        </div>
      ))}
      <div className="actions">
        <button className="btn" onClick={() => set('software', [...software, { name: '', vendor: '', func: '', deploy: '', unit_price: '', qty: '1', total: '', note: '' }])}>增加软件</button>
        <button className="btn primary" onClick={() => props.onSave({ hardware, software })}>保存清单</button>
      </div>
    </div>
  )
}

export default function CatalogView(props: {
  project: Project
  catalog: CatalogVolumeState[]
  onRefresh: () => Promise<void> | void
  notify: (msg: string) => void
}) {
  const [sel, setSel] = useState<string | null>(null)
  const selected = useMemo(() => {
    for (const vol of props.catalog) {
      const found = vol.items.find((i) => i.item.code === sel)
      if (found) return found
    }
    return props.catalog[0]?.items[0] ?? null
  }, [props.catalog, sel])

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn()
      props.notify(ok)
      await props.onRefresh()
    } catch (e) {
      props.notify(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="catalog">
      <div className="card tree">
        {props.catalog.map((vol) => (
          <div className="volume" key={vol.volume.id}>
            <div className="volume-h">{vol.volume.folder}</div>
            {vol.items.map((entry) => (
              <div
                key={entry.item.code}
                className={`item-row ${selected?.item.code === entry.item.code ? 'sel' : ''}`}
                onClick={() => setSel(entry.item.code)}
              >
                <span className="code">{entry.item.code}</span>
                <span>
                  {entry.item.title}
                  {entry.item.required ? <span className="badge req">必填</span> : <span className="badge opt">选填</span>}
                  {entry.item.stubNote ? <span className="badge waived">{entry.item.stubNote}</span> : null}
                </span>
                <StatusBadge status={entry.instance.status} />
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="card">
        {selected ? (
          <>
            <h3 className="sec">
              {selected.item.code} {selected.item.title}
            </h3>
            <div className="row" style={{ marginBottom: 12 }}>
              <ProduceBadge type={selected.item.produceType} />
              <StatusBadge status={selected.instance.status} />
              {selected.item.required ? <span className="badge req">必填</span> : <span className="badge opt">选填</span>}
            </div>
            {selected.item.stubNote ? (
              <div className="notice">本条目为占位：{selected.item.stubNote}。可生成说明性 Word 稿后确认。</div>
            ) : null}
            <p className="muted">
              产出方式：{selected.item.produceType === 'upload' ? '上传原件/扫描件' : selected.item.produceType === 'derived' ? '由施工日志或后续模块派生' : 'Word 模板填报'}
            </p>
            <PayloadForm
              key={selected.item.code + selected.instance.updated_at}
              item={selected}
              onSave={(payload) =>
                run(
                  () => window.studio.updateItemPayload(props.project.id, selected.item.code, payload),
                  '字段已保存'
                )
              }
            />
            <div className="actions">
              {selected.item.produceType === 'upload' ? (
                <button
                  className="btn primary"
                  onClick={() =>
                    run(
                      () => window.studio.uploadFiles(props.project.id, selected.item.code),
                      '已归档上传文件'
                    )
                  }
                >
                  上传资料
                </button>
              ) : (
                <button
                  className="btn primary"
                  onClick={() =>
                    run(
                      () => window.studio.generateDocument(props.project.id, selected.item.code),
                      '已生成 Word，并用系统默认程序打开'
                    )
                  }
                >
                  生成 Word
                </button>
              )}
              {selected.instance.generated_path ? (
                <button className="btn" onClick={() => window.studio.openPath(selected.instance.generated_path!)}>
                  打开已生成文件
                </button>
              ) : null}
              <select
                value={selected.instance.status}
                onChange={(e) =>
                  run(
                    () =>
                      window.studio.setItemStatus(
                        props.project.id,
                        selected.item.code,
                        e.target.value as ItemStatus
                      ),
                    '状态已更新'
                  )
                }
              >
                <option value="empty">未开始</option>
                <option value="draft">草稿</option>
                <option value="confirmed">已确认</option>
                <option value="waived">免于提供</option>
              </select>
            </div>
            {selected.uploads.length > 0 ? (
              <div style={{ marginTop: 16 }}>
                <h4>已上传</h4>
                <ul>
                  {selected.uploads.map((u) => (
                    <li key={u.id}>
                      <button className="btn ghost" onClick={() => window.studio.revealInFolder(u.stored_path)}>
                        {u.original_name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : (
          <p className="muted">选择左侧目录条目</p>
        )}
      </div>
    </div>
  )
}
