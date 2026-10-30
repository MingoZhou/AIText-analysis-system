import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

export const AUTH_TOKEN_KEY = 'cezhi-auth-token'

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url || ''
    if (error.response?.status === 401 && !url.includes('/auth/login') && !url.includes('/auth/register')) {
      localStorage.removeItem(AUTH_TOKEN_KEY)
      if (window.location.pathname !== '/login') {
        const redirect = encodeURIComponent(window.location.pathname + window.location.search)
        window.location.assign(`/login?redirect=${redirect}`)
      }
    }
    return Promise.reject(error)
  },
)

// ========== Authentication ==========
export const authApi = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
}

// ========== Dashboard ==========
export const dashboardApi = {
  getStats: () => api.get('/dashboard/stats'),
}

// ========== Keywords ==========
export const keywordApi = {
  list: () => api.get('/keywords'),
  preview: (data) => api.post('/keywords/preview', data),
  create: (data) => api.post('/keywords', data),
  update: (id, data) => api.put(`/keywords/${id}`, data),
  delete: (id) => api.delete(`/keywords/${id}`),
}

// ========== Data Sources ==========
export const sourceApi = {
  list: () => api.get('/sources'),
  create: (data) => api.post('/sources', data),
  update: (id, data) => api.put(`/sources/${id}`, data),
  delete: (id) => api.delete(`/sources/${id}`),
}

// ========== Crawler ==========
export const crawlerApi = {
  run: (data) => api.post('/crawler/run', data),
  getLogs: (limit = 20) => api.get('/crawler/logs', { params: { limit } }),
  getLog: (id) => api.get(`/crawler/logs/${id}`),
  getItems: (id, limit = 200) => api.get(`/crawler/logs/${id}/items`, { params: { limit } }),
  deleteLog: (id) => api.delete(`/crawler/logs/${id}`),
}

// ========== Articles ==========
export const articleApi = {
  list: (params) => api.get('/articles', { params }),
  get: (id) => api.get(`/articles/${id}`),
  download: (id) => api.get(`/articles/${id}/download`, { responseType: 'blob' }),
  delete: (id) => api.delete(`/articles/${id}`),
  toggleStar: (id) => api.put(`/articles/${id}/star`),
}

// ========== AI Providers ==========
export const providerApi = {
  listPresets: () => api.get('/providers/presets'),
  listLocalPresets: () => api.get('/providers/local-presets'),
  getPresetOrder: () => api.get('/providers/preset-order'),
  updatePresetOrder: (keys) => api.put('/providers/preset-order', { keys }),
  list: () => api.get('/providers'),
  create: (data) => api.post('/providers', data),
  update: (id, data) => api.put(`/providers/${id}`, data),
  delete: (id) => api.delete(`/providers/${id}`),
  setCurrent: (id) => api.put(`/providers/${id}/current`),
  testConnection: (data) => api.post('/providers/test', data),
  getModels: (data) => api.post('/providers/models', data),
}

export default api

// ========== AI Analysis ==========
export const analysisApi = {
  summary: (data) => api.post('/analysis/summary', data),
  wordcloud: (data) => api.post('/analysis/wordcloud', data),
  chart: (data) => api.post('/analysis/chart', data),
  chat: (data) => api.post('/analysis/chat', data),
  history: (limit = 20) => api.get('/analysis/history', { params: { limit } }),
  downloadSummary: (resultId, format = 'md') =>
    api.get(`/analysis/summary/${resultId}/download`, { params: { format }, responseType: 'blob' }),
  usageStats: () => api.get('/analysis/usage-stats'),
}

// ========== Profile ==========
export const profileApi = {
  get: () => api.get('/profile'),
  update: (data) => api.put('/profile', data),
  uploadAvatar: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/profile/avatar', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  changePassword: (data) => api.post('/profile/change-password', data),
  sendCode: (data) => api.post('/profile/send-code', data),
  sendChangeEmailCode: (data) => api.post('/profile/send-change-email-code', data),
  verifyCode: (data) => api.post('/profile/verify-code', data),
}

// ========== Chat Sessions ==========
export const chatSessionApi = {
  list: () => api.get('/chat-sessions'),
  create: (data) => api.post('/chat-sessions', data),
  get: (id) => api.get(`/chat-sessions/${id}`),
  update: (id, data) => api.put(`/chat-sessions/${id}`, data),
  delete: (id) => api.delete(`/chat-sessions/${id}`),
  sendMessage: (id, data) => api.post(`/chat-sessions/${id}/messages`, data),
  compress: (id) => api.post(`/chat-sessions/${id}/compress`),
}

// ========== Admin (权限管理) ==========
export const adminApi = {
  // 角色
  listRoles: () => api.get('/admin/roles'),
  createRole: (data) => api.post('/admin/roles', data),
  updateRole: (id, data) => api.put(`/admin/roles/${id}`, data),
  deleteRole: (id) => api.delete(`/admin/roles/${id}`),
  // 用户
  listUsers: () => api.get('/admin/users'),
  assignRoles: (data) => api.post('/admin/users/assign-roles', data),
  removeUserRole: (userId, roleId) => api.delete(`/admin/users/${userId}/roles/${roleId}`),
  // 智能体授权
  listRoleProviders: (roleId) => api.get(`/admin/roles/${roleId}/providers`),
  listProviderGrants: (providerId) => api.get(`/admin/providers/${providerId}/grants`),
  createProviderGrant: (data) => api.post('/admin/providers/grants', data),
  deleteProviderGrant: (providerId, roleId) => api.delete(`/admin/providers/${providerId}/grants/${roleId}`),
  // Token 用量
  getUserTokenUsage: (userId) => api.get(`/admin/users/${userId}/token-usage`),
  getAllTokenUsage: () => api.get('/admin/token-usage/all'),
}
