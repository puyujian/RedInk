<template>
  <div class="theme-switcher-floating">
    <!-- 主按钮 -->
    <button
      type="button"
      class="theme-toggle-btn"
      :class="{ 'is-open': isOpen }"
      @click="toggleMenu"
      :title="getCurrentThemeLabel()"
    >
      <!-- 浅色主题图标 -->
      <svg v-if="themeStore.userPreference === 'light'" class="theme-toggle-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
      </svg>
      <!-- 深色主题图标 -->
      <svg v-else-if="themeStore.userPreference === 'dark'" class="theme-toggle-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
      <!-- 跟随系统图标 -->
      <svg v-else class="theme-toggle-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
        <line x1="8" y1="21" x2="16" y2="21"></line>
        <line x1="12" y1="17" x2="12" y2="21"></line>
      </svg>
    </button>

    <!-- 选项面板 -->
    <Transition name="theme-panel">
      <div v-if="isOpen" class="theme-panel" @click.stop>
        <div class="theme-panel__header">
          <span>选择主题</span>
        </div>
        <div class="theme-panel__options">
          <!-- 浅色主题 -->
          <button
            type="button"
            class="theme-option"
            :class="{ 'is-active': themeStore.userPreference === 'light' }"
            @click="handleThemeChange('light')"
          >
            <svg class="theme-option__icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>
            <span class="theme-option__label">浅色</span>
            <svg v-if="themeStore.userPreference === 'light'" class="check-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          </button>
          <!-- 深色主题 -->
          <button
            type="button"
            class="theme-option"
            :class="{ 'is-active': themeStore.userPreference === 'dark' }"
            @click="handleThemeChange('dark')"
          >
            <svg class="theme-option__icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
            <span class="theme-option__label">深色</span>
            <svg v-if="themeStore.userPreference === 'dark'" class="check-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          </button>
          <!-- 跟随系统 -->
          <button
            type="button"
            class="theme-option"
            :class="{ 'is-active': themeStore.userPreference === 'system' }"
            @click="handleThemeChange('system')"
          >
            <svg class="theme-option__icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
              <line x1="8" y1="21" x2="16" y2="21"></line>
              <line x1="12" y1="17" x2="12" y2="21"></line>
            </svg>
            <span class="theme-option__label">跟随系统</span>
            <svg v-if="themeStore.userPreference === 'system'" class="check-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          </button>
        </div>
      </div>
    </Transition>

    <!-- 遮罩层 -->
    <Transition name="backdrop">
      <div v-if="isOpen" class="theme-backdrop" @click="closeMenu"></div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useThemeStore, type ThemeMode } from '@/stores/theme'

// ============================================================================
// State & Store
// ============================================================================

const themeStore = useThemeStore()
const isOpen = ref(false)

// ============================================================================
// Methods
// ============================================================================

/**
 * 切换菜单显示/隐藏
 */
function toggleMenu() {
  isOpen.value = !isOpen.value
}

/**
 * 关闭菜单
 */
function closeMenu() {
  isOpen.value = false
}

/**
 * 处理主题切换
 */
function handleThemeChange(mode: ThemeMode) {
  themeStore.setTheme(mode)
  closeMenu()
}

/**
 * 获取当前主题的标签
 */
function getCurrentThemeLabel() {
  const labels = {
    light: '浅色',
    dark: '深色',
    system: '跟随系统'
  }
  return labels[themeStore.userPreference] || '主题'
}

// ============================================================================
// Lifecycle
// ============================================================================

onBeforeUnmount(() => {
  themeStore.dispose()
})
</script>

<style scoped>
/* 浮动容器 */
.theme-switcher-floating {
  position: fixed;
  bottom: 24px;
  right: -32px;
  z-index: 999;
  transition: right 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

/* PC端：仅在打开面板时展开 */
.theme-switcher-floating:focus-within {
  right: 24px;
}

/* 主切换按钮 */
.theme-toggle-btn {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: none;
  background: var(--bg-card);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-main);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.theme-toggle-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: var(--primary);
  opacity: 0;
  transform: scale(0);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.theme-toggle-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16), 0 4px 12px rgba(0, 0, 0, 0.12);
}

.theme-toggle-btn:hover::before {
  opacity: 0.08;
  transform: scale(1);
}

.theme-toggle-btn:active {
  transform: translateY(0) scale(0.95);
}

.theme-toggle-btn.is-open {
  background: var(--primary);
  color: white;
  transform: rotate(180deg);
}

.theme-toggle-icon {
  position: relative;
  z-index: 1;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.theme-toggle-btn.is-open .theme-toggle-icon {
  transform: rotate(-180deg);
}

/* 选项面板 */
.theme-panel {
  position: absolute;
  bottom: 64px;
  right: 0;
  min-width: 200px;
  background: var(--bg-card);
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15), 0 4px 16px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  border: 1px solid var(--border-color);
}

.theme-panel__header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-color);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-sub);
  background: var(--overlay-light);
}

.theme-panel__options {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.theme-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-main);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  text-align: left;
  width: 100%;
  position: relative;
}

.theme-option:hover {
  background: var(--overlay-light);
  transform: translateX(2px);
}

.theme-option.is-active {
  background: var(--primary-light);
  color: var(--primary);
}

.theme-option__icon {
  flex-shrink: 0;
  opacity: 0.8;
  transition: opacity 0.2s;
}

.theme-option.is-active .theme-option__icon {
  opacity: 1;
}

.theme-option__label {
  flex: 1;
}

.check-icon {
  flex-shrink: 0;
  color: var(--primary);
  animation: checkIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes checkIn {
  from {
    opacity: 0;
    transform: scale(0.5);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* 遮罩层 */
.theme-backdrop {
  position: fixed;
  inset: 0;
  background: transparent;
  z-index: -1;
}

/* 面板动画 */
.theme-panel-enter-active,
.theme-panel-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.theme-panel-enter-from {
  opacity: 0;
  transform: translateY(10px) scale(0.95);
}

.theme-panel-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.95);
}

/* 遮罩动画 */
.backdrop-enter-active,
.backdrop-leave-active {
  transition: opacity 0.2s ease;
}

.backdrop-enter-from,
.backdrop-leave-to {
  opacity: 0;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .theme-switcher-floating {
    bottom: 20px;
    right: -28px;
  }

  /* 移动端：悬停或打开时展开 */
  .theme-switcher-floating:hover,
  .theme-switcher-floating:focus-within {
    right: 20px;
  }

  .theme-toggle-btn {
    width: 48px;
    height: 48px;
  }

  .theme-panel {
    bottom: 60px;
    min-width: 180px;
  }

  .theme-option {
    padding: 14px 12px;
  }
}

/* 小屏手机适配 */
@media (max-width: 428px) {
  .theme-switcher-floating {
    bottom: 16px;
    right: -26px;
  }

  /* 小屏手机：悬停或打开时展开 */
  .theme-switcher-floating:hover,
  .theme-switcher-floating:focus-within {
    right: 16px;
  }

  .theme-toggle-btn {
    width: 44px;
    height: 44px;
  }

  .theme-panel {
    bottom: 56px;
  }
}

/* 暗黑模式优化 */
[data-theme="dark"] .theme-toggle-btn {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3), 0 2px 8px rgba(0, 0, 0, 0.2);
}

[data-theme="dark"] .theme-toggle-btn:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4), 0 4px 12px rgba(0, 0, 0, 0.3);
}

[data-theme="dark"] .theme-panel {
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5), 0 4px 16px rgba(0, 0, 0, 0.3);
}
</style>
