<template>
  <div class="admin-layout">
    <!-- 侧边栏 -->
    <aside class="admin-sidebar">
      <div class="sidebar-header">
        <h1 class="sidebar-title">RedInk 管理后台</h1>
      </div>

      <nav class="sidebar-nav">
        <router-link to="/admin" class="nav-item" exact-active-class="active">
          <span class="nav-icon">📊</span>
          <span class="nav-text">仪表盘</span>
        </router-link>

        <router-link to="/admin/users" class="nav-item" active-class="active">
          <span class="nav-icon">👥</span>
          <span class="nav-text">用户管理</span>
        </router-link>

        <router-link to="/admin/records" class="nav-item" active-class="active">
          <span class="nav-icon">📝</span>
          <span class="nav-text">生成记录</span>
        </router-link>

        <router-link to="/admin/images" class="nav-item" active-class="active">
          <span class="nav-icon">🖼️</span>
          <span class="nav-text">图片管理</span>
        </router-link>

        <router-link to="/admin/config" class="nav-item" active-class="active">
          <span class="nav-icon">⚙️</span>
          <span class="nav-text">配置管理</span>
        </router-link>

        <router-link to="/admin/registration" class="nav-item" active-class="active">
          <span class="nav-icon">🔐</span>
          <span class="nav-text">注册设置</span>
        </router-link>

        <router-link to="/admin/audit-logs" class="nav-item" active-class="active">
          <span class="nav-icon">📋</span>
          <span class="nav-text">审计日志</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <router-link to="/" class="nav-item back-link">
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
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

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

async function handleLogout() {
  await authStore.logout()
  router.push('/')
}
</script>

<style scoped>
.admin-layout {
  display: flex;
  min-height: 100vh;
  background-color: #f5f7fa;
}

/* 侧边栏 */
.admin-sidebar {
  width: 240px;
  background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 100;
}

.sidebar-header {
  padding: 24px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.sidebar-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #fff;
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
  margin-left: 240px;
  display: flex;
  flex-direction: column;
}

.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 32px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  position: sticky;
  top: 0;
  z-index: 50;
}

.header-left {
  display: flex;
  align-items: center;
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
}

.btn-logout:hover {
  background: #f3f4f6;
  color: #1a1a2e;
}

.admin-content {
  flex: 1;
  padding: 24px 32px;
}
</style>
