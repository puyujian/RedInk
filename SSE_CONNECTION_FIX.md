# SSE 连接错误修复方案

## 📋 问题概述

**错误现象：**
- 错误文件：`index-kdTRLhbS.js:42`
- EventSource readyState: 2 (CLOSED - 连接已关闭)
- 错误URL：`https://hscz.yujian.de/api/generate/stream/[token]`
- 错误提示：SSE 连接失败，可能是认证失败、任务不存在或网络问题

## 🔍 根本原因分析

### 1. **Token 过期导致认证失败** ⭐⭐⭐⭐⭐ (最常见)

**原因：**
- SSE 连接通过 URL 参数传递 `access_token`（因为 EventSource API 无法发送自定义 headers）
- 当 token 过期时，后端 `@login_required` 装饰器返回 401 错误
- EventSource 收到非 2xx 响应后立即将 readyState 设为 2 (CLOSED) 并触发 onerror

**典型场景：**
```
1. 用户登录，获得 access_token（有效期 1 小时）
2. 50 分钟后，用户开始生成图片
3. 创建 SSE 连接时，token 还有 10 分钟有效期
4. 但在图片生成过程中或重连时，token 已过期
5. 新的 SSE 连接请求被后端拒绝 (401)
6. EventSource readyState = 2，连接关闭
```

### 2. **Token 刷新时机不当** ⭐⭐⭐⭐

**原因：**
- axios 拦截器可以在 401 时自动刷新 token 并重试
- 但 SSE 连接一旦建立，无法中途更新 URL 中的 token
- 旧的 EventSource 实现没有重连和 token 刷新逻辑

### 3. **缺乏智能重连机制** ⭐⭐⭐

**原因：**
- EventSource 自带的重连机制只对网络错误生效
- 对于 HTTP 错误（如 401、404）会立即关闭，不重连
- 旧代码在 onerror 中直接关闭连接，没有重试逻辑

### 4. **错误处理不够细致** ⭐⭐

**原因：**
- 无法区分认证失败、任务不存在、网络错误等不同情况
- 给用户的错误提示不够精确
- 缺少详细的调试日志

---

## ✅ 实施的修复方案

### 1. **SSE 连接管理器 (SSEConnectionManager)**

创建了一个智能连接管理类，提供：

#### a. **自动 Token 刷新 + 重连**
```typescript
// 在 onerror 中检测 readyState=2 且未收到数据
if (readyState === EventSource.CLOSED && !this.hasReceivedData) {
  // 尝试刷新 token
  const newToken = await this.refreshToken()
  
  if (newToken) {
    // 关闭旧连接，创建新连接
    eventSource.close()
    await delay(1000)
    this.connect() // 使用新 token 重连
  }
}
```

#### b. **重连次数限制**
- 最多重试 3 次
- 避免无限重连造成资源浪费
- 每次重连间隔 1 秒

#### c. **智能错误判断**
- 区分正常关闭（已收到数据）和异常关闭（未收到数据）
- 已收到数据后关闭：认为是任务完成，正常退出
- 未收到数据就关闭：认为是认证/任务问题，尝试重连

#### d. **详细日志输出**
```typescript
console.error('[SSE] 连接错误:', {
  readyState: 2,
  readyStateName: 'CLOSED (2)',
  reconnectAttempts: 1,
  hasReceivedData: false,
  event
})
```

### 2. **连接前主动 Token 检查**

添加 `ensureValidToken()` 函数：

```typescript
export async function ensureValidToken(): Promise<string | null> {
  const currentToken = getStoredAccessToken()
  
  if (!currentToken) return null
  
  // 检查 token 是否即将过期（5分钟内）
  if (isTokenExpiringSoon(currentToken)) {
    console.log('[Auth] Token 即将过期，正在刷新...')
    const result = await refresh()
    return result.access_token || null
  }
  
  return currentToken
}
```

#### 使用场景：
```typescript
// 在创建 SSE 连接前
await ensureValidToken()  // 如果 token 快过期，先刷新
const eventSource = new EventSource(url)
```

### 3. **Token 过期判断工具**

添加 JWT 解析和过期检查：

```typescript
// 解析 JWT payload（不验证签名）
export function decodeToken(token: string): any | null {
  const parts = token.split('.')
  const payload = atob(parts[1])
  return JSON.parse(payload)
}

// 检查是否即将过期（默认阈值：5分钟）
export function isTokenExpiringSoon(
  token: string | null, 
  thresholdSeconds: number = 300
): boolean {
  if (!token) return true
  
  const payload = decodeToken(token)
  if (!payload?.exp) return true
  
  const now = Math.floor(Date.now() / 1000)
  const remainingSeconds = payload.exp - now
  
  return remainingSeconds < thresholdSeconds
}
```

### 4. **改进的错误消息**

```typescript
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
```

---

## 🧪 如何调试和验证修复效果

### 1. **查看浏览器控制台日志**

修复后，你会看到详细的 SSE 连接日志：

```
✅ 正常流程：
[Auth] Token 验证完成，准备建立连接
[SSE] 正在连接: /api/generate/stream/abc123?... (尝试 1/3)
[SSE] 连接已关闭

❌ Token 过期场景：
[Auth] Token 即将过期，正在刷新...
[Auth] Token 刷新成功
[SSE] 正在连接: /api/generate/stream/abc123?... (尝试 1/3)
[SSE] 连接错误: { readyState: 2, readyStateName: 'CLOSED (2)', ... }
[SSE] 连接已关闭 (readyState=2)
[SSE] 尝试刷新 token 后重连...
[SSE] Token 刷新成功，正在重新连接...
[SSE] 正在连接: /api/generate/stream/abc123?... (尝试 2/3)
```

### 2. **使用浏览器开发者工具**

#### Network 面板：
1. 筛选 "EventStream" 类型的请求
2. 检查 `/api/generate/stream/xxx` 请求的状态码
   - **200**: 连接成功
   - **401**: 认证失败（应触发重连）
   - **404**: 任务不存在
   - **403**: 权限不足

3. 查看请求头中的 `access_token` 参数
   - 复制 token 到 [jwt.io](https://jwt.io) 查看过期时间

#### Console 面板：
- 查找 `[SSE]` 开头的日志
- 查找 `[Auth]` 开头的日志
- 检查是否有刷新 token 的记录

### 3. **模拟 Token 过期场景**

#### 方法 1：修改 JWT 过期时间（后端）
```python
# backend/config.py
JWT_ACCESS_EXPIRES = 60  # 改为 60 秒（仅测试）
```

#### 方法 2：手动修改 localStorage（前端）
```javascript
// 浏览器控制台执行
const token = localStorage.getItem('redink_access_token')
console.log('当前 token:', token)

// 强制设置一个过期的 token（修改 exp 字段）
const expiredToken = 'eyJ...'  // 一个已过期的 token
localStorage.setItem('redink_access_token', expiredToken)
```

#### 方法 3：删除 token 测试未登录场景
```javascript
localStorage.removeItem('redink_access_token')
location.reload()
```

### 4. **监控重连行为**

打开控制台后，执行生成任务：

```
预期行为：
1. 首次连接失败 → 日志显示 readyState=2
2. 自动刷新 token → 日志显示 "Token 刷新成功"
3. 自动重连 → 日志显示 "尝试 2/3"
4. 连接成功 → 开始接收 SSE 事件（progress、complete、finish）
```

### 5. **测试不同错误场景**

#### a. **认证失败（401）**
- 手动使 token 失效
- 预期：自动刷新 token 并重连

#### b. **任务不存在（404）**
- 使用错误的 task_id
- 预期：重试 3 次后显示错误

#### c. **网络中断**
- 开发者工具 → Network → Offline
- 预期：EventSource 自动重连（readyState=0）

#### d. **长时间运行**
- 生成 10+ 张图片（耗时 > 1 小时）
- 预期：中途 token 过期时自动刷新

---

## 🎯 用户指南

### 遇到 SSE 连接错误时的处理步骤

1. **打开浏览器控制台** (F12)
2. **查看 Console 面板**，搜索 `[SSE]` 或 `readyState`
3. **根据日志判断原因：**

   #### 情况 1：看到 "Token 刷新成功" → 自动修复
   ```
   ✅ 无需操作，系统已自动处理
   ```

   #### 情况 2：看到 "Token 刷新失败" → 需要重新登录
   ```
   ❌ 点击右上角退出，重新登录
   ```

   #### 情况 3：看到 "已重试 3 次" → 检查网络或任务状态
   ```
   ❌ 刷新页面，或检查网络连接
   ```

   #### 情况 4：没有看到 [SSE] 日志 → 检查是否使用旧代码
   ```
   ⚠️ 清除缓存后刷新页面 (Ctrl+Shift+R)
   ```

---

## 📝 关键代码位置

### 前端代码

#### 1. SSE 连接管理器
- **文件**: `frontend/src/api/index.ts`
- **类**: `SSEConnectionManager` (第 318-576 行)
- **功能**: 处理连接、重连、错误处理

#### 2. Token 工具函数
- **文件**: `frontend/src/api/auth.ts`
- **函数**: 
  - `decodeToken()` (第 267-284 行)
  - `isTokenExpiringSoon()` (第 287-304 行)
  - `ensureValidToken()` (第 306-343 行)

#### 3. 订阅函数
- **文件**: `frontend/src/api/index.ts`
- **函数**: `subscribeImageTask()` (第 578-614 行)
- **改动**: 添加了连接前的 token 预检

### 后端代码

#### 1. SSE 端点
- **文件**: `backend/routes/api.py`
- **函数**: `stream_image_task()` (第 242-461 行)
- **装饰器**: `@login_required`

#### 2. 认证逻辑
- **文件**: `backend/auth.py`
- **函数**: 
  - `load_current_user()` (第 150-197 行) - 支持从 URL 参数读取 token
  - `login_required` (第 236-256 行) - 装饰器

---

## 🚀 未来优化建议

1. **后端改进：**
   - 在 SSE 连接失败时，返回特定的错误事件而不是直接关闭
   - 添加心跳机制，检测连接是否仍然活跃
   - 支持在 URL 中传递 `last_event_id`，实现断点续传

2. **前端改进：**
   - 添加可视化的重连提示（而不仅仅是控制台日志）
   - 支持手动重连按钮
   - 记录重连历史，用于问题诊断

3. **监控告警：**
   - 统计 SSE 连接失败率
   - 监控 token 刷新成功率
   - 记录平均重连次数

---

## ✨ 测试清单

- [ ] Token 未过期时，SSE 连接正常建立
- [ ] Token 即将过期时，自动刷新后建立连接
- [ ] Token 已过期时，SSE 连接失败后自动刷新并重连
- [ ] Token 刷新失败时，显示友好错误消息
- [ ] 重连次数达到上限后，停止重连并报错
- [ ] 网络中断时，EventSource 自动重连
- [ ] 任务不存在时（404），不会无限重连
- [ ] 任务完成后，连接正常关闭
- [ ] 控制台日志完整且易于理解
- [ ] 错误消息对用户友好且可操作

---

## 📞 技术支持

如果修复后仍然遇到问题，请提供以下信息：

1. **浏览器控制台完整日志**（包含 [SSE] 和 [Auth] 开头的所有行）
2. **Network 面板截图**（SSE 请求的状态码和响应头）
3. **复现步骤**（如何触发错误）
4. **用户登录状态**（是否登录、登录时长）
5. **Token 信息**（复制 access_token 到 jwt.io 查看过期时间）

---

**修复完成时间**: 2024-11-26  
**修复版本**: v1.1.0  
**影响范围**: 所有使用 SSE 的图片生成功能
