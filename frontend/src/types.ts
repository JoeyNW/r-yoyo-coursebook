export interface User {
  id: number
  display_name: string
  login_name: string
}

export interface Family {
  id: number
  name: string
  role: 'owner' | 'member'
}

export interface Me {
  user: User
  families: Family[]
}

export interface PackageBalance {
  id: number
  title: string
  total_units: number
  used_units: number
  remaining_units: number
  low_balance: boolean
}

export interface Slot {
  local_date: string
  local_time: string
}

export interface HomeCourse {
  id: number
  name: string
  color: string
  active: boolean
  package: PackageBalance | null
  next_lesson: Slot | null
  today_open_count: number
}

export interface AuditItem {
  id: number
  action: string
  summary: string
  created_at: string
  actor_name: string
}

export interface HomeData {
  family: Family
  today: string
  attended_this_month: number
  courses: HomeCourse[]
  recent: AuditItem[]
}

export interface CalendarItem {
  course_id: number
  course_name: string
  color: string
  local_time: string
  state: 'scheduled' | 'attended' | 'leave' | 'canceled'
  lesson_id: number | null
  source: 'planned' | 'manual' | null
  consumed_units: number
  notes: string
}

export interface CalendarDay {
  date: string
  items: CalendarItem[]
}

export interface Schedule {
  id: number
  weekday: number
  local_time: string
  effective_from: string
  effective_to: string | null
  active_now: boolean
}

export interface PackageDetail extends PackageBalance {
  opening_consumed_units: number
  start_date: string | null
  expiry_date: string | null
  notes: string
  is_current: boolean
}

export interface LessonItem {
  id: number
  course_id: number
  package_id: number
  local_date: string
  local_time: string
  source: 'planned' | 'manual'
  status: 'attended' | 'leave' | 'canceled'
  consumed_units: number
  notes: string
  voided_at: string | null
  actor_name: string
}

export interface CourseDetail {
  id: number
  family_id: number
  name: string
  color: string
  teacher: string
  location: string
  notes: string
  active: boolean
  role: 'owner' | 'member'
  schedules: Schedule[]
  packages: PackageDetail[]
  lessons: LessonItem[]
}

export interface CourseBrief {
  id: number
  name: string
  color: string
  active: boolean
}

export interface Member {
  user_id: number
  display_name: string
  role: 'owner' | 'member'
  joined_at: string
}

export interface LessonResult {
  created: boolean
  lesson: LessonItem
  package: PackageBalance
}
