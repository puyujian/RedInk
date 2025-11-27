/**
 * 后台管理 API 模块
 *
 * 提供用户管理、生成记录管理、图片管理、配置管理等 API
 */
import axios from 'axios'
import { getStoredAccessToken } from './auth'
import { getUserId } from '../utils/userId'

export const API_BASE_URL = '/api/admin'

// ============================================================================
// axios 实例配置
// ============================================================================

const adminClient = axios.create({
  baseURL: API_BASE_URL,
})

// 请求拦截器：添加认证信息
adminClient.interceptors.request.use((config) => {
  config.headers = config.headers || {}
  config.headers['X-User-Id'] = getUserId()

  const token = getStoredAccessToken()
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }

  return config
})

// 响应拦截器：统一错误处理
adminClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token 过期，尝试刷新
      try {
        const { useAuthStore } = await import('../stores/auth')
        const authStore = useAuthStore()
        const newToken = await authStore.refreshToken()

        if (newToken) {
          error.config.headers['Authorization'] = `Bearer ${newToken}`
          return adminClient(error.config)
        }
      } catch {
        // 刷新失败，跳转到登录页
        window.location.href = '/?login_required=1'
      }
    }
    return Promise.reject(error)
  }
)

// ============================================================================
// 类型定义
// ============================================================================

export interface AdminUser {
  id: number
  uuid: string
  username: string
  email: string | null
  role: string
  is_active: boolean
  client_id: string | null
  created_at: string
  updated_at: string
  last_login_at: string | null
}

export interface AdminRecord {
  id: number
  record_uuid: string
  user_id: number | null
  client_id: string | null
  title: string
  status: string
  thumbnail_url: string | null
  page_count: number
  image_task_id: string | null
  created_at: string
  updated_at: string
  outline_raw?: string
  outline_json?: Record<string, unknown>
  images_json?: Record<string, unknown>
  user?: { username: string }
}

export interface AdminImage {
  id: number
  user_id: number
  record_id: number | null
  task_id: string | null
  filename: string
  file_size: number | null
  created_at: string
  user?: { username: string }
}

export interface ConfigVersion {
  id: number
  version: number
  content: string
  diff_summary: string | null
  created_at: string
  created_by: number | null
  created_by_username?: string
}

export interface RegistrationSetting {
  enabled: boolean
  default_role: string
  invite_required: boolean
  invite_code: string | null
  email_verification_required: boolean
  rate_limit_per_hour: number
  updated_at: string
  updated_by_username?: string
}

export interface AuditLogEntry {
  id: number
  actor_id: number | null
  actor_username: string | null
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}

export interface ImageStats {
  total_count: number
  total_size: number
  today_count: number
}

export interface DashboardStats {
  total_users: number
  active_users: number
  inactive_users: number
  pro_count: number  // PRO用户数量（VIP用户）
  users_today: number
  total_records: number
  completed_records: number
  generating_records: number
  draft_records: number
  records_today: number
  total_images: number
  images_today: number
  total_storage_bytes: number
}

interface ApiResponse<T> {
  success: boolean
  error?: string
  [key: string]: unknown
}

interface PaginatedApiResponse<T> extends ApiResponse<T> {
  items?: T[]
  page?: number
  pages?: number
  total?: number
}

// ============================================================================
// 用户管理 API
// ============================================================================

export async function getUsers(params?: {
  page?: number
  per_page?: number
  search?: string
  role?: string
  is_active?: boolean
}): Promise<PaginatedApiResponse<AdminUser>> {
  try {
    const response = await adminClient.get('/users', { params })
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '请求失败' }
  }
}

export async function getUser(userId: number): Promise<ApiResponse<AdminUser> & { user?: AdminUser }> {
  try {
    const response = await adminClient.get(`/users/${userId}`)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '请求失败' }
  }
}

export async function createUser(data: {
  username: string
  email?: string
  password: string
  role?: string
}): Promise<ApiResponse<AdminUser> & { user?: AdminUser }> {
  try {
    const response = await adminClient.post('/users', data)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '创建失败' }
  }
}

export async function updateUser(
  userId: number,
  data: {
    email?: string
    role?: string
  }
): Promise<ApiResponse<AdminUser> & { user?: AdminUser }> {
  try {
    const response = await adminClient.put(`/users/${userId}`, data)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '更新失败' }
  }
}

export async function updateUserStatus(
  userId: number,
  isActive: boolean
): Promise<ApiResponse<AdminUser>> {
  try {
    const response = await adminClient.patch(`/users/${userId}/status`, { is_active: isActive })
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '操作失败' }
  }
}

export async function deleteUser(userId: number): Promise<ApiResponse<void>> {
  try {
    const response = await adminClient.delete(`/users/${userId}`)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '删除失败' }
  }
}

// ============================================================================
// 生成记录管理 API
// ============================================================================

export async function getRecords(params?: {
  page?: number
  per_page?: number
  search?: string
  status?: string
  user_id?: number
}): Promise<PaginatedApiResponse<AdminRecord>> {
  try {
    const response = await adminClient.get('/records', { params })
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '请求失败' }
  }
}

export async function getRecordDetail(recordId: number): Promise<ApiResponse<AdminRecord> & { record?: AdminRecord }> {
  try {
    const response = await adminClient.get(`/records/${recordId}`)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '请求失败' }
  }
}

export async function deleteRecord(recordId: number): Promise<ApiResponse<void>> {
  try {
    const response = await adminClient.delete(`/records/${recordId}`)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '删除失败' }
  }
}

export async function batchDeleteRecords(ids: number[]): Promise<ApiResponse<void> & { deleted?: number }> {
  try {
    const response = await adminClient.delete('/records', { data: { ids } })
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '批量删除失败' }
  }
}

// ============================================================================
// 图片管理 API
// ============================================================================

export async function getImages(params?: {
  page?: number
  per_page?: number
  search?: string
  user_id?: number
}): Promise<PaginatedApiResponse<AdminImage>> {
  try {
    const response = await adminClient.get('/images', { params })
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '请求失败' }
  }
}

export async function getImageStats(): Promise<ApiResponse<ImageStats> & { stats?: ImageStats }> {
  try {
    const response = await adminClient.get('/images/stats')
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '请求失败' }
  }
}

export async function deleteImage(imageId: number): Promise<ApiResponse<void>> {
  try {
    const response = await adminClient.delete(`/images/${imageId}`)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '删除失败' }
  }
}

export async function batchDeleteImages(ids: number[]): Promise<ApiResponse<void> & { deleted?: number }> {
  try {
    const response = await adminClient.delete('/images', { data: { ids } })
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '批量删除失败' }
  }
}

// ============================================================================
// 配置文件管理 API
// ============================================================================

/**
 * 获取图片服务商配置
 *
 * @returns 配置内容和解析后的 YAML 对象
 */
export async function getImageProvidersConfig(): Promise<
  ApiResponse<{ content: string; parsed: unknown }>
> {
  try {
    const response = await adminClient.get('/config/image-providers')
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '获取配置失败' }
  }
}

export async function updateImageProvidersConfig(content: string): Promise<ApiResponse<void>> {
  try {
    const response = await adminClient.put('/config/image-providers', { content })
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '保存配置失败' }
  }
}

export async function getConfigHistory(): Promise<ApiResponse<void> & { versions?: ConfigVersion[] }> {
  try {
    const response = await adminClient.get('/config/image-providers/history')
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '获取历史失败' }
  }
}

export async function rollbackConfig(version: number): Promise<ApiResponse<void>> {
  try {
    const response = await adminClient.post(`/config/image-providers/rollback/${version}`)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '回滚失败' }
  }
}

// ============================================================================
// 注册开关管理 API
// ============================================================================

export async function getRegistrationSettings(): Promise<ApiResponse<void> & { settings?: RegistrationSetting }> {
  try {
    const response = await adminClient.get('/registration')
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '获取设置失败' }
  }
}

export async function updateRegistrationSettings(data: {
  enabled?: boolean
  default_role?: string
  invite_required?: boolean
  invite_code?: string
  email_verification_required?: boolean
  rate_limit_per_hour?: number
}): Promise<ApiResponse<void>> {
  try {
    const response = await adminClient.put('/registration', data)
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '保存设置失败' }
  }
}

export async function getRegistrationHistory(): Promise<ApiResponse<void> & { logs?: AuditLogEntry[] }> {
  try {
    const response = await adminClient.get('/registration/history')
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '获取历史失败' }
  }
}

// ============================================================================
// 审计日志 API
// ============================================================================

export async function getAuditLogs(params?: {
  page?: number
  per_page?: number
  action?: string
  resource_type?: string
  actor_id?: number
}): Promise<PaginatedApiResponse<AuditLogEntry>> {
  try {
    const response = await adminClient.get('/audit-logs', { params })
    return response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '请求失败' }
  }
}

// ============================================================================
// 仪表盘 API
// ============================================================================

/**
 * 后端返回的原始统计数据结构（嵌套格式）
 */
interface RawDashboardData {
  users?: {
    total?: number
    active?: number
    pro?: number  // PRO用户数量
  }
  records?: {
    total?: number
    completed?: number
  }
  images?: {
    total?: number
    size_bytes?: number
    size_mb?: number
  }
}

/**
 * 将后端返回的嵌套数据结构映射为前端期望的扁平结构
 */
function mapDashboardStats(rawData?: RawDashboardData): DashboardStats {
  const users = rawData?.users ?? {}
  const records = rawData?.records ?? {}
  const images = rawData?.images ?? {}

  const totalUsers = users.total ?? 0
  const activeUsers = users.active ?? 0

  return {
    // 用户统计
    total_users: totalUsers,
    active_users: activeUsers,
    inactive_users: Math.max(totalUsers - activeUsers, 0), // 计算得出
    pro_count: users.pro ?? 0, // PRO用户数量（VIP用户）
    users_today: 0, // 后端暂未提供

    // 记录统计
    total_records: records.total ?? 0,
    completed_records: records.completed ?? 0,
    generating_records: 0, // 后端暂未提供
    draft_records: 0, // 后端暂未提供
    records_today: 0, // 后端暂未提供

    // 图片统计
    total_images: images.total ?? 0,
    images_today: 0, // 后端暂未提供
    total_storage_bytes: images.size_bytes ?? 0,
  }
}

export async function getDashboardStats(): Promise<ApiResponse<void> & { stats?: DashboardStats }> {
  try {
    const response = await adminClient.get('/dashboard/stats')
    const apiData = response.data

    // 检查响应是否成功
    if (apiData.success && apiData.data) {
      // 将后端返回的嵌套数据映射为前端期望的扁平结构
      const stats = mapDashboardStats(apiData.data as RawDashboardData)
      return {
        success: true,
        stats,
      }
    } else {
      return {
        success: false,
        error: apiData.error || '获取统计数据失败',
      }
    }
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    return { success: false, error: err.response?.data?.error || '获取统计失败' }
  }
}
