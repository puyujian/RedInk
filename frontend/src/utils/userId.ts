/**
 * 用户 ID 管理工具
 *
 * 为多用户隔离提供客户端唯一标识符。
 * ID 存储在 localStorage 中，跨会话持久化。
 */

const USER_ID_KEY = 'redink_user_id'

/**
 * 生成 UUID v4
 */
function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/**
 * 获取或创建用户 ID
 *
 * 首次访问时生成新 ID 并存储到 localStorage
 * 后续访问返回已存储的 ID
 */
export function getUserId(): string {
  let userId = localStorage.getItem(USER_ID_KEY)

  if (!userId) {
    userId = generateUUID()
    localStorage.setItem(USER_ID_KEY, userId)
  }

  return userId
}

/**
 * 清除用户 ID（用于测试或重置）
 */
export function clearUserId(): void {
  localStorage.removeItem(USER_ID_KEY)
}
