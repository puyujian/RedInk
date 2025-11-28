<template>
  <div class="user-menu" ref="menuRef">
    <!-- 未登录状态：显示登录/注册按钮 -->
    <template v-if="!isAuthenticated">
      <button
        v-if="!initializing"
        type="button"
        class="btn btn-primary user-menu-auth-btn"
        @click="handleOpenAuth"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
          <circle cx="12" cy="7" r="4"></circle>
        </svg>
        登录 / 注册
      </button>
      <!-- 初始化加载状态 -->
      <div v-else class="user-menu-skeleton">
        <div class="skeleton-avatar"></div>
        <div class="skeleton-text"></div>
      </div>
    </template>

    <!-- 已登录状态：显示用户信息和下拉菜单 -->
    <div v-else class="user-menu-logged">
      <button type="button" class="user-menu-trigger" @click="toggleDropdown">
        <div class="user-avatar">
          <span>{{ avatarInitial }}</span>
        </div>
        <div class="user-info">
          <div class="user-name">{{ displayName }}</div>
          <div class="user-role" v-if="user?.email">{{ user.email }}</div>
          <div class="user-role" v-else>已登录</div>
        </div>
        <span class="user-menu-arrow" :class="{ open: dropdownOpen }">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </span>
      </button>

      <!-- 下拉菜单 -->
      <Transition name="user-dropdown">
        <div v-if="dropdownOpen" class="user-menu-dropdown">
          <!-- 用户信息卡片 -->
          <div class="user-menu-card">
            <div class="user-avatar user-avatar-lg">
              <span>{{ avatarInitial }}</span>
            </div>
            <div class="user-card-info">
              <div class="user-card-name">{{ displayName }}</div>
              <div class="user-card-email">{{ user?.email || '暂无邮箱' }}</div>
            </div>
          </div>

          <div class="user-menu-divider"></div>

          <!-- 菜单项 -->
          <div class="user-menu-item user-menu-item-role">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
            <span class="user-menu-item-value">{{ roleDisplayName }}</span>
          </div>

          <button type="button" class="user-menu-item user-menu-item-logout" @click="handleLogout">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
              <polyline points="16 17 21 12 16 7"></polyline>
              <line x1="21" y1="12" x2="9" y2="12"></line>
            </svg>
            退出登录
          </button>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'

// ============================================================================
// Emits
// ============================================================================

const emit = defineEmits<{
  (event: 'open-auth'): void
}>()

// ============================================================================
// Store & State
// ============================================================================

const authStore = useAuthStore()
const menuRef = ref<HTMLElement | null>(null)
const dropdownOpen = ref(false)

// ============================================================================
// Computed
// ============================================================================

const isAuthenticated = computed(() => authStore.isAuthenticated)
const initializing = computed(() => authStore.initializing)
const user = computed(() => authStore.user)
const displayName = computed(() => authStore.displayName)
const avatarInitial = computed(() => authStore.avatarInitial)
const roleDisplayName = computed(() => authStore.roleDisplayName)

// ============================================================================
// Methods
// ============================================================================

function handleOpenAuth() {
  emit('open-auth')
}

function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value
}

async function handleLogout() {
  dropdownOpen.value = false
  await authStore.logout()
}

function handleClickOutside(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  if (!target) return

  // 点击菜单外部时关闭下拉框
  if (menuRef.value && !menuRef.value.contains(target)) {
    dropdownOpen.value = false
  }
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  window.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  window.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
/* 容器 */
.user-menu {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  width: 100%;
}

/* 登录按钮 */
.user-menu-auth-btn {
  width: 100%;
  font-size: 14px;
  padding: 12px 16px;
  gap: 8px;
  justify-content: center;
}

/* 加载骨架屏 */
.user-menu-skeleton {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 0;
}

.skeleton-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
}

.skeleton-text {
  flex: 1;
  height: 16px;
  border-radius: 4px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
}

@keyframes skeleton-loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* 已登录状态 */
.user-menu-logged {
  position: relative;
  width: 100%;
}

.user-menu-trigger {
  width: 100%;
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 8px 4px;
  border-radius: 10px;
  transition: background 0.2s;
}

.user-menu-trigger:hover {
  background: var(--overlay-light);
}

/* 用户头像 */
.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(255, 36, 66, 0.15) 0%, rgba(255, 36, 66, 0.25) 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
  color: var(--primary);
  flex-shrink: 0;
}

.user-avatar-lg {
  width: 44px;
  height: 44px;
  font-size: 16px;
}

/* 用户信息 */
.user-info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.user-role {
  font-size: 12px;
  color: var(--text-sub);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

/* 箭头 */
.user-menu-arrow {
  margin-left: auto;
  color: var(--text-sub);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.user-menu-arrow.open {
  transform: rotate(180deg);
}

/* 下拉菜单 */
.user-menu-dropdown {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 8px);
  background: var(--bg-card);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
  padding: 8px;
  z-index: 100;
}

/* 用户信息卡片 */
.user-menu-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--overlay-light);
  border-radius: 10px;
}

.user-card-info {
  flex: 1;
  min-width: 0;
}

.user-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-card-email {
  font-size: 12px;
  color: var(--text-sub);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 分隔线 */
.user-menu-divider {
  height: 1px;
  background: var(--border-color);
  margin: 8px 0;
}

/* 菜单项 */
.user-menu-item {
  width: 100%;
  border: none;
  background: transparent;
  padding: 10px 12px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-main);
  transition: all 0.2s;
}

.user-menu-item:hover {
  background: var(--overlay-light);
}

/* 身份显示项（不可点击） */
.user-menu-item-role {
  cursor: default;
  pointer-events: none;
}

.user-menu-item-value {
  font-weight: 500;
  color: var(--primary);
}

.user-menu-item-logout {
  color: #ff4d4f;
}

.user-menu-item-logout:hover {
  background: var(--primary-light);
}

/* 下拉动画 */
.user-dropdown-enter-active,
.user-dropdown-leave-active {
  transition: all 0.2s ease;
}

.user-dropdown-enter-from,
.user-dropdown-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

/* 移动端适配 */
@media (max-width: 768px) {
  .user-menu {
    justify-content: center;
  }

  .user-menu-dropdown {
    position: fixed;
    left: 16px;
    right: 16px;
    bottom: auto;
    top: 50%;
    transform: translateY(-50%);
    max-width: 320px;
    margin: 0 auto;
  }

  .user-dropdown-enter-from,
  .user-dropdown-leave-to {
    transform: translateY(-50%) scale(0.95);
  }
}
</style>
