import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import HomeView from '../views/HomeView.vue'
import OutlineView from '../views/OutlineView.vue'
import GenerateView from '../views/GenerateView.vue'
import ResultView from '../views/ResultView.vue'
import HistoryView from '../views/HistoryView.vue'

// 管理后台组件（懒加载）
const AdminLayout = () => import('../views/admin/AdminLayout.vue')
const AdminDashboard = () => import('../views/admin/AdminDashboard.vue')
const AdminUsers = () => import('../views/admin/AdminUsers.vue')
const AdminRecords = () => import('../views/admin/AdminRecords.vue')
const AdminImages = () => import('../views/admin/AdminImages.vue')
const AdminConfig = () => import('../views/admin/AdminConfig.vue')
const AdminRegistration = () => import('../views/admin/AdminRegistration.vue')
const AdminAuditLogs = () => import('../views/admin/AdminAuditLogs.vue')

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
    },
    // 管理后台路由
    {
      path: '/admin',
      component: AdminLayout,
      meta: { requiresAdmin: true },
      children: [
        {
          path: '',
          name: 'admin-dashboard',
          component: AdminDashboard
        },
        {
          path: 'users',
          name: 'admin-users',
          component: AdminUsers
        },
        {
          path: 'records',
          name: 'admin-records',
          component: AdminRecords
        },
        {
          path: 'images',
          name: 'admin-images',
          component: AdminImages
        },
        {
          path: 'config',
          name: 'admin-config',
          component: AdminConfig
        },
        {
          path: 'registration',
          name: 'admin-registration',
          component: AdminRegistration
        },
        {
          path: 'audit-logs',
          name: 'admin-audit-logs',
          component: AdminAuditLogs
        }
      ]
    }
  ]
})

// 需要登录的路由
const authRequiredRoutes = ['outline', 'generate', 'result', 'history']

// 路由守卫：检查登录状态和管理员权限
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 确保认证状态已初始化（只在首次加载时执行）
  // 修复：无条件等待初始化完成，避免时序问题
  if (!authStore._initialized) {
    await authStore.initAuth()
  }

  // 检查是否需要管理员权限
  if (to.matched.some(record => record.meta.requiresAdmin)) {
    if (!authStore.isAuthenticated) {
      // 未登录，跳转到首页并提示登录
      next({
        name: 'home',
        query: { redirect: to.fullPath, login_required: '1' }
      })
      return
    }
    if (!authStore.isAdmin) {
      // 已登录但非管理员，跳转到首页
      next({ name: 'home' })
      return
    }
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
