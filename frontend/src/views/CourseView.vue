<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { addDays, monthStart, stateLabel, todayShanghai, weekdayLabel } from '../format'
import { session } from '../session'
import type { CourseDetail } from '../types'

const route = useRoute()
const router = useRouter()
const creating = computed(() => route.name === 'course-new')
const owner = computed(
  () => session.family?.role === 'owner' || detail.value?.role === 'owner',
)
const detail = ref<CourseDetail | null>(null)
const message = ref('')
const saving = ref(false)
const name = ref('')
const color = ref('#0f766e')
const teacher = ref('')
const location = ref('')
const notes = ref('')
const slots = ref([{ weekday: 0, local_time: '16:30' }])
const packageTitle = ref('第一期')
const totalUnits = ref<number | null>(null)
const opening = ref(0)
const effectiveOn = ref(addDays(todayShanghai(), 1))
const draftTimes = ref<Record<number, string>>({})

const colors = ['#0f766e', '#b45309', '#1d4ed8', '#be123c', '#6d28d9', '#3f6212']

async function load() {
  if (creating.value) {
    detail.value = null
    return
  }
  const id = Number(route.params.id)
  detail.value = await api<CourseDetail>(`/api/courses/${id}`)
  name.value = detail.value.name
  color.value = detail.value.color
  teacher.value = detail.value.teacher
  location.value = detail.value.location
  notes.value = detail.value.notes
  for (const schedule of detail.value.schedules) {
    draftTimes.value[schedule.id] = schedule.local_time
  }
}

onMounted(load)
watch(() => route.fullPath, load)

function addSlot() {
  slots.value.push({ weekday: 0, local_time: '' })
}

async function createCourse() {
  if (!session.family) return
  const schedules = slots.value.filter((slot) => slot.local_time)
  saving.value = true
  message.value = ''
  try {
    const created = await api<{ id: number }>(
      `/api/families/${session.family.id}/courses`,
      {
        method: 'POST',
        body: JSON.stringify({
          name: name.value,
          color: color.value,
          teacher: teacher.value,
          location: location.value,
          notes: notes.value,
          schedules: schedules.map((slot) => ({
            ...slot,
            effective_from: monthStart(),
          })),
        }),
      },
    )
    await router.replace(`/courses/${created.id}`)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function saveProfile() {
  if (!detail.value) return
  saving.value = true
  message.value = ''
  try {
    detail.value = await api<CourseDetail>(`/api/courses/${detail.value.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name: name.value,
        color: color.value,
        teacher: teacher.value,
        location: location.value,
        notes: notes.value,
        active: detail.value.active,
      }),
    })
    message.value = '已保存'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function toggleActive() {
  if (!detail.value) return
  detail.value = await api<CourseDetail>(`/api/courses/${detail.value.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ active: !detail.value.active }),
  })
}

async function addSchedule() {
  if (!detail.value) return
  const time = slots.value[0]?.local_time
  if (!time) {
    message.value = '请填写上课时间'
    return
  }
  detail.value = await api<CourseDetail>(`/api/courses/${detail.value.id}/schedules`, {
    method: 'POST',
    body: JSON.stringify({
      weekday: slots.value[0].weekday,
      local_time: time,
      effective_from: monthStart(),
    }),
  })
  message.value = '已增加上课时间'
}

async function replaceSlot(scheduleId: number, weekday: number, localTime: string) {
  if (!detail.value) return
  const start = effectiveOn.value || monthStart()
  detail.value = await api<CourseDetail>(`/api/schedules/${scheduleId}/replace`, {
    method: 'POST',
    body: JSON.stringify({
      weekday,
      local_time: localTime,
      effective_on: start,
    }),
  })
  message.value = '已改以后的课表，已打卡的记录不变'
}

async function endSlot(scheduleId: number) {
  if (!detail.value) return
  const today = new Date()
  const iso = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(today)
  detail.value = await api<CourseDetail>(`/api/schedules/${scheduleId}/end`, {
    method: 'POST',
    body: JSON.stringify({ last_date: iso }),
  })
}

async function createPackage() {
  if (!detail.value || totalUnits.value === null) return
  saving.value = true
  message.value = ''
  try {
    await api(`/api/courses/${detail.value.id}/packages`, {
      method: 'POST',
      body: JSON.stringify({
        title: packageTitle.value,
        total_units: totalUnits.value,
        opening_consumed_units: opening.value,
      }),
    })
    await load()
    totalUnits.value = null
    opening.value = 0
    message.value = '课包已添加'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '添加失败'
  } finally {
    saving.value = false
  }
}

async function makeCurrent(packageId: number) {
  if (!detail.value) return
  detail.value = await api<CourseDetail>(`/api/packages/${packageId}/make-current`, {
    method: 'POST',
  })
}

async function saveOpening(pkg: CourseDetail['packages'][number]) {
  if (!detail.value) return
  detail.value = await api<CourseDetail>(`/api/packages/${pkg.id}`, {
    method: 'PATCH',
    body: JSON.stringify({
      opening_consumed_units: pkg.opening_consumed_units,
      total_units: pkg.total_units,
      title: pkg.title,
    }),
  })
  message.value = '课包已更新'
}

async function voidLesson(lessonId: number) {
  if (!window.confirm('撤销后这节课的课时会加回去。')) return
  await api(`/api/lessons/${lessonId}/void`, {
    method: 'POST',
    body: JSON.stringify({ confirm: true }),
  })
  await load()
}
</script>

<template>
  <main>
    <header class="top">
      <h1>{{ creating ? '添加课程' : detail?.name || '课程' }}</h1>
    </header>
    <p v-if="message" class="error">{{ message }}</p>
    <form v-if="creating" class="card" @submit.prevent="createCourse">
      <label class="field">
        课程名
        <input v-model="name" required maxlength="40" />
      </label>
      <div class="actions">
        <button
          v-for="item in colors"
          :key="item"
          type="button"
          class="btn"
          :style="{ background: item }"
          @click="color = item"
        >
          {{ color === item ? '当前' : '颜色' }}
        </button>
      </div>
      <div v-for="(slot, index) in slots" :key="index" class="row">
        <label class="field">
          星期
          <select v-model.number="slot.weekday">
            <option v-for="day in 7" :key="day" :value="day - 1">
              {{ weekdayLabel(day - 1) }}
            </option>
          </select>
        </label>
        <label class="field">
          时间
          <input v-model="slot.local_time" type="time" />
        </label>
      </div>
      <button class="btn" type="button" @click="addSlot">再加一个上课时间</button>
      <label class="field">老师<input v-model="teacher" /></label>
      <label class="field">地点<input v-model="location" /></label>
      <button class="btn primary" :disabled="saving">保存课程</button>
    </form>

    <template v-else-if="detail">
      <section class="card">
        <p v-if="!detail.active" class="warn">这门课已停用，历史记录还在。</p>
        <form v-if="owner" @submit.prevent="saveProfile">
          <label class="field">课程名<input v-model="name" required /></label>
          <label class="field">老师<input v-model="teacher" /></label>
          <label class="field">地点<input v-model="location" /></label>
          <label class="field">备注<input v-model="notes" /></label>
          <button class="btn" :disabled="saving">保存资料</button>
        </form>
        <p v-else class="muted">{{ detail.teacher }} {{ detail.location }}</p>
        <button v-if="owner" class="btn ghost" type="button" @click="toggleActive">
          {{ detail.active ? '停用课程' : '重新启用' }}
        </button>
      </section>

      <section class="card">
        <h2>上课时间</h2>
        <article
          v-for="schedule in detail.schedules.filter((item) => item.active_now)"
          :key="schedule.id"
          class="item"
        >
          <p>{{ weekdayLabel(schedule.weekday) }} {{ schedule.local_time }}</p>
          <div v-if="owner" class="actions">
            <input v-model="draftTimes[schedule.id]" type="time" />
            <input v-model="effectiveOn" type="date" />
            <button
              class="btn"
              type="button"
              @click="replaceSlot(schedule.id, schedule.weekday, draftTimes[schedule.id] || schedule.local_time)"
            >
              从所选日期起改时间
            </button>
            <button class="btn" type="button" @click="endSlot(schedule.id)">
              上到今天
            </button>
          </div>
        </article>
        <form v-if="owner" @submit.prevent="addSchedule">
          <div class="row">
            <label class="field">
              星期
              <select v-model.number="slots[0].weekday">
                <option v-for="day in 7" :key="day" :value="day - 1">
                  {{ weekdayLabel(day - 1) }}
                </option>
              </select>
            </label>
            <label class="field">
              时间
              <input v-model="slots[0].local_time" type="time" />
            </label>
          </div>
          <button class="btn">增加时段</button>
        </form>
      </section>

      <section class="card">
        <h2>课包</h2>
        <article v-for="pkg in detail.packages" :key="pkg.id" class="item">
          <p>
            <strong>{{ pkg.title }}</strong>
            <span v-if="pkg.is_current"> · 当前</span>
          </p>
          <p>已用 {{ pkg.used_units }} / 总 {{ pkg.total_units }} / 剩余 {{ pkg.remaining_units }}</p>
          <p v-if="pkg.expiry_date" class="muted">到期 {{ pkg.expiry_date }}，过期仍可打卡</p>
          <label v-if="owner" class="field">
            启用前已用
            <input v-model.number="pkg.opening_consumed_units" type="number" min="0" />
          </label>
          <div v-if="owner" class="actions">
            <button class="btn" type="button" @click="saveOpening(pkg)">保存课包</button>
            <button
              v-if="!pkg.is_current"
              class="btn"
              type="button"
              @click="makeCurrent(pkg.id)"
            >
              设为当前课包
            </button>
          </div>
        </article>
        <form v-if="owner" @submit.prevent="createPackage">
          <label class="field">名称<input v-model="packageTitle" required /></label>
          <label class="field">
            购买节数
            <input v-model.number="totalUnits" type="number" min="1" required />
          </label>
          <label class="field">
            启用前已用
            <input v-model.number="opening" type="number" min="0" />
          </label>
          <button class="btn primary" :disabled="saving">添加课包</button>
        </form>
      </section>

      <section class="card">
        <h2>上课记录</h2>
        <p v-if="detail.lessons.length === 0" class="muted">还没有记录。</p>
        <article v-for="lesson in detail.lessons" :key="lesson.id" class="item">
          <p>
            {{ lesson.local_date }} {{ lesson.local_time }}
            {{ stateLabel(lesson.status, lesson.source) }}
            <span v-if="lesson.voided_at" class="muted">已撤销</span>
            <span v-else class="muted">扣 {{ lesson.consumed_units }}</span>
          </p>
          <p class="muted">{{ lesson.actor_name }}</p>
          <button
            v-if="!lesson.voided_at"
            class="btn danger"
            type="button"
            @click="voidLesson(lesson.id)"
          >
            撤销
          </button>
        </article>
      </section>
    </template>
  </main>
</template>
