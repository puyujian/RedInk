import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import HomeView from '../views/HomeView.vue'
import OutlineView from '../views/OutlineView.vue'
import GenerateView from '../views/GenerateView.vue'
import ResultView from '../views/ResultView.vue'
import HistoryView from '../views/HistoryView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/outline',
      name: 'outline',
      component: OutlineView
    },
    {
      path: '/generate',
      name: 'generate',
      component: GenerateView
    },
    {
      path: '/result',
      name: 'result',
      component: ResultView
    },
    {
      path: '/history',
      name: 'history',
      component: HistoryView
    }
  ]
})

// 需要登录的路由
const authRequiredRoutes = ['outline', 'generate', 'result', 'history']

// 路由守卫：检查登录状态
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 首次加载时初始化认证状态
  if (!authStore.initializing && !authStore.isAuthenticated && !authStore.user) {
    await authStore.initAuth()
  }

  // 检查是否需要登录
  if (authRequiredRoutes.includes(to.name as string)) {
    if (!authStore.isAuthenticated) {
      // 保存目标路由用于登录后跳转
      next({
        name: 'home',
        query: { redirect: to.fullPath, login_required: '1' }
      })
      return
    }
  }

  next()
})

export default router
