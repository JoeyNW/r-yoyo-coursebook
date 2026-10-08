const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export function weekdayLabel(weekday: number): string {
  return WEEKDAYS[weekday] ?? ''
}

export function todayShanghai(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

export function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day + days))
  return date.toISOString().slice(0, 10)
}

export function monthStart(iso = todayShanghai()): string {
  return `${iso.slice(0, 7)}-01`
}

export function formatStamp(iso: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(iso))
}

export function formatDay(iso: string): string {
  const date = new Date(`${iso}T12:00:00+08:00`)
  const week = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    weekday: 'short',
  }).format(date)
  const [, month, day] = iso.split('-')
  return `${Number(month)}月${Number(day)}日 ${week}`
}

export function stateLabel(state: string, source: string | null): string {
  if (source === 'manual' && state === 'attended') {
    return '补课'
  }
  if (state === 'scheduled') return '计划'
  if (state === 'attended') return '已上'
  if (state === 'leave') return '请假'
  if (state === 'canceled') return '取消'
  return state
}

export function monthGrid(year: number, month: number): string[] {
  const first = new Date(Date.UTC(year, month - 1, 1))
  const mondayIndex = (first.getUTCDay() + 6) % 7
  const start = new Date(Date.UTC(year, month - 1, 1 - mondayIndex))
  const dates: string[] = []
  for (let index = 0; index < 42; index += 1) {
    const day = new Date(start)
    day.setUTCDate(start.getUTCDate() + index)
    dates.push(day.toISOString().slice(0, 10))
  }
  return dates
}

export function roleLabel(role: string): string {
  return role === 'owner' ? '创建者' : '家人'
}
