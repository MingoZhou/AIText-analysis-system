import { reactive } from 'vue'
import { authApi, AUTH_TOKEN_KEY } from './api'

export const authState = reactive({
  user: null,
  ready: false,
})

export function hasToken() {
  return Boolean(localStorage.getItem(AUTH_TOKEN_KEY))
}

function applySession(data) {
  localStorage.setItem(AUTH_TOKEN_KEY, data.access_token)
  authState.user = data.user
}

export async function initializeAuth() {
  if (!hasToken()) {
    authState.ready = true
    return
  }
  try {
    const response = await authApi.me()
    authState.user = response.data
  } catch {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    authState.user = null
  } finally {
    authState.ready = true
  }
}

export async function loginAccount(payload) {
  const response = await authApi.login(payload)
  applySession(response.data)
  return response.data.user
}

export async function registerAccount(payload) {
  const response = await authApi.register(payload)
  applySession(response.data)
  return response.data.user
}

export async function logoutAccount() {
  try {
    if (hasToken()) await authApi.logout()
  } finally {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    authState.user = null
  }
}
