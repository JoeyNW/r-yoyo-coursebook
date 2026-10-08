<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ApiError, api } from '../api'
import { formatDay } from '../format'
import { session } from '../session'
import type { HomeData, LessonResult } from '../types'

const router = useRouter()
const home = ref<HomeData | null>(null)
const message = ref('')
const savingId = ref<number | null>(null)

async function load() {
  if (!session.family) return
  home.value = await api<HomeData>(`/api/families/${session.family.id}/home`)
}

onMounted(load)

function percent(used: number, total: number) {
  if (!total) return 0
  return Math.max(0, Math.min(100, Math.round((used / total) * 100)))
}

async function quick(courseId: number, openCount: number) {
  message.value = ''
  if (openCount === 0) {
    message.value = '今天没有待打卡的课'
    return
  }
  if (openCount > 1) {
    await router.push({ name: 'calendar', query: { date: home.value?.today } })
    return
  }
  savingId.value = courseId
  try {
    const result = await api<LessonResult>(`/api/courses/${courseId}/quick-check-in`, {
      method: 'POST',
    })
    message.value = result.created
      ? `已记录，剩余 ${result.package.remaining_units} 节`
      : `这节课已经记过了，剩余 ${result.package.remaining_units} 节`
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.code === 'multiple_today') {
      await router.push({ name: 'calendar', query: { date: home.value?.today } })
      return
    }
    message.value = error instanceof Error ? error.message : '打卡失败'
  } finally {
    savingId.value = null
  }
}
</script>

<template>
  <main>
    <header class="top">
      <p class="muted">{{ home?.family.name }}</p>
      <h1>课时</h1>
      <p v-if="home" class="kicker">本月已上 {{ home.attended_this_month }} 节</p>
    </header>
    <p v-if="message" class="error">{{ message }}</p>
    <p v-if="home && home.courses.length === 0" class="card">
      还没有课程。
      <RouterLink v-if="session.family?.role === 'owner'" to="/courses/new">添加一门课</RouterLink>
    </p>
    <article v-for="course in home?.courses" :key="course.id" class="card">
      <RouterLink class="course-card" :to="`/courses/${course.id}`">
        <h2 :style="{ color: course.color }">{{ course.name }}</h2>
        <template v-if="course.package">
          <p class="remain">
            <strong>{{ course.package.remaining_units }}</strong>
            <span>剩余</span>
          </p>
          <p class="used">
            已用 {{ course.package.used_units }} / 总 {{ course.package.total_units }}
            · {{ course.package.title }}
          </p>
          <div class="bar">
            <span
              :style="{
                width: percent(course.package.used_units, course.package.total_units) + '%',
                background: course.color,
              }"
            ></span>
          </div>
          <p v-if="course.package.remaining_units === 0" class="warn">课时已用完</p>
          <p v-else-if="course.package.low_balance" class="warn">剩余不多</p>
        </template>
        <p v-else class="muted">还没有课包</p>
        <p v-if="course.next_lesson" class="muted">
          下次 {{ formatDay(course.next_lesson.local_date) }}
          {{ course.next_lesson.local_time }}
        </p>
        <p v-else class="muted">还没有排课</p>
      </RouterLink>
      <button
        v-if="course.package"
        class="btn primary"
        type="button"
        :disabled="savingId === course.id"
        @click="quick(course.id, course.today_open_count)"
      >
        已上课
      </button>
    </article>
    <section v-if="home && home.recent.length" class="card">
      <h2>最近记录</h2>
      <p v-for="item in home.recent" :key="item.id" class="item">
        {{ item.summary }}
        <span class="muted">{{ item.actor_name }}</span>
      </p>
    </section>
  </main>
</template>
