import { defineStore } from 'pinia'

/**
 * 主题模式类型
 * - light: 浅色模式
 * - dark: 深色模式
 * - system: 跟随系统
 */
export type ThemeMode = 'light' | 'dark' | 'system'

/**
 * 实际生效的主题类型
 */
export type EffectiveTheme = 'light' | 'dark'

const STORAGE_KEY = 'redink-theme-preference'

/**
 * 主题管理 Store
 *
 * 职责：
 * 1. 管理用户主题偏好设置
 * 2. 监听系统主题变化
 * 3. 应用实际生效的主题
 * 4. 持久化用户选择
 */
export const useThemeStore = defineStore('theme', {
  state: () => ({
    /** 用户偏好设置 */
    userPreference: 'system' as ThemeMode,

    /** 实际生效的主题 */
    effectiveTheme: 'light' as EffectiveTheme,

    /** 系统主题媒体查询对象 */
    mediaQuery: null as MediaQueryList | null,
  }),

  getters: {
    /**
     * 当前是否为深色模式
     */
    isDark: (state) => state.effectiveTheme === 'dark',

    /**
     * 当前是否为浅色模式
     */
    isLight: (state) => state.effectiveTheme === 'light',

    /**
     * 是否跟随系统
     */
    isSystemMode: (state) => state.userPreference === 'system',
  },

  actions: {
    /**
     * 初始化主题系统
     *
     * 执行流程：
     * 1. 从 localStorage 读取用户偏好
     * 2. 创建系统主题媒体查询监听器
     * 3. 应用实际生效的主题
     */
    init() {
      // 读取持久化的用户偏好
      const savedPreference = this.loadPreference()
      if (savedPreference) {
        this.userPreference = savedPreference
      }

      // 创建系统主题媒体查询
      if (typeof window !== 'undefined') {
        this.mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

        // 监听系统主题变化
        this.mediaQuery.addEventListener('change', this.handleSystemThemeChange)
      }

      // 应用主题
      this.applyEffectiveTheme()
    },

    /**
     * 设置主题模式
     *
     * @param mode - 要设置的主题模式
     */
    setTheme(mode: ThemeMode) {
      this.userPreference = mode
      this.savePreference(mode)
      this.applyEffectiveTheme()
    },

    /**
     * 处理系统主题变化
     *
     * 仅在用户选择"跟随系统"时响应
     */
    handleSystemThemeChange() {
      if (this.userPreference === 'system') {
        this.applyEffectiveTheme()
      }
    },

    /**
     * 应用实际生效的主题
     *
     * 逻辑：
     * - 如果用户选择 light/dark，直接应用
     * - 如果用户选择 system，根据系统主题决定
     */
    applyEffectiveTheme() {
      let theme: EffectiveTheme

      if (this.userPreference === 'system') {
        // 跟随系统：检查系统是否为深色模式
        const systemPrefersDark = this.mediaQuery?.matches ?? false
        theme = systemPrefersDark ? 'dark' : 'light'
      } else {
        // 用户明确选择
        theme = this.userPreference
      }

      // 更新状态
      this.effectiveTheme = theme

      // 应用到 DOM
      if (typeof document !== 'undefined') {
        document.documentElement.setAttribute('data-theme', theme)
      }
    },

    /**
     * 从 localStorage 加载用户偏好
     */
    loadPreference(): ThemeMode | null {
      if (typeof localStorage === 'undefined') return null

      try {
        const saved = localStorage.getItem(STORAGE_KEY)
        if (saved && ['light', 'dark', 'system'].includes(saved)) {
          return saved as ThemeMode
        }
      } catch (error) {
        console.warn('Failed to load theme preference:', error)
      }

      return null
    },

    /**
     * 保存用户偏好到 localStorage
     */
    savePreference(mode: ThemeMode) {
      if (typeof localStorage === 'undefined') return

      try {
        localStorage.setItem(STORAGE_KEY, mode)
      } catch (error) {
        console.warn('Failed to save theme preference:', error)
      }
    },

    /**
     * 清理资源
     *
     * 移除系统主题监听器
     */
    dispose() {
      if (this.mediaQuery) {
        this.mediaQuery.removeEventListener('change', this.handleSystemThemeChange)
        this.mediaQuery = null
      }
    },
  },
})
