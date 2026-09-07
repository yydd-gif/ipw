import type { DailyLog } from '../shared/types'

export function filterLogsByPeriod(logs: DailyLog[], start?: string, end?: string): DailyLog[] {
  if (!start && !end) return logs
  return logs.filter((log) => {
    if (start && log.date < start) return false
    if (end && log.date > end) return false
    return true
  })
}

export function aggregateLogs(logs: DailyLog[]): { done: string; issues: string } {
  const done = logs
    .filter((l) => l.work_done.trim())
    .map((l) => `【${l.date}】${l.work_done.trim()}`)
    .join('\n')
  const issues = logs
    .filter((l) => l.issues.trim())
    .map((l) => `【${l.date}】${l.issues.trim()}`)
    .join('\n')
  return {
    done: done || '（本期施工日志暂无完成工作记录）',
    issues: issues || '（本期未记录问题）'
  }
}

export function logsToTemplateRows(logs: DailyLog[]): Record<string, unknown>[] {
  return logs.map((log) => ({
    date: log.date,
    weather: log.weather,
    location: log.location,
    work_done: log.work_done,
    qs_check: log.qs_check,
    crew_count: String(log.crew_count ?? 0),
    issues: log.issues,
    coordination: log.coordination
  }))
}
