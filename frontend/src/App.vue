<template>
  <div id="app">
    <!-- 移动端汉堡菜单按钮 -->
    <button
      type="button"
      class="sidebar-toggle"
      :class="{ 'is-active': isSidebarOpen }"
      @click="toggleSidebar"
      aria-label="切换侧边栏"
    >
      <span class="sidebar-toggle__icon">
        <span class="sidebar-toggle__line"></span>
        <span class="sidebar-toggle__line"></span>
        <span class="sidebar-toggle__line"></span>
      </span>
    </button>

    <!-- 侧边栏遮罩层（移动端） -->
    <div
      class="sidebar-backdrop"
      :class="{ 'is-visible': isSidebarOpen }"
      @click="closeSidebar"
    ></div>

    <!-- 侧边栏 Sidebar -->
    <aside class="layout-sidebar" :class="{ 'is-open': isSidebarOpen }">
      <div class="logo-area">
        <img src="/logo.png" alt="迪迦" class="logo-icon" />
        <span class="logo-text">迪迦</span>
      </div>

      <nav class="nav-menu" @click="handleNavClick">
        <RouterLink to="/" class="nav-item" active-class="active">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
          创作中心
        </RouterLink>
        <RouterLink to="/history" class="nav-item" active-class="active">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
          历史记录
        </RouterLink>
        <RouterLink v-if="authStore.isAdmin" to="/admin" class="nav-item admin-nav" active-class="active">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
          管理中心
        </RouterLink>
      </nav>

      <!-- 用户信息区域 -->
      <div class="user-section">
        <UserMenu @open-auth="showAuthModal = true" />
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="layout-main">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>

    <!-- 登录/注册模态框 -->
    <AuthModal v-model:visible="showAuthModal" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterView, RouterLink, useRoute, useRouter } from 'vue-router'
import AuthModal from './components/AuthModal.vue'
import UserMenu from './components/UserMenu.vue'
import { useAuthStore } from './stores/auth'
import { useGeneratorStore } from './stores/generator'

// ============================================================================
// State
// ============================================================================

const showAuthModal = ref(false)
const isSidebarOpen = ref(false)
const authStore = useAuthStore()
const generatorStore = useGeneratorStore()
const route = useRoute()
const router = useRouter()

// ============================================================================
// Sidebar Control
// ============================================================================

/** 切换侧边栏显示状态 */
function toggleSidebar() {
  isSidebarOpen.value = !isSidebarOpen.value
}

/** 关闭侧边栏 */
function closeSidebar() {
  isSidebarOpen.value = false
}

/** 处理导航点击，移动端自动关闭侧边栏 */
function handleNavClick() {
  // 仅在移动端时关闭侧边栏
  if (window.innerWidth < 768) {
    closeSidebar()
  }
}

/** ESC 键关闭侧边栏 */
function handleEscKey(event: KeyboardEvent) {
  if (event.key === 'Escape' && isSidebarOpen.value) {
    closeSidebar()
  }
}

// ============================================================================
// Lifecycle & Watchers
// ============================================================================

// 监听路由参数，处理 showAuth=login
watch(
  () => route.query,
  (query) => {
    if (query.showAuth === 'login') {
      showAuthModal.value = true
      // 清除 query 参数，避免刷新页面时再次弹出
      router.replace({ query: { ...query, showAuth: undefined } })
    }
  },
  { immediate: true }
)

// 路由变化时关闭侧边栏（移动端）
watch(
  () => route.path,
  () => {
    if (window.innerWidth < 768) {
      closeSidebar()
    }
  }
)

// 侧边栏打开时禁止 body 滚动（使用 CSS class）
watch(isSidebarOpen, (isOpen) => {
  if (typeof document !== 'undefined') {
    if (isOpen) {
      document.body.classList.add('sidebar-open')
    } else {
      document.body.classList.remove('sidebar-open')
    }
  }
})

// 监听认证状态变化
watch(
  () => authStore.isAuthenticated,
  (isAuthenticated) => {
    if (!isAuthenticated) {
      // 用户登出，清理生成器状态
      generatorStore.reset()
      
      // 如果当前在创作相关页面，跳转回首页
      const creationPaths = ['/outline', '/generate', '/result']
      if (creationPaths.some(path => route.path.startsWith(path))) {
        router.push('/')
      }
    }
  }
)

onMounted(() => {
  // 应用启动时初始化认证状态
  authStore.initAuth()
  // 监听 ESC 键
  window.addEventListener('keydown', handleEscKey)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleEscKey)
  // 确保清理滚动锁定
  if (typeof document !== 'undefined') {
    document.body.classList.remove('sidebar-open')
  }
})
</script>

<style scoped>
/* 用户信息区域 */
.user-section {
  margin-top: auto;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}
</style>
