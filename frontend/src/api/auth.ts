/**
 * 认证相关 API 函数
 *
 * 提供用户注册、登录、刷新 token、登出、获取用户信息等功能
 * 与后端 /api/auth/* 接口对应
 */
import axios from 'axios'
import { getUserId } from '../utils/userId'

const API_BASE_URL = '/api'

// ============================================================================
// 常量定义
// ============================================================================

/** access_token 在 localStorage 中的存储键名 */
export const ACCESS_TOKEN_STORAGE_KEY = 'redink_access_token'

// ============================================================================
// 类型定义
// ============================================================================

/** 用户信息结构（与后端返回一致） */
export interface AuthUser {
  id: number
  uuid: string
  username: string
  email: string | null
  role: string
  is_active?: boolean
  created_at?: string
  last_login_at?: string | null
}

/** 登录/注册成功响应 */
export interface AuthResponse {
  success: boolean
  user: AuthUser
  access_token: string
  refresh_token?: string
  error?: string
}

/** 刷新 token 响应 */
export interface RefreshResponse {
  success: boolean
  access_token?: string
  error?: string
}

/** 通用响应 */
export interface CommonResponse {
  success: boolean
  message?: string
  error?: string
}

/** 登录参数 */
export interface LoginParams {
  username: string
  password: string
}

/** 注册参数 */
export interface RegisterParams {
  username: string
  password: string
  email?: string
  client_id?: string
  /** 邀请码(当后台开启邀请码注册时必填) */
  invite_code?: string
}

/** 公开注册配置响应 */
export interface PublicRegistrationConfigResponse {
  success: boolean
  invite_required: boolean
  error?: string
}

// ============================================================================
// 工具函数
// ============================================================================

/**
 * 检测当前环境是否为浏览器
 */
function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

/**
 * 从 localStorage 读取 access_token
 *
 * @returns 存储的 token 或 null
 */
export function getStoredAccessToken(): string | null {
  if (!isBrowser()) return null
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

/**
 * 将 access_token 写入 localStorage
 *
 * @param token - 要存储的 token，传入 null 表示清除
 */
export function saveAccessToken(token: string | null): void {
  if (!isBrowser()) return
  try {
    if (token) {
      window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token)
    } else {
      window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
    }
  } catch {
    // localStorage 不可用时静默失败，不影响主流程
    console.warn('localStorage 不可用，无法持久化 token')
  }
}

/**
 * 构造通用请求头
 *
 * @param includeAuth - 是否包含 Authorization 头
 * @returns 请求头对象
 */
function buildHeaders(includeAuth: boolean = false): Record<string, string> {
  const headers: Record<string, string> = {
    'X-User-Id': getUserId(),
    'Content-Type': 'application/json',
  }

  if (includeAuth) {
    const token = getStoredAccessToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
  }

  return headers
}

// ============================================================================
// API 函数
// ============================================================================

/**
 * 用户注册
 *
 * @param data - 注册参数
 * @returns 注册响应，包含用户信息和 token
 * @throws 网络错误或服务端错误
 */
export async function register(data: RegisterParams): Promise<AuthResponse> {
  const payload: RegisterParams = {
    ...data,
  }

  // 如果未提供 client_id，使用匿名用户 UUID
  if (!payload.client_id) {
    payload.client_id = getUserId()
  }

  const response = await axios.post<AuthResponse>(
    `${API_BASE_URL}/auth/register`,
    payload,
    {
      withCredentials: true,
      headers: buildHeaders(false),
    }
  )

  return response.data
}

/**
 * 用户登录
 *
 * @param data - 登录参数
 * @returns 登录响应，包含用户信息和 token
 * @throws 网络错误或服务端错误
 */
export async function login(data: LoginParams): Promise<AuthResponse> {
  const response = await axios.post<AuthResponse>(
    `${API_BASE_URL}/auth/login`,
    data,
    {
      withCredentials: true,
      headers: buildHeaders(false),
    }
  )

  return response.data
}

/**
 * 用户登出
 *
 * 需要用户已登录（携带有效的 access_token）
 *
 * @returns 登出响应
 * @throws 网络错误或服务端错误
 */
export async function logout(): Promise<CommonResponse> {
  const response = await axios.post<CommonResponse>(
    `${API_BASE_URL}/auth/logout`,
    undefined,
    {
      withCredentials: true,
      headers: buildHeaders(true),
    }
  )

  return response.data
}

/**
 * 刷新 access_token
 *
 * 从 HttpOnly Cookie 中读取 refresh_token 进行刷新
 * 如果刷新成功，会自动更新本地存储的 access_token
 *
 * @returns 刷新响应，包含新的 access_token
 * @throws 网络错误或服务端错误
 */
export async function refresh(): Promise<RefreshResponse> {
  const response = await axios.post<RefreshResponse>(
    `${API_BASE_URL}/auth/refresh`,
    undefined,
    {
      withCredentials: true,
      headers: buildHeaders(false),
    }
  )

  const data = response.data

  // 如果刷新成功，自动保存新的 token
  if (data.success && data.access_token) {
    saveAccessToken(data.access_token)
  }

  return data
}

/**
 * 获取当前登录用户信息
 *
 * 需要用户已登录（携带有效的 access_token）
 *
 * @returns 用户信息
 * @throws 网络错误或服务端错误
 */
export async function getMe(): Promise<AuthUser> {
  const response = await axios.get<{ success: boolean; user: AuthUser }>(
    `${API_BASE_URL}/auth/me`,
    {
      withCredentials: true,
      headers: buildHeaders(true),
    }
  )

  const data = response.data

  if (data.success && data.user) {
    return data.user
  }

  throw new Error('获取用户信息失败')
}

/**
 * 解析 JWT token 的 payload（不验证签名）
 *
 * @param token - JWT token 字符串
 * @returns 解码后的 payload 对象，解析失败返回 null
 */
export function decodeToken(token: string): any | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null

    const payload = parts[1]
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decoded)
  } catch (err) {
    console.warn('[Auth] 解析 token 失败:', err)
    return null
  }
}

/**
 * 检查 token 是否即将过期（5分钟内）
 *
 * @param token - JWT token 字符串
 * @returns true 表示即将过期，false 表示还有效
 */
export function isTokenExpiringSoon(token: string | null, thresholdSeconds: number = 300): boolean {
  if (!token) return true

  const payload = decodeToken(token)
  if (!payload || !payload.exp) return true

  const now = Math.floor(Date.now() / 1000)
  const expiresAt = payload.exp
  const remainingSeconds = expiresAt - now

  return remainingSeconds < thresholdSeconds
}

/**
 * 确保 access token 有效（如果即将过期则刷新）
 *
 * 此函数用于在创建 SSE 连接等长连接前，主动检查并刷新 token
 *
 * @returns 有效的 token，如果无法获取有效 token 则返回 null
 */
export async function ensureValidToken(): Promise<string | null> {
  const currentToken = getStoredAccessToken()

  // 如果没有 token，直接返回
  if (!currentToken) {
    console.log('[Auth] 未登录，跳过 token 检查')
    return null
  }

  // 检查 token 是否即将过期
  if (isTokenExpiringSoon(currentToken)) {
    console.log('[Auth] Token 即将过期，正在刷新...')

    try {
      const result = await refresh()
      if (result.success && result.access_token) {
        console.log('[Auth] Token 刷新成功')
        return result.access_token
      } else {
        console.error('[Auth] Token 刷新失败:', result.error)
        return null
      }
    } catch (err) {
      console.error('[Auth] Token 刷新出错:', err)
      return null
    }
  }

  // Token 仍然有效
  return currentToken
}

/**
 * 获取公开的注册配置(无需认证)
 *
 * 仅返回是否需要邀请码,不包含邀请码本身等敏感信息
 *
 * @returns 公开注册配置响应
 * @throws 网络错误或服务端错误
 */
export async function getPublicRegistrationConfig(): Promise<PublicRegistrationConfigResponse> {
  const response = await axios.get<PublicRegistrationConfigResponse>(
    `${API_BASE_URL}/auth/registration/config`,
    {
      headers: buildHeaders(false),
    }
  )
  return response.data
}
