<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../api'
import { refreshSession } from '../session'

const router = useRouter()
const displayName = ref('')
const loginName = ref('')
const password = ref('')
const message = ref('')
const saving = ref(false)

async function submit() {
  saving.value = true
  message.value = ''
  try {
    await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        display_name: displayName.value,
        login_name: loginName.value,
        password: password.value,
      }),
    })
    await refreshSession()
    await router.push('/setup')
  } catch (error) {
    message.value = error instanceof Error ? error.message : '注册失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="auth">
    <h1>注册</h1>
    <form @submit.prevent="submit">
      <label class="field">
        怎么称呼你
        <input v-model="displayName" required maxlength="40" />
      </label>
      <label class="field">
        用户名
        <input v-model="loginName" autocomplete="username" required />
      </label>
      <label class="field">
        密码（至少 8 位）
        <input
          v-model="password"
          type="password"
          autocomplete="new-password"
          minlength="8"
          required
        />
      </label>
      <p v-if="message" class="error">{{ message }}</p>
      <div class="actions">
        <button class="btn primary" type="submit" :disabled="saving">注册</button>
      </div>
    </form>
    <p><RouterLink to="/login">已有账号，去登录</RouterLink></p>
  </main>
</template>
