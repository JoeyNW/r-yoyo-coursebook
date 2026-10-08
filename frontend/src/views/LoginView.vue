<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../api'
import { refreshSession } from '../session'

const router = useRouter()
const loginName = ref('')
const password = ref('')
const message = ref('')
const saving = ref(false)

async function submit() {
  saving.value = true
  message.value = ''
  try {
    await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        login_name: loginName.value,
        password: password.value,
      }),
    })
    await refreshSession()
    await router.push('/')
  } catch (error) {
    message.value = error instanceof Error ? error.message : '登录失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="auth">
    <h1>悠悠课程本</h1>
    <p class="muted">家里人看同一本课时账。</p>
    <form @submit.prevent="submit">
      <label class="field">
        用户名
        <input v-model="loginName" autocomplete="username" required />
      </label>
      <label class="field">
        密码
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
        />
      </label>
      <p v-if="message" class="error">{{ message }}</p>
      <div class="actions">
        <button class="btn primary" type="submit" :disabled="saving">登录</button>
      </div>
    </form>
    <p><RouterLink to="/register">没有账号，去注册</RouterLink></p>
  </main>
</template>
