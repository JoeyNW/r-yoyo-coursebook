<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import {
  addDays,
  formatDay,
  monthGrid,
  stateLabel,
  todayShanghai,
} from '../format'
import { session } from '../session'
import type {
  CalendarDay,
  CalendarItem,
  CourseBrief,
  LessonResult,
} from '../types'

const route = useRoute()
const today = todayShanghai()
const cursor = ref(today.slice(0, 7))
const selected = ref(
  typeof route.query.date === 'string' ? route.query.date : today,
)
const days = ref<CalendarDay[]>([])
const courses = ref<CourseBrief[]>([])
const message = ref('')
const saving = ref(false)
const charge = ref(false)
const makeupTime = ref('16:00')
const makeupCourseId = ref<number | null>(null)
const voidId = ref<number | null>(null)

const year = computed(() => Number(cursor.value.slice(0, 4)))
const month = computed(() => Number(cursor.value.slice(5, 7)))
const dates = computed(() => monthGrid(year.value, month.value))
const byDate = computed(() => {
  const map = new Map<string, CalendarItem[]>()
  for (const day of days.value) map.set(day.date, day.items)
  return map
})
const selectedItems = computed(() => byDate.value.get(selected.value) ?? [])
const future = computed(() => selected.value > today)

async function load() {
  if (!session.family) return
  const grid = dates.value
  const body = await api<{ days: CalendarDay[] }>(
    `/api/families/${session.family.id}/calendar?start=${grid[0]}&end=${grid[41]}`,
  )
  days.value = body.days
  const list = await api<{ courses: CourseBrief[] }>(
    `/api/families/${session.family.id}/courses`,
  )
  courses.value = list.courses.filter((course) => course.active)
  if (makeupCourseId.value === null && courses.value[0]) {
    makeupCourseId.value = courses.value[0].id
  }
}

onMounted(load)
watch(cursor, load)

function shift(delta: number) {
  const date = new Date(Date.UTC(year.value, month.value - 1 + delta, 1))
  cursor.value = date.toISOString().slice(0, 7)
}

async function mark(item: CalendarItem, status: 'attended' | 'leave' | 'canceled') {
  saving.value = true
  message.value = ''
  try {
    const result = await api<LessonResult>('/api/lessons', {
      method: 'POST',
      body: JSON.stringify({
        course_id: item.course_id,
        local_date: selected.value,
        local_time: item.local_time,
        source: 'planned',
        status,
        charge: status === 'leave' ? charge.value : false,
      }),
    })
    message.value = result.created
      ? `已记录，剩余 ${result.package.remaining_units} 节`
      : `这节课已经记过了，剩余 ${result.package.remaining_units} 节`
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '操作失败'
  } finally {
    saving.value = false
  }
}

async function makeup() {
  if (!makeupCourseId.value) return
  saving.value = true
  message.value = ''
  try {
    const result = await api<LessonResult>('/api/lessons', {
      method: 'POST',
      body: JSON.stringify({
        course_id: makeupCourseId.value,
        local_date: selected.value,
        local_time: makeupTime.value,
        source: 'manual',
        status: 'attended',
        charge: false,
      }),
    })
    message.value = `补课已记录，剩余 ${result.package.remaining_units} 节`
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '操作失败'
  } finally {
    saving.value = false
  }
}

async function confirmVoid() {
  if (voidId.value === null) return
  saving.value = true
  message.value = ''
  try {
    const result = await api<LessonResult>(`/api/lessons/${voidId.value}/void`, {
      method: 'POST',
      body: JSON.stringify({ confirm: true }),
    })
    message.value = `已撤销，剩余 ${result.package.remaining_units} 节`
    voidId.value = null
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '撤销失败'
  } finally {
    saving.value = false
  }
}

async function chargeLeave(lessonId: number) {
  saving.value = true
  message.value = ''
  try {
    const result = await api<LessonResult>(`/api/lessons/${lessonId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'leave', charge: true, confirm: true }),
    })
    message.value = `已改为扣课，剩余 ${result.package.remaining_units} 节`
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '修改失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main>
    <header class="top row">
      <button class="btn ghost" type="button" @click="shift(-1)">上个月</button>
      <h1>{{ year }}年{{ month }}月</h1>
      <button class="btn ghost" type="button" @click="shift(1)">下个月</button>
    </header>
    <div class="grid">
      <span v-for="label in ['一', '二', '三', '四', '五', '六', '日']" :key="label" class="dow">
        {{ label }}
      </span>
      <button
        v-for="iso in dates"
        :key="iso"
        type="button"
        class="day"
        :class="{
          out: iso.slice(0, 7) !== cursor,
          today: iso === today,
          picked: iso === selected,
        }"
        @click="selected = iso"
      >
        <span>{{ Number(iso.slice(8)) }}</span>
        <span class="dots">
          <i
            v-for="(item, index) in (byDate.get(iso) || []).slice(0, 4)"
            :key="`${iso}-${index}`"
            :style="{ background: item.color }"
          ></i>
        </span>
      </button>
    </div>
    <section class="day-sheet">
      <h2>{{ formatDay(selected) }}</h2>
      <p v-if="message" class="error">{{ message }}</p>
      <p v-if="selectedItems.length === 0" class="muted">这一天没有课。</p>
      <article v-for="(item, index) in selectedItems" :key="`${item.local_time}-${index}`" class="item">
        <p>
          <strong :style="{ color: item.color }">{{ item.course_name }}</strong>
          {{ item.local_time }}
          {{ stateLabel(item.state, item.source) }}
          <span v-if="item.consumed_units" class="muted">扣 {{ item.consumed_units }} 课时</span>
        </p>
        <div v-if="item.state === 'scheduled'" class="actions">
          <button
            v-if="!future"
            class="btn primary"
            type="button"
            :disabled="saving"
            @click="mark(item, 'attended')"
          >
            已上课
          </button>
          <label class="check">
            <input v-model="charge" type="checkbox" />
            这次请假也扣课时
          </label>
          <button class="btn" type="button" :disabled="saving" @click="mark(item, 'leave')">
            请假
          </button>
          <button class="btn" type="button" :disabled="saving" @click="mark(item, 'canceled')">
            取消
          </button>
        </div>
        <div v-else class="actions">
          <button
            v-if="item.lesson_id && item.state === 'leave' && item.consumed_units === 0"
            class="btn"
            type="button"
            :disabled="saving"
            @click="chargeLeave(item.lesson_id)"
          >
            确认：这节请假扣 1 课时
          </button>
          <button
            v-if="item.lesson_id && voidId !== item.lesson_id"
            class="btn danger"
            type="button"
            @click="voidId = item.lesson_id"
          >
            撤销
          </button>
          <button
            v-if="voidId === item.lesson_id"
            class="btn danger"
            type="button"
            :disabled="saving"
            @click="confirmVoid"
          >
            确认撤销
          </button>
        </div>
      </article>
      <form v-if="!future && courses.length" class="item" @submit.prevent="makeup">
        <h2>临时补课</h2>
        <label class="field">
          课程
          <select v-model.number="makeupCourseId">
            <option v-for="course in courses" :key="course.id" :value="course.id">
              {{ course.name }}
            </option>
          </select>
        </label>
        <label class="field">
          时间
          <input v-model="makeupTime" type="time" required />
        </label>
        <button class="btn primary" :disabled="saving">记一节补课</button>
      </form>
    </section>
  </main>
</template>
