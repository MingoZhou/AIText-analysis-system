import { createRouter, createWebHistory } from 'vue-router'
import { hasToken } from '../auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { title: '登录', public: true } },
  { path: '/', name: 'home', component: () => import('../views/Home.vue'), meta: { title: '首页' } },
  { path: '/collection', name: 'collection', component: () => import('../views/DataCollection.vue'), meta: { title: '数据采集' } },
  { path: '/articles', name: 'articles', component: () => import('../views/CollectedInfo.vue'), meta: { title: '采集信息' } },
  { path: '/data-analysis', name: 'data-analysis', component: () => import('../views/DataAnalysis.vue'), meta: { title: '数据分析' } },
  { path: '/analysis', name: 'analysis', component: () => import('../views/AIAnalysis.vue'), meta: { title: 'AI 分析' } },
  { path: '/profile', name: 'profile', component: () => import('../views/Profile.vue'), meta: { title: '个人信息' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (!to.meta.public && !hasToken()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && hasToken()) {
    return { name: 'home' }
  }
  return true
})

export default router
