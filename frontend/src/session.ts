import { reactive } from 'vue'
import { ApiError, api } from './api'
import type { Family, Me, User } from './types'

export const session = reactive({
  ready: false,
  user: null as User | null,
  family: null as Family | null,
})

export async function refreshSession(): Promise<void> {
  try {
    const me = await api<Me>('/api/me')
    session.user = me.user
    session.family = me.families[0] ?? null
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      session.user = null
      session.family = null
    } else {
      throw error
    }
  } finally {
    session.ready = true
  }
}

export function clearSession(): void {
  session.user = null
  session.family = null
  session.ready = true
}
