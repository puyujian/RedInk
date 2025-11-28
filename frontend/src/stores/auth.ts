/**
 * 认证状态管理 Store
 *
 * 统一管理用户认证状态，包括：
 * - 登录/登出状态
 * - 用户信息
 * - Token 管理
 * - 自动刷新 Token
 */
import { defineStore } from 'pinia'
import type { AuthUser, LoginParams, RegisterParams } from '../api/auth'
import {
  getStoredAccessToken,
  saveAccessToken,
  login as loginApi,
  register as registerApi,
  logout as logoutApi,
  refresh as refreshApi,
  getMe as getMeApi,
} from '../api/auth'

// ============================================================================
// 类型定义
// ============================================================================

/** 认证状态结构 */
export interface AuthState {
  /** 是否已登录 */
  isAuthenticated: boolean
  /** 是否正在初始化或请求中（用于 UI 加载状态） */
  initializing: boolean
  /** 当前 access_token */
  accessToken: string | null
  /** 当前用户信息 */
  user: AuthUser | null
  /** 是否已完成初始化（用于路由守卫判断） */
  _initialized: boolean
}

// ============================================================================
// Store 定义
// ============================================================================

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    isAuthenticated: false,
    initializing: false,
    accessToken: null,
    user: null,
    _initialized: false,
  }),

  getters: {
    /**
     * 获取用户显示名称
     */
    displayName(): string {
      if (this.user?.username) {
        return this.user.username
      }
      if (this.user?.email) {
        return this.user.email.split('@')[0]
      }
      return '用户'
    },

    /**
     * 获取用户头像首字母
     */
    avatarInitial(): string {
      const name = this.user?.username || this.user?.email || ''
      if (!name) return 'U'
      return name.trim().charAt(0).toUpperCase()
    },

    /**
     * 检查用户是否为管理员
     */
    isAdmin(): boolean {
      return this.user?.role === 'admin'
    },

    /**
     * 获取用户角色显示名称
     */
    roleDisplayName(): string {
      const role = this.user?.role
      if (!role) return '普通会员'

      switch (role) {
        case 'admin':
          return '管理员'
        case 'pro':
        case 'premium':
          return '专业会员'
        case 'user':
        case 'member':
        default:
          return '普通会员'
      }
    },
  },

  actions: {
    /**
     * 设置 access_token 并同步到本地存储
     *
     * @param token - 新的 token，传入 null 清除
     */
    setAccessToken(token: string | null) {
      this.accessToken = token
      saveAccessToken(token)

      // 更新认证状态
      if (!token) {
        this.isAuthenticated = false
      } else if (this.user) {
        this.isAuthenticated = true
      }
    },

    /**
     * 用户登录
     *
     * @param payload - 登录参数
     * @returns 登录响应
     * @throws 登录失败时抛出错误
     */
    async login(payload: LoginParams) {
      this.initializing = true
      try {
        const result = await loginApi(payload)

        if (!result.success) {
          throw new Error(result.error || '登录失败')
        }

        // 更新状态
        this.accessToken = result.access_token
        saveAccessToken(result.access_token)
        this.user = result.user
        this.isAuthenticated = true

        return result
      } finally {
        this.initializing = false
      }
    },

    /**
     * 用户注册
     *
     * @param payload - 注册参数
     * @returns 注册响应
     * @throws 注册失败时抛出错误
     */
    async register(payload: RegisterParams) {
      this.initializing = true
      try {
        const result = await registerApi(payload)

        if (!result.success) {
          throw new Error(result.error || '注册失败')
        }

        // 注册成功后自动登录
        this.accessToken = result.access_token
        saveAccessToken(result.access_token)
        this.user = result.user
        this.isAuthenticated = true

        return result
      } finally {
        this.initializing = false
      }
    },

    /**
     * 用户登出
     *
     * 即使服务端登出失败，也会清理本地状态
     */
    async logout() {
      this.initializing = true
      try {
        await logoutApi()
      } catch (error) {
        // 登出接口失败时，仍然清理本地状态，避免出现"假登录"状态
        console.warn('登出请求失败:', error)
      } finally {
        // 清理所有认证相关状态
        this.accessToken = null
        saveAccessToken(null)
        this.user = null
        this.isAuthenticated = false
        this.initializing = false
      }
    },

    /**
     * 刷新 access_token
     *
     * 通常由 axios 拦截器在遇到 401 时调用
     *
     * @returns 新的 access_token，刷新失败返回 null
     * @throws 刷新失败时抛出错误
     */
    async refreshToken(): Promise<string | null> {
      try {
        const result = await refreshApi()

        if (result.success && result.access_token) {
          this.accessToken = result.access_token
          // refreshApi 内部已调用 saveAccessToken
          if (this.user) {
            this.isAuthenticated = true
          }
          return result.access_token
        }

        // 刷新失败（返回成功但无 token），清理所有状态
        this.accessToken = null
        saveAccessToken(null)
        this.user = null
        this.isAuthenticated = false
        return null
      } catch (error) {
        // 刷新出错，清理所有状态
        this.accessToken = null
        saveAccessToken(null)
        this.user = null
        this.isAuthenticated = false
        throw error
      }
    },

    /**
     * 获取当前用户信息
     *
     * @returns 用户信息，失败返回 null
     * @throws 请求失败时抛出错误
     */
    async fetchMe(): Promise<AuthUser | null> {
      try {
        const user = await getMeApi()
        this.user = user

        // 有 token 且用户信息获取成功，则认为已登录
        if (this.accessToken) {
          this.isAuthenticated = true
        }

        return user
      } catch (error) {
        this.user = null
        this.isAuthenticated = false
        throw error
      }
    },

    /**
     * 初始化认证状态
     *
     * 应用启动时调用，检查本地存储的 token 是否有效
     */
    async initAuth() {
      this.initializing = true
      try {
        // 尝试从本地存储读取 token
        const token = getStoredAccessToken()

        if (!token) {
          // 无本地 token，保持未登录状态
          this.accessToken = null
          this.user = null
          this.isAuthenticated = false
          return
        }

        // 设置 token 并验证有效性
        this.accessToken = token

        try {
          // 调用 /me 接口验证 token 是否有效
          await this.fetchMe()
        } catch {
          // /me 请求失败（例如 401），清理本地状态
          this.accessToken = null
          saveAccessToken(null)
          this.user = null
          this.isAuthenticated = false
        }
      } finally {
        this.initializing = false
        this._initialized = true
      }
    },

    /**
     * 重置认证状态（用于测试或手动清理）
     */
    reset() {
      this.accessToken = null
      saveAccessToken(null)
      this.user = null
      this.isAuthenticated = false
      this.initializing = false
    },
  },
})
