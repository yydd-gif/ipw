const STUBS = ['智能填写', '校核', '条文检索']

export default function AiRibbon() {
  return (
    <div className="ai-ribbon" title="离线 · dsh 未接入">
      {STUBS.map((label) => (
        <button key={label} className="btn ai-stub" disabled title="离线 · dsh 未接入">
          {label}
        </button>
      ))}
    </div>
  )
}
