import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { getUserId } from '../utils/userId'
import { getStoredAccessToken, saveAccessToken, ensureValidToken } from './auth'

export const API_BASE_URL = '/api'

// ============================================================================
// axios 实例配置
// ============================================================================

/**
 * 配置 axios 实例
 *
 * 功能：
 * - 自动添加 X-User-Id 请求头（匿名用户兼容）
 * - 自动添加 Authorization: Bearer token 头（已登录用户）
 * - 401 响应时自动刷新 token 并重试
 */
const apiClient = axios.create({
  baseURL: API_BASE_URL,
})

// ============================================================================
// 请求拦截器
// ============================================================================

apiClient.interceptors.request.use((config) => {
  // 确保 headers 对象存在
  config.headers = config.headers || {}

  // 始终添加匿名用户 ID（向后兼容）
  config.headers['X-User-Id'] = getUserId()

  // 如果有 access_token 且未手动设置 Authorization，则自动添加
  const token = getStoredAccessToken()
  if (token && !config.headers['Authorization']) {
    config.headers['Authorization'] = `Bearer ${token}`
  }

  return config
})

// ============================================================================
// 响应拦截器 - 自动刷新 token
// ============================================================================

/** 扩展请求配置类型，添加重试标记 */
interface ExtendedAxiosRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

/** 刷新 token 的并发控制：同一时间只发起一个刷新请求 */
let refreshPromise: Promise<string | null> | null = null

apiClient.interceptors.response.use(
  // 成功响应直接返回
  (response) => response,
  // 处理错误响应
  async (error: AxiosError) => {
    const { response, config } = error
    const originalRequest = config as ExtendedAxiosRequestConfig

    // 非 401 错误或无原始请求配置，直接抛出
    if (!response || response.status !== 401 || !originalRequest) {
      return Promise.reject(error)
    }

    // 已经重试过，不再重试
    if (originalRequest._retry) {
      return Promise.reject(error)
    }

    // 检查是否为认证相关接口，避免循环刷新
    const url = originalRequest.url || ''
    const isAuthEndpoint =
      url.includes('/auth/login') ||
      url.includes('/auth/register') ||
      url.includes('/auth/refresh') ||
      url.includes('/auth/logout')

    if (isAuthEndpoint) {
      return Promise.reject(error)
    }

    // 尝试刷新 token（通过 store 以保持状态同步）
    if (!refreshPromise) {
      // 延迟导入 store 以避免循环依赖和 Pinia 初始化问题
      refreshPromise = import('../stores/auth')
        .then(({ useAuthStore }) => {
          const authStore = useAuthStore()
          return authStore.refreshToken()
        })
        .catch((refreshError) => {
          console.warn('刷新 token 失败:', refreshError)
          // 确保清理本地存储
          saveAccessToken(null)
          return null
        })
        .finally(() => {
          refreshPromise = null
        })
    }

    // 等待刷新结果
    const newToken = await refreshPromise

    if (!newToken) {
      // 刷新失败，返回原始错误
      return Promise.reject(error)
    }

    // 刷新成功，重试原始请求
    originalRequest._retry = true
    originalRequest.headers['Authorization'] = `Bearer ${newToken}`

    return apiClient(originalRequest)
  }
)

export interface Page {
  index: number
  type: 'cover' | 'content' | 'summary'
  content: string
}

export interface OutlineResponse {
  success: boolean
  outline?: string
  pages?: Page[]
  error?: string
}

export interface ProgressEvent {
  index: number
  status: 'generating' | 'done' | 'error'
  current?: number
  total?: number
  image_url?: string
  candidates?: string[]
  message?: string
  phase?: string
}

export interface FinishEvent {
  success: boolean
  task_id: string
  images: string[]
  total?: number
  completed?: number
  failed?: number
  failed_indices?: number[]
}

// ==================== 大纲生成 API ====================

interface OutlineTaskResponse {
  success: boolean
  task_id?: string
  status?: string
  error?: string
}

interface OutlineTaskStatusResponse {
  success: boolean
  task_id: string
  status: string
  progress_current: number
  progress_total: number
  outline?: string
  pages?: Page[]
  error?: string
}

/**
 * 创建大纲生成任务
 */
async function createOutlineTask(
  topic: string,
  images?: File[]
): Promise<OutlineTaskResponse> {
  if (images && images.length > 0) {
    const formData = new FormData()
    formData.append('topic', topic)
    images.forEach((file) => {
      formData.append('images', file)
    })

    const response = await apiClient.post<OutlineTaskResponse>('/outline', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  }

  const response = await apiClient.post<OutlineTaskResponse>('/outline', { topic })
  return response.data
}

/**
 * 查询大纲任务状态
 */
async function getOutlineTaskStatus(taskId: string): Promise<OutlineTaskStatusResponse> {
  const response = await apiClient.get<OutlineTaskStatusResponse>(`/outline/${taskId}`)
  return response.data
}

/**
 * 轮询等待大纲生成完成
 */
async function pollOutlineTask(
  taskId: string,
  interval: number = 1000,
  maxAttempts: number = 300
): Promise<OutlineTaskStatusResponse> {
  for (let i = 0; i < maxAttempts; i++) {
    const status = await getOutlineTaskStatus(taskId)

    if (status.status === 'finished') {
      return status
    }

    if (status.status === 'failed') {
      throw new Error(status.error || '大纲生成失败')
    }

    // 等待后继续轮询
    await new Promise((resolve) => setTimeout(resolve, interval))
  }

  throw new Error('大纲生成超时')
}

/**
 * 生成大纲（异步版本）
 *
 * 内部创建任务并轮询等待完成，对外保持同步接口不变
 */
export async function generateOutline(
  topic: string,
  images?: File[]
): Promise<OutlineResponse & { has_images?: boolean }> {
  // 创建任务
  const createResult = await createOutlineTask(topic, images)

  if (!createResult.success || !createResult.task_id) {
    return {
      success: false,
      error: createResult.error || '创建大纲任务失败',
    }
  }

  try {
    // 轮询等待完成
    const finalStatus = await pollOutlineTask(createResult.task_id)

    return {
      success: true,
      outline: finalStatus.outline,
      pages: finalStatus.pages,
      has_images: images && images.length > 0,
    }
  } catch (err: any) {
    return {
      success: false,
      error: err.message || '大纲生成失败',
    }
  }
}

// ==================== 图片生成 API ====================

interface ImageTaskResponse {
  success: boolean
  task_id?: string
  status?: string
  error?: string
}

/**
 * 创建图片生成任务
 */
export async function createImageTask(
  pages: Page[],
  fullOutline: string,
  userImages?: File[],
  userTopic?: string,
  taskId?: string | null
): Promise<ImageTaskResponse> {
  // 将用户图片转换为 base64
  let userImagesBase64: string[] = []
  if (userImages && userImages.length > 0) {
    userImagesBase64 = await Promise.all(
      userImages.map(
        (file) =>
          new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(reader.result as string)
            reader.onerror = reject
            reader.readAsDataURL(file)
          })
      )
    )
  }

  const response = await apiClient.post<ImageTaskResponse>('/generate', {
    pages,
    task_id: taskId || undefined,
    full_outline: fullOutline,
    user_images: userImagesBase64.length > 0 ? userImagesBase64 : undefined,
    user_topic: userTopic || '',
  })

  return response.data
}

/**
 * SSE 连接管理器（支持认证失败时自动刷新 token 并重连）
 */
class SSEConnectionManager {
  private eventSource: EventSource | null = null
  private taskId: string
  private onProgress: (event: ProgressEvent) => void
  private onComplete: (event: ProgressEvent) => void
  private onError: (event: ProgressEvent) => void
  private onFinish: (event: FinishEvent) => void
  private onStreamError: (error: Error) => void
  private reconnectAttempts: number = 0
  private maxReconnectAttempts: number = 3
  private isClosed: boolean = false
  private hasReceivedData: boolean = false

  constructor(
    taskId: string,
    onProgress: (event: ProgressEvent) => void,
    onComplete: (event: ProgressEvent) => void,
    onError: (event: ProgressEvent) => void,
    onFinish: (event: FinishEvent) => void,
    onStreamError: (error: Error) => void
  ) {
    this.taskId = taskId
    this.onProgress = onProgress
    this.onComplete = onComplete
    this.onError = onError
    this.onFinish = onFinish
    this.onStreamError = onStreamError
  }

  /**
   * 连接 SSE 流
   */
  connect(): EventSource {
    if (this.isClosed) {
      throw new Error('连接管理器已关闭')
    }

    const userId = getUserId()
    const params = new URLSearchParams({ user_id: userId })

    // 获取最新的 token
    const token = getStoredAccessToken()
    if (token) {
      params.append('access_token', token)
    }

    const url = `${API_BASE_URL}/generate/stream/${this.taskId}?${params.toString()}`
    console.log(`[SSE] 正在连接: ${url} (尝试 ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`)

    const eventSource = new EventSource(url)
    this.eventSource = eventSource

    // 注册事件监听器
    this.setupEventListeners(eventSource)

    return eventSource
  }

  /**
   * 设置 EventSource 事件监听器
   */
  private setupEventListeners(eventSource: EventSource): void {
    eventSource.addEventListener('progress', (e: MessageEvent) => {
      this.hasReceivedData = true
      try {
        const data = JSON.parse(e.data) as ProgressEvent
        this.onProgress(data)
      } catch (err) {
        console.error('[SSE] 解析 progress 事件失败:', err)
      }
    })

    eventSource.addEventListener('complete', (e: MessageEvent) => {
      this.hasReceivedData = true
      try {
        const data = JSON.parse(e.data) as ProgressEvent
        this.onComplete(data)
      } catch (err) {
        console.error('[SSE] 解析 complete 事件失败:', err)
      }
    })

    eventSource.addEventListener('error', (e: MessageEvent) => {
      // 来自服务器的错误事件（非连接错误）
      if (e.data) {
        this.hasReceivedData = true
        try {
          const data = JSON.parse(e.data) as ProgressEvent
          this.onError(data)
        } catch (err) {
          console.error('[SSE] 解析 error 事件失败:', err)
        }
      }
    })

    eventSource.addEventListener('finish', (e: MessageEvent) => {
      this.hasReceivedData = true
      try {
        const data = JSON.parse(e.data) as FinishEvent
        this.onFinish(data)
        this.close()
      } catch (err) {
        console.error('[SSE] 解析 finish 事件失败:', err)
      }
    })

    eventSource.onerror = async (event: Event) => {
      await this.handleConnectionError(eventSource, event)
    }
  }

  /**
   * 处理连接错误
   */
  private async handleConnectionError(eventSource: EventSource, event: Event): Promise<void> {
    const readyState = eventSource.readyState

    console.error('[SSE] 连接错误:', {
      readyState,
      readyStateName: this.getReadyStateName(readyState),
      reconnectAttempts: this.reconnectAttempts,
      hasReceivedData: this.hasReceivedData,
      event
    })

    // 如果正在重连（EventSource 内部重连机制），暂不处理
    if (readyState === EventSource.CONNECTING) {
      console.warn('[SSE] 连接断开，EventSource 正在自动重连...')
      return
    }

    // 连接已关闭（readyState = 2）
    if (readyState === EventSource.CLOSED) {
      console.error('[SSE] 连接已关闭 (readyState=2)')

      // 如果已经收到过数据，说明之前连接是成功的，可能是任务完成或其他正常关闭
      if (this.hasReceivedData) {
        console.log('[SSE] 连接在接收数据后关闭，可能是正常完成')
        this.close()
        return
      }

      // 如果从未收到数据，可能是认证失败或任务不存在
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        console.log('[SSE] 尝试刷新 token 后重连...')

        try {
          // 尝试刷新 token
          const newToken = await this.refreshToken()

          if (newToken) {
            console.log('[SSE] Token 刷新成功，正在重新连接...')
            this.reconnectAttempts++

            // 关闭旧连接
            try {
              eventSource.close()
            } catch (e) {
              console.warn('[SSE] 关闭旧连接失败:', e)
            }

            // 短暂延迟后重连（避免请求过快）
            await new Promise(resolve => setTimeout(resolve, 1000))

            // 创建新连接
            if (!this.isClosed) {
              this.connect()
            }
            return
          } else {
            console.error('[SSE] Token 刷新失败')
          }
        } catch (err) {
          console.error('[SSE] 刷新 token 时出错:', err)
        }
      }

      // 超过重试次数或无法刷新 token，报告错误
      const errorMessage = this.buildErrorMessage()
      this.onStreamError(new Error(errorMessage))
      this.close()
    }
  }

  /**
   * 刷新访问令牌
   */
  private async refreshToken(): Promise<string | null> {
    try {
      // 延迟导入，避免循环依赖
      const { useAuthStore } = await import('../stores/auth')
      const authStore = useAuthStore()
      return await authStore.refreshToken()
    } catch (err) {
      console.error('[SSE] 刷新 token 失败:', err)
      return null
    }
  }

  /**
   * 构建用户友好的错误消息
   */
  private buildErrorMessage(): string {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      return `SSE 连接失败，已重试 ${this.reconnectAttempts} 次。可能原因：
1. 身份验证已过期，请重新登录
2. 任务不存在或已过期
3. 网络连接不稳定

建议：刷新页面后重试，或检查登录状态`
    }

    return `SSE 连接失败。可能原因：
1. 认证失败，请尝试重新登录
2. 任务不存在或已过期  
3. 网络连接问题

请刷新页面后重试`
  }

  /**
   * 获取 readyState 的可读名称
   */
  private getReadyStateName(state: number): string {
    switch (state) {
      case EventSource.CONNECTING:
        return 'CONNECTING (0)'
      case EventSource.OPEN:
        return 'OPEN (1)'
      case EventSource.CLOSED:
        return 'CLOSED (2)'
      default:
        return `UNKNOWN (${state})`
    }
  }

  /**
   * 关闭连接
   */
  close(): void {
    this.isClosed = true
    if (this.eventSource) {
      try {
        this.eventSource.close()
        console.log('[SSE] 连接已关闭')
      } catch (err) {
        console.warn('[SSE] 关闭连接时出错:', err)
      }
      this.eventSource = null
    }
  }

  /**
   * 获取当前的 EventSource 实例
   */
  getEventSource(): EventSource | null {
    return this.eventSource
  }
}

/**
 * 订阅图片生成任务事件（SSE）
 *
 * 使用 EventSource 订阅 Redis Pub/Sub 事件
 * 
 * 新特性：
 * - 自动检测 token 过期并刷新
 * - 智能重连机制（最多 3 次）
 * - 详细的错误日志和用户提示
 */
export async function subscribeImageTask(
  taskId: string,
  onProgress: (event: ProgressEvent) => void,
  onComplete: (event: ProgressEvent) => void,
  onError: (event: ProgressEvent) => void,
  onFinish: (event: FinishEvent) => void,
  onStreamError: (error: Error) => void
): Promise<EventSource> {
  // 在建立连接前，确保 token 有效（如果即将过期则刷新）
  try {
    await ensureValidToken()
    console.log('[SSE] Token 验证完成，准备建立连接')
  } catch (err) {
    console.warn('[SSE] Token 预检失败，仍尝试连接:', err)
  }

  const manager = new SSEConnectionManager(
    taskId,
    onProgress,
    onComplete,
    onError,
    onFinish,
    onStreamError
  )

  return manager.connect()
}

/**
 * 生成图片（兼容旧接口）
 *
 * 内部创建任务并订阅 SSE 事件
 */
export async function generateImagesPost(
  pages: Page[],
  taskId: string | null,
  fullOutline: string,
  onProgress: (event: ProgressEvent) => void,
  onComplete: (event: ProgressEvent) => void,
  onError: (event: ProgressEvent) => void,
  onFinish: (event: FinishEvent) => void,
  onStreamError: (error: Error) => void,
  userImages?: File[],
  userTopic?: string
): Promise<EventSource | null> {
  try {
    // 创建任务
    const createResult = await createImageTask(pages, fullOutline, userImages, userTopic, taskId)

    if (!createResult.success || !createResult.task_id) {
      onStreamError(new Error(createResult.error || '创建图片任务失败'))
      return null
    }

    // 订阅 SSE 事件（建立连接前会自动校验 token）
    return await subscribeImageTask(
      createResult.task_id,
      onProgress,
      onComplete,
      onError,
      onFinish,
      onStreamError
    )
  } catch (err: any) {
    onStreamError(err)
    return null
  }
}

// ==================== 旧版 SSE 接口（保留兼容） ====================

/**
 * @deprecated 使用 generateImagesPost 代替
 */
export function generateImages(
  pages: Page[],
  taskId: string | null,
  onProgress: (event: ProgressEvent) => void,
  onComplete: (event: ProgressEvent) => void,
  onError: (event: ProgressEvent) => void,
  onFinish: (event: FinishEvent) => void,
  onStreamError: (error: Error) => void
) {
  const eventSource = new EventSource(
    `${API_BASE_URL}/generate?pages=${encodeURIComponent(JSON.stringify(pages))}&task_id=${taskId || ''}`
  )

  eventSource.addEventListener('progress', (e: MessageEvent) => {
    const data = JSON.parse(e.data) as ProgressEvent
    onProgress(data)
  })

  eventSource.addEventListener('complete', (e: MessageEvent) => {
    const data = JSON.parse(e.data) as ProgressEvent
    onComplete(data)
  })

  eventSource.addEventListener('error', (e: MessageEvent) => {
    const data = JSON.parse(e.data) as ProgressEvent
    onError(data)
  })

  eventSource.addEventListener('finish', (e: MessageEvent) => {
    const data = JSON.parse(e.data) as FinishEvent
    onFinish(data)
    eventSource.close()
  })

  eventSource.onerror = () => {
    onStreamError(new Error('SSE 连接错误'))
    eventSource.close()
  }

  return eventSource
}

// ==================== 图片操作 API ====================

// 获取图片 URL
export function getImageUrl(filename: string): string {
  return `${API_BASE_URL}/images/${filename}`
}

// 重试单张图片
export async function retrySingleImage(
  taskId: string,
  page: Page,
  useReference: boolean = true
): Promise<{ success: boolean; index: number; image_url?: string; error?: string }> {
  const response = await apiClient.post('/retry', {
    task_id: taskId,
    page,
    use_reference: useReference,
  })
  return response.data
}

// 重新生成图片（即使成功的也可以重新生成）
export async function regenerateImage(
  taskId: string,
  page: Page,
  useReference: boolean = true
): Promise<{ success: boolean; index: number; image_url?: string; error?: string }> {
  const response = await apiClient.post('/regenerate', {
    task_id: taskId,
    page,
    use_reference: useReference,
  })
  return response.data
}

// 批量重试失败的图片（SSE）
export async function retryFailedImages(
  taskId: string,
  pages: Page[],
  onProgress: (event: ProgressEvent) => void,
  onComplete: (event: ProgressEvent) => void,
  onError: (event: ProgressEvent) => void,
  onFinish: (event: { success: boolean; total: number; completed: number; failed: number }) => void,
  onStreamError: (error: Error) => void
) {
  try {
    const response = await fetch(`${API_BASE_URL}/retry-failed`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': getUserId(),
      },
      body: JSON.stringify({
        task_id: taskId,
        pages,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('无法读取响应流')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()

      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.trim()) continue

        const [eventLine, dataLine] = line.split('\n')
        if (!eventLine || !dataLine) continue

        const eventType = eventLine.replace('event: ', '').trim()
        const eventData = dataLine.replace('data: ', '').trim()

        try {
          const data = JSON.parse(eventData)

          switch (eventType) {
            case 'retry_start':
              onProgress({ index: -1, status: 'generating', message: data.message })
              break
            case 'complete':
              onComplete(data)
              break
            case 'error':
              onError(data)
              break
            case 'retry_finish':
              onFinish(data)
              break
          }
        } catch (e) {
          console.error('解析 SSE 数据失败:', e)
        }
      }
    }
  } catch (error) {
    onStreamError(error as Error)
  }
}

// ==================== 历史记录相关 API ====================

export interface HistoryRecord {
  id: string
  title: string
  created_at: string
  updated_at: string
  status: string
  thumbnail: string | null
  page_count: number
}

export interface HistoryDetail {
  id: string
  title: string
  created_at: string
  updated_at: string
  outline: {
    raw: string
    pages: Page[]
  }
  images: {
    task_id: string | null
    generated: string[]
  }
  status: string
  thumbnail: string | null
}

// 创建历史记录
export async function createHistory(
  topic: string,
  outline: { raw: string; pages: Page[] },
  taskId?: string
): Promise<{ success: boolean; record_id?: string; error?: string }> {
  const response = await apiClient.post('/history', {
    topic,
    outline,
    task_id: taskId,
  })
  return response.data
}

// 获取历史记录列表
export async function getHistoryList(
  page: number = 1,
  pageSize: number = 20,
  status?: string
): Promise<{
  success: boolean
  records: HistoryRecord[]
  total: number
  page: number
  page_size: number
  total_pages: number
}> {
  const params: Record<string, any> = { page, page_size: pageSize }
  if (status) params.status = status

  const response = await apiClient.get('/history', { params })
  return response.data
}

// 获取历史记录详情
export async function getHistory(recordId: string): Promise<{
  success: boolean
  record?: HistoryDetail
  error?: string
}> {
  const response = await apiClient.get(`/history/${recordId}`)
  return response.data
}

// 更新历史记录
export async function updateHistory(
  recordId: string,
  data: {
    outline?: { raw: string; pages: Page[] }
    images?: { task_id: string | null; generated: string[] }
    status?: string
    thumbnail?: string
  }
): Promise<{ success: boolean; error?: string }> {
  const response = await apiClient.put(`/history/${recordId}`, data)
  return response.data
}

// 删除历史记录
export async function deleteHistory(recordId: string): Promise<{
  success: boolean
  error?: string
}> {
  const response = await apiClient.delete(`/history/${recordId}`)
  return response.data
}

// 搜索历史记录
export async function searchHistory(keyword: string): Promise<{
  success: boolean
  records: HistoryRecord[]
}> {
  const response = await apiClient.get('/history/search', {
    params: { keyword },
  })
  return response.data
}

// 获取统计信息
export async function getHistoryStats(): Promise<{
  success: boolean
  total: number
  by_status: Record<string, number>
}> {
  const response = await apiClient.get('/history/stats')
  return response.data
}
