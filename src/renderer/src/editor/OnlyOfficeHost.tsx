/**
 * ONLYOFFICE_HOST_STUB
 *
 * Future swap: set ACTIVE_EDITOR_KERNEL = 'onlyoffice' in src/shared/types.ts
 * and mount the official editor here. v1 must not pretend WYSIWYG is ready.
 */
export default function OnlyOfficeHost() {
  return (
    <div className="card onlyoffice-stub">
      <h3 className="sec">OnlyOffice 内核未接入</h3>
      <p className="muted">
        ADR-5 当前走备胎线：上表单、下只读预览。此组件是 EditorHost 的交换位，后续嵌入 OnlyOffice 时替换本文件即可，不必改目录树 / 成册 /
        打印状态机。
      </p>
    </div>
  )
}
