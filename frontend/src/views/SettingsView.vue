<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../api'
import { formatStamp, roleLabel } from '../format'
import { clearSession, session } from '../session'
import type { CourseBrief, Member } from '../types'

const router = useRouter()
const members = ref<Member[]>([])
const courses = ref<CourseBrief[]>([])
const invite = ref('')
const expires = ref('')
const message = ref('')

async function load() {
  if (!session.family) return
  const familyId = session.family.id
  const memberBody = await api<{ members: Member[] }>(
    `/api/families/${familyId}/members`,
  )
  members.value = memberBody.members
  const courseBody = await api<{ courses: CourseBrief[] }>(
    `/api/families/${familyId}/courses`,
  )
  courses.value = courseBody.courses
}

onMounted(load)

async function createInvite() {
  if (!session.family) return
  const body = await api<{ code: string; expires_at: string }>(
    `/api/families/${session.family.id}/invitations`,
    { method: 'POST' },
  )
  invite.value = body.code
  expires.value = body.expires_at
}

async function removeMember(userId: number) {
  if (!session.family) return
  if (!window.confirm('确定移出这位家人？')) return
  await api(`/api/families/${session.family.id}/members/${userId}`, {
    method: 'DELETE',
  })
  await load()
}

async function downloadExport() {
  if (!session.family) return
  const response = await fetch(`/api/families/${session.family.id}/export`, {
    credentials: 'include',
  })
  if (!response.ok) {
    message.value = '导出失败'
    return
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'yoyo-export.json'
  link.click()
  URL.revokeObjectURL(url)
}

async function logout() {
  await api('/api/auth/logout', { method: 'POST' })
  clearSession()
  await router.push('/login')
}
</script>

<template>
  <main>
    <header class="top">
      <h1>{{ session.family?.name }}</h1>
      <p class="muted">你是{{ roleLabel(session.family?.role || 'member') }}</p>
    </header>
    <section class="card">
      <h2>课程</h2>
      <RouterLink
        v-for="course in courses"
        :key="course.id"
        class="list-link"
        :to="`/courses/${course.id}`"
      >
        <span :style="{ color: course.color }">{{ course.name }}</span>
        <span class="muted">{{ course.active ? '' : '已停用' }}</span>
      </RouterLink>
      <RouterLink v-if="session.family?.role === 'owner'" class="btn primary" to="/courses/new">
        添加课程
      </RouterLink>
    </section>
    <section class="card">
      <h2>家人</h2>
      <p v-for="member in members" :key="member.user_id" class="item row">
        <span>{{ member.display_name }} · {{ roleLabel(member.role) }}</span>
        <button
          v-if="session.family?.role === 'owner' && member.role !== 'owner'"
          class="btn danger"
          type="button"
          @click="removeMember(member.user_id)"
        >
          移除
        </button>
      </p>
      <button
        v-if="session.family?.role === 'owner'"
        class="btn"
        type="button"
        @click="createInvite"
      >
        生成邀请码
      </button>
      <p v-if="invite">
        <code class="invite">{{ invite }}</code>
        <span class="muted">{{ formatStamp(expires) }} 前有效，只能用一次</span>
      </p>
    </section>
    <section class="card">
      <button class="btn" type="button" @click="downloadExport">导出 JSON</button>
      <button class="btn ghost" type="button" @click="logout">退出登录</button>
      <p v-if="message" class="error">{{ message }}</p>
    </section>
  </main>
</template>
