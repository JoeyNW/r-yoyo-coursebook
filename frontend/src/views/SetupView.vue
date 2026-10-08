<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { refreshSession } from '../session'

const router = useRouter()
const familyName = ref('')
const code = ref('')
const message = ref('')
const saving = ref(false)

async function createFamily() {
  saving.value = true
  message.value = ''
  try {
    await api('/api/families', {
      method: 'POST',
      body: JSON.stringify({ name: familyName.value }),
    })
    await refreshSession()
    await router.push('/')
  } catch (error) {
    message.value = error instanceof Error ? error.message : '创建失败'
  } finally {
    saving.value = false
  }
}

async function joinFamily() {
  saving.value = true
  message.value = ''
  try {
    await api('/api/invitations/accept', {
      method: 'POST',
      body: JSON.stringify({ code: code.value }),
    })
    await refreshSession()
    await router.push('/')
  } catch (error) {
    message.value = error instanceof Error ? error.message : '加入失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main>
    <h1>加入家庭</h1>
    <section class="card">
      <h2>创建家庭</h2>
      <form @submit.prevent="createFamily">
        <label class="field">
          家庭名称
          <input v-model="familyName" placeholder="例如：悠悠的家" required />
        </label>
        <div class="actions">
          <button class="btn primary" :disabled="saving">创建</button>
        </div>
      </form>
    </section>
    <section class="card">
      <h2>用邀请码加入</h2>
      <form @submit.prevent="joinFamily">
        <label class="field">
          邀请码
          <input v-model="code" required />
        </label>
        <div class="actions">
          <button class="btn primary" :disabled="saving">加入</button>
        </div>
      </form>
    </section>
    <p v-if="message" class="error">{{ message }}</p>
  </main>
</template>
