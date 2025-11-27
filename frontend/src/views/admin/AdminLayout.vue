<template>
  <div class="admin-layout" :class="{ 'sidebar-open': isSidebarOpen }">
    <!-- 移动端遮罩层 -->
    <div
      class="sidebar-backdrop"
      :class="{ visible: isSidebarOpen }"
      @click="closeSidebar"
    ></div>

    <!-- 侧边栏 -->
    <aside class="admin-sidebar" :class="{ open: isSidebarOpen }">
      <div class="sidebar-header">
        <h1 class="sidebar-title">RedInk 管理后台</h1>
        <button
          class="btn-close-sidebar"
          @click="closeSidebar"
          aria-label="关闭侧边栏"
        >
          ×
        </button>
      </div>

      <nav class="sidebar-nav">
        <router-link to="/admin" class="nav-item" exact-active-class="active" @click="handleNavClick">
          <span class="nav-icon">📊</span>
          <span class="nav-text">仪表盘</span>
        </router-link>

        <router-link to="/admin/users" class="nav-item" active-class="active" @click="handleNavClick">
          <span class="nav-icon">👥</span>
          <span class="nav-text">用户管理</span>
        </router-link>

        <router-link to="/admin/records" class="nav-item" active-class="active" @click="handleNavClick">
          <span class="nav-icon">📝</span>
          <span class="nav-text">生成记录</span>
        </router-link>

        <router-link to="/admin/images" class="nav-item" active-class="active" @click="handleNavClick">
          <span class="nav-icon">🖼️</span>
          <span class="nav-text">图片管理</span>
        </router-link>

        <router-link to="/admin/config" class="nav-item" active-class="active" @click="handleNavClick">
          <span class="nav-icon">⚙️</span>
          <span class="nav-text">配置管理</span>
        </router-link>

        <router-link to="/admin/registration" class="nav-item" active-class="active" @click="handleNavClick">
          <span class="nav-icon">🔐</span>
          <span class="nav-text">注册设置</span>
        </router-link>

        <router-link to="/admin/audit-logs" class="nav-item" active-class="active" @click="handleNavClick">
          <span class="nav-icon">📋</span>
          <span class="nav-text">审计日志</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <router-link to="/" class="nav-item back-link" @click="handleNavClick">
          <span class="nav-icon">←</span>
          <span class="nav-text">返回主站</span>
        </router-link>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="admin-main">
      <!-- 顶部栏 -->
      <header class="admin-header">
        <div class="header-left">
          <!-- 汉堡菜单按钮 -->
          <button
            class="btn-hamburger"
            @click="toggleSidebar"
            :aria-expanded="isSidebarOpen"
            aria-label="切换菜单"
          >
            <span class="hamburger-bar"></span>
            <span class="hamburger-bar"></span>
            <span class="hamburger-bar"></span>
          </button>
          <h2 class="page-title">{{ pageTitle }}</h2>
        </div>
        <div class="header-right">
          <span class="user-info">{{ authStore.displayName }}</span>
          <button class="btn-logout" @click="handleLogout">登出</button>
        </div>
      </header>

      <!-- 页面内容 -->
      <div class="admin-content">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// 侧边栏状态
const isSidebarOpen = ref(false)

// 页面标题映射
const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    'admin-dashboard': '仪表盘',
    'admin-users': '用户管理',
    'admin-records': '生成记录',
    'admin-images': '图片管理',
    'admin-config': '配置管理',
    'admin-registration': '注册设置',
    'admin-audit-logs': '审计日志',
  }
  return titles[route.name as string] || '管理后台'
})

// 切换侧边栏
function toggleSidebar() {
  isSidebarOpen.value = !isSidebarOpen.value
  updateBodyScroll()
}

// 关闭侧边栏
function closeSidebar() {
  isSidebarOpen.value = false
  updateBodyScroll()
}

// 导航点击处理（移动端自动关闭侧边栏）
function handleNavClick() {
  if (window.innerWidth <= 1024) {
    closeSidebar()
  }
}

// 控制body滚动（侧边栏打开时禁止背景滚动）
function updateBodyScroll() {
  if (isSidebarOpen.value && window.innerWidth <= 1024) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
}

// 窗口大小变化时处理
function handleResize() {
  if (window.innerWidth > 1024) {
    isSidebarOpen.value = false
    document.body.style.overflow = ''
  }
}

// 登出处理
async function handleLogout() {
  await authStore.logout()
  router.push('/')
}

// 监听路由变化，移动端自动关闭侧边栏
watch(() => route.path, () => {
  if (window.innerWidth <= 1024) {
    closeSidebar()
  }
})

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  document.body.style.overflow = ''
})
</script>

<style scoped>
/* CSS 变量定义 */
.admin-layout {
  --sidebar-width: 240px;
  --sidebar-mobile-width: min(280px, 85vw);
  --header-height: 64px;
  --transition-duration: 250ms;
  --transition-timing: cubic-bezier(0.4, 0, 0.2, 1);

  display: flex;
  min-height: 100vh;
  background-color: #f5f7fa;
}

/* 遮罩层 */
.sidebar-backdrop {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 99;
  opacity: 0;
  transition: opacity var(--transition-duration) var(--transition-timing);
  pointer-events: none;
}

.sidebar-backdrop.visible {
  opacity: 1;
  pointer-events: auto;
}

/* 侧边栏 */
.admin-sidebar {
  width: var(--sidebar-width);
  background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 100;
  transition: transform var(--transition-duration) var(--transition-timing);
}

.sidebar-header {
  padding: 24px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sidebar-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #fff;
}

/* 关闭按钮（仅移动端显示） */
.btn-close-sidebar {
  display: none;
  width: 32px;
  height: 32px;
  border: none;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  font-size: 20px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-close-sidebar:hover {
  background: rgba(255, 255, 255, 0.2);
}

.sidebar-nav {
  flex: 1;
  padding: 16px 12px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.7);
  text-decoration: none;
  transition: all 0.2s;
  margin-bottom: 4px;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.nav-item.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.nav-icon {
  width: 24px;
  font-size: 16px;
  margin-right: 12px;
  text-align: center;
}

.nav-text {
  font-size: 14px;
}

.sidebar-footer {
  padding: 16px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.back-link {
  color: rgba(255, 255, 255, 0.5);
}

.back-link:hover {
  color: #fff;
}

/* 主内容区 */
.admin-main {
  flex: 1;
  margin-left: var(--sidebar-width);
  display: flex;
  flex-direction: column;
  min-width: 0; /* 防止flex子元素溢出 */
}

.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  position: sticky;
  top: 0;
  z-index: 50;
  min-height: var(--header-height);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 汉堡菜单按钮（默认隐藏，仅移动端显示） */
.btn-hamburger {
  display: none;
  width: 44px;
  height: 44px;
  padding: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 5px;
  border-radius: 8px;
  transition: background 0.2s;
}

.btn-hamburger:hover {
  background: #f3f4f6;
}

.hamburger-bar {
  width: 22px;
  height: 2px;
  background: #374151;
  border-radius: 2px;
  transition: transform 0.2s, opacity 0.2s;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-info {
  font-size: 14px;
  color: #6b7280;
}

.btn-logout {
  padding: 8px 16px;
  background: transparent;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
}

.btn-logout:hover {
  background: #f3f4f6;
  color: #1a1a2e;
}

.admin-content {
  flex: 1;
  padding: 24px;
  overflow-x: hidden;
}

/* ==================== 响应式布局 ==================== */

/* 平板适配 (769px - 1024px) */
@media (max-width: 1024px) {
  .admin-layout {
    --sidebar-width: 220px;
  }

  .admin-content {
    padding: 20px;
  }
}

/* 移动端适配 (768px 及以下) */
@media (max-width: 768px) {
  /* 显示遮罩层 */
  .sidebar-backdrop {
    display: block;
  }

  /* 侧边栏改为抽屉模式 */
  .admin-sidebar {
    width: var(--sidebar-mobile-width);
    transform: translateX(-100%);
    box-shadow: 4px 0 20px rgba(0, 0, 0, 0.15);
  }

  .admin-sidebar.open {
    transform: translateX(0);
  }

  /* 显示关闭按钮 */
  .btn-close-sidebar {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* 显示汉堡菜单 */
  .btn-hamburger {
    display: flex;
  }

  /* 主内容区占满宽度 */
  .admin-main {
    margin-left: 0;
    width: 100%;
  }

  /* 头部调整 */
  .admin-header {
    padding: 12px 16px;
    min-height: 56px;
  }

  .page-title {
    font-size: 16px;
  }

  /* 右侧信息在移动端简化 */
  .header-right {
    gap: 8px;
  }

  .user-info {
    display: none;
  }

  .btn-logout {
    padding: 8px 12px;
    font-size: 13px;
  }

  /* 内容区域 */
  .admin-content {
    padding: 16px;
  }

  /* 导航项增大点击区域 */
  .nav-item {
    padding: 14px 16px;
    margin-bottom: 6px;
  }

  .nav-icon {
    font-size: 18px;
  }

  .nav-text {
    font-size: 15px;
  }
}

/* 小屏手机适配 (480px 及以下) */
@media (max-width: 480px) {
  .admin-header {
    padding: 10px 12px;
  }

  .header-left {
    gap: 8px;
  }

  .page-title {
    font-size: 15px;
  }

  .admin-content {
    padding: 12px;
  }

  .sidebar-title {
    font-size: 16px;
  }
}
</style>
