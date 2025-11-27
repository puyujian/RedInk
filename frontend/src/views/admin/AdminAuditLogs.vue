<template>
  <div class="admin-audit-logs">
    <!-- 筛选工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <select v-model="filterAction" class="filter-select" @change="fetchLogs">
          <option value="">所有操作</option>
          <option value="create_user">创建用户</option>
          <option value="update_user">更新用户</option>
          <option value="delete_user">删除用户</option>
          <option value="update_user_status">更新用户状态</option>
          <option value="delete_record">删除记录</option>
          <option value="delete_image">删除图片</option>
          <option value="update_config">更新配置</option>
          <option value="rollback_config">回滚配置</option>
          <option value="update_registration">更新注册设置</option>
        </select>
        <select v-model="filterResourceType" class="filter-select" @change="fetchLogs">
          <option value="">所有资源</option>
          <option value="user">用户</option>
          <option value="history_record">生成记录</option>
          <option value="image_file">图片</option>
          <option value="config">配置</option>
          <option value="registration">注册设置</option>
        </select>
        <input
          v-model="filterActorId"
          type="number"
          placeholder="操作者ID"
          class="filter-input"
          @change="fetchLogs"
        />
      </div>
      <div class="toolbar-right">
        <button class="btn btn-secondary" @click="fetchLogs">
          🔄 刷新
        </button>
      </div>
    </div>

    <!-- 桌面端日志表格 -->
    <div class="table-container desktop-only">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>操作类型</th>
            <th>资源类型</th>
            <th>资源ID</th>
            <th>操作者</th>
            <th>IP地址</th>
            <th>时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.id">
            <td>{{ log.id }}</td>
            <td>
              <span :class="['action-badge', getActionClass(log.action)]">
                {{ actionLabels[log.action] || log.action }}
              </span>
            </td>
            <td>{{ resourceLabels[log.resource_type] || log.resource_type }}</td>
            <td>{{ log.resource_id || '-' }}</td>
            <td>{{ log.actor_username || `用户#${log.actor_id}` }}</td>
            <td>{{ log.ip_address || '-' }}</td>
            <td>{{ formatDate(log.created_at) }}</td>
            <td>
              <button
                v-if="log.details"
                class="btn-action btn-view"
                title="查看详情"
                @click="viewDetails(log)"
              >
                👁️
              </button>
            </td>
          </tr>
          <tr v-if="logs.length === 0 && !loading">
            <td colspan="8" class="empty-row">暂无审计日志</td>
          </tr>
        </tbody>
      </table>

      <div v-if="loading" class="loading-overlay">
        <div class="loading-spinner"></div>
      </div>
    </div>

    <!-- 移动端卡片视图 -->
    <div class="mobile-cards mobile-only">
      <div
        v-for="log in logs"
        :key="log.id"
        class="log-card"
      >
        <div class="log-card-header">
          <span :class="['action-badge', getActionClass(log.action)]">
            {{ actionLabels[log.action] || log.action }}
          </span>
          <span class="log-time">{{ formatDateShort(log.created_at) }}</span>
        </div>
        <div class="log-card-body">
          <div class="log-info-row">
            <span class="log-label">资源类型</span>
            <span class="log-value">{{ resourceLabels[log.resource_type] || log.resource_type }}</span>
          </div>
          <div class="log-info-row">
            <span class="log-label">资源ID</span>
            <span class="log-value">{{ log.resource_id || '-' }}</span>
          </div>
          <div class="log-info-row">
            <span class="log-label">操作者</span>
            <span class="log-value">{{ log.actor_username || `用户#${log.actor_id}` }}</span>
          </div>
          <div class="log-info-row">
            <span class="log-label">IP地址</span>
            <span class="log-value log-ip">{{ log.ip_address || '-' }}</span>
          </div>
        </div>
        <div class="log-card-footer" v-if="log.details">
          <button
            class="btn-card-detail"
            @click="viewDetails(log)"
          >
            👁️ 查看详情
          </button>
        </div>
      </div>

      <!-- 移动端空状态 -->
      <div v-if="logs.length === 0 && !loading" class="empty-state-mobile">
        <span class="empty-icon">📋</span>
        <span>暂无审计日志</span>
      </div>

      <!-- 移动端加载状态 -->
      <div v-if="loading" class="loading-container-mobile">
        <div class="loading-spinner"></div>
        <span>加载中...</span>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination" v-if="totalPages > 1">
      <button
        class="btn-page"
        :disabled="currentPage <= 1"
        @click="goToPage(currentPage - 1)"
      >
        上一页
      </button>
      <span class="page-info">第 {{ currentPage }} / {{ totalPages }} 页</span>
      <button
        class="btn-page"
        :disabled="currentPage >= totalPages"
        @click="goToPage(currentPage + 1)"
      >
        下一页
      </button>
    </div>

    <!-- 详情弹窗 -->
    <div v-if="detailLog" class="modal-overlay" @click.self="detailLog = null">
      <div class="modal">
        <div class="modal-header">
          <h3>操作详情</h3>
          <button class="btn-close" @click="detailLog = null">×</button>
        </div>
        <div class="modal-body">
          <div class="detail-grid">
            <div class="detail-item">
              <label>操作类型</label>
              <span>{{ actionLabels[detailLog.action] || detailLog.action }}</span>
            </div>
            <div class="detail-item">
              <label>资源类型</label>
              <span>{{ resourceLabels[detailLog.resource_type] || detailLog.resource_type }}</span>
            </div>
            <div class="detail-item">
              <label>资源ID</label>
              <span>{{ detailLog.resource_id || '-' }}</span>
            </div>
            <div class="detail-item">
              <label>操作者</label>
              <span>{{ detailLog.actor_username || `用户#${detailLog.actor_id}` }}</span>
            </div>
            <div class="detail-item">
              <label>IP地址</label>
              <span>{{ detailLog.ip_address || '-' }}</span>
            </div>
            <div class="detail-item">
              <label>操作时间</label>
              <span>{{ formatDate(detailLog.created_at) }}</span>
            </div>
          </div>
          <div class="detail-section" v-if="detailLog.details">
            <h4>详细信息</h4>
            <pre class="detail-json">{{ formatDetails(detailLog.details) }}</pre>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="detailLog = null">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-toast">
      {{ error }}
      <button @click="error = ''">×</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAuditLogs, type AuditLogEntry } from '@/api/admin'

const loading = ref(false)
const error = ref('')
const logs = ref<AuditLogEntry[]>([])
const currentPage = ref(1)
const totalPages = ref(1)
const pageSize = 30

const filterAction = ref('')
const filterResourceType = ref('')
const filterActorId = ref<number | ''>('')

const detailLog = ref<AuditLogEntry | null>(null)

const actionLabels: Record<string, string> = {
  create_user: '创建用户',
  update_user: '更新用户',
  delete_user: '删除用户',
  update_user_status: '更新用户状态',
  delete_record: '删除记录',
  batch_delete_records: '批量删除记录',
  delete_image: '删除图片',
  batch_delete_images: '批量删除图片',
  update_config: '更新配置',
  rollback_config: '回滚配置',
  update_registration: '更新注册设置',
}

const resourceLabels: Record<string, string> = {
  user: '用户',
  history_record: '生成记录',
  image_file: '图片',
  config: '配置',
  registration: '注册设置',
}

function getActionClass(action: string): string {
  if (action.includes('delete')) return 'action-danger'
  if (action.includes('create')) return 'action-success'
  if (action.includes('update') || action.includes('rollback')) return 'action-warning'
  return ''
}

async function fetchLogs() {
  loading.value = true
  error.value = ''
  try {
    const response = await getAuditLogs({
      page: currentPage.value,
      per_page: pageSize,
      action: filterAction.value || undefined,
      resource_type: filterResourceType.value || undefined,
      actor_id: filterActorId.value ? Number(filterActorId.value) : undefined,
    })
    if (response.success) {
      logs.value = response.items || []
      totalPages.value = response.pages || 1
    } else {
      error.value = response.error || '获取审计日志失败'
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    loading.value = false
  }
}

function goToPage(page: number) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    fetchLogs()
  }
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatDateShort(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2)
}

function viewDetails(log: AuditLogEntry) {
  detailLog.value = log
}

onMounted(() => {
  fetchLogs()
})
</script>

<style scoped>
.admin-audit-logs {
  position: relative;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  gap: 16px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-select {
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  background: #fff;
  min-width: 140px;
}

.filter-input {
  width: 100px;
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-secondary {
  background: #f3f4f6;
  color: #374151;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.table-container {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  position: relative;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.data-table th {
  background: #f9fafb;
  font-weight: 600;
  color: #374151;
  font-size: 13px;
}

.data-table td {
  font-size: 14px;
  color: #1a1a2e;
}

.data-table tbody tr:hover {
  background: #f9fafb;
}

.empty-row {
  text-align: center !important;
  color: #9ca3af;
  padding: 48px !important;
}

.action-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
  background: #e5e7eb;
  color: #374151;
}

.action-success {
  background: #d1fae5;
  color: #059669;
}

.action-warning {
  background: #fef3c7;
  color: #d97706;
}

.action-danger {
  background: #fee2e2;
  color: #dc2626;
}

.btn-action {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-view {
  background: #e0e7ff;
}

.btn-view:hover {
  background: #c7d2fe;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-top: 24px;
}

.btn-page {
  padding: 8px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
}

.btn-page:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  color: #6b7280;
  font-size: 14px;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e5e7eb;
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #fff;
  border-radius: 16px;
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
}

.btn-close {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  font-size: 24px;
  color: #9ca3af;
  cursor: pointer;
  border-radius: 6px;
}

.btn-close:hover {
  background: #f3f4f6;
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-item label {
  font-size: 12px;
  color: #6b7280;
  text-transform: uppercase;
}

.detail-item span {
  font-size: 14px;
  color: #1a1a2e;
}

.detail-section {
  margin-top: 24px;
}

.detail-section h4 {
  font-size: 14px;
  color: #374151;
  margin: 0 0 12px 0;
}

.detail-json {
  background: #f9fafb;
  padding: 16px;
  border-radius: 8px;
  font-size: 13px;
  font-family: 'Monaco', 'Menlo', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.error-toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: #fef2f2;
  color: #dc2626;
  padding: 16px 24px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  display: flex;
  align-items: center;
  gap: 16px;
  z-index: 1001;
}

.error-toast button {
  background: none;
  border: none;
  font-size: 18px;
  color: #dc2626;
  cursor: pointer;
}

/* ==================== 移动端视图切换 ==================== */
.desktop-only {
  display: block;
}

.mobile-only {
  display: none;
}

/* ==================== 移动端卡片样式 ==================== */
.mobile-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.log-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.log-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.log-time {
  font-size: 12px;
  color: #9ca3af;
}

.log-card-body {
  padding: 14px 16px;
}

.log-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f3f4f6;
}

.log-info-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.log-info-row:first-child {
  padding-top: 0;
}

.log-label {
  font-size: 13px;
  color: #6b7280;
}

.log-value {
  font-size: 14px;
  color: #1a1a2e;
  font-weight: 500;
}

.log-ip {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 12px;
}

.log-card-footer {
  padding: 12px 16px;
  border-top: 1px solid #e5e7eb;
}

.btn-card-detail {
  width: 100%;
  padding: 10px 16px;
  background: #e0e7ff;
  color: #4338ca;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: background 0.2s;
}

.btn-card-detail:hover {
  background: #c7d2fe;
}

.empty-state-mobile {
  text-align: center;
  padding: 60px 20px;
  color: #9ca3af;
}

.empty-state-mobile .empty-icon {
  display: block;
  font-size: 48px;
  margin-bottom: 16px;
}

.loading-container-mobile {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 20px;
  gap: 16px;
  color: #6b7280;
}

/* ==================== 响应式布局 ==================== */

/* 平板适配 */
@media (max-width: 1024px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .toolbar-left {
    flex-wrap: wrap;
  }

  .filter-select {
    flex: 1;
    min-width: 120px;
  }

  .toolbar-right {
    display: flex;
    justify-content: flex-end;
  }
}

/* 移动端适配 */
@media (max-width: 768px) {
  /* 视图切换 */
  .desktop-only {
    display: none !important;
  }

  .mobile-only {
    display: block !important;
  }

  /* 工具栏 */
  .toolbar {
    margin-bottom: 16px;
  }

  .toolbar-left {
    gap: 8px;
  }

  .filter-select {
    flex: 1;
    min-width: 0;
    padding: 12px 14px;
    font-size: 13px;
  }

  .filter-input {
    width: 80px;
    padding: 12px 14px;
    font-size: 13px;
  }

  .toolbar-right {
    width: 100%;
  }

  .toolbar-right .btn {
    width: 100%;
    justify-content: center;
  }

  /* 分页 */
  .pagination {
    gap: 12px;
    margin-top: 20px;
  }

  .btn-page {
    padding: 10px 14px;
    font-size: 13px;
  }

  .page-info {
    font-size: 13px;
  }

  /* 弹窗底部抽屉样式 */
  .modal-overlay {
    align-items: flex-end;
  }

  .modal {
    width: 100% !important;
    max-width: 100% !important;
    max-height: 85vh;
    border-radius: 16px 16px 0 0;
    margin: 0;
  }

  .modal-header {
    padding: 16px 20px;
  }

  .modal-header h3 {
    font-size: 16px;
  }

  .modal-body {
    padding: 16px 20px;
  }

  .modal-footer {
    padding: 12px 20px 20px;
  }

  .modal-footer .btn {
    width: 100%;
    justify-content: center;
    padding: 12px 20px;
  }

  /* 详情弹窗 */
  .detail-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .detail-json {
    font-size: 12px;
    max-height: 200px;
  }

  /* 错误提示 */
  .error-toast {
    left: 16px;
    right: 16px;
    bottom: 16px;
    padding: 14px 16px;
    font-size: 13px;
  }
}

/* 小屏手机适配 */
@media (max-width: 480px) {
  .log-card {
    border-radius: 10px;
  }

  .log-card-header {
    padding: 12px 14px;
  }

  .log-card-body {
    padding: 12px 14px;
  }

  .log-info-row {
    padding: 6px 0;
  }

  .log-label {
    font-size: 12px;
  }

  .log-value {
    font-size: 13px;
  }

  .log-card-footer {
    padding: 10px 14px;
  }

  .btn-card-detail {
    padding: 8px 14px;
    font-size: 12px;
  }

  .action-badge {
    padding: 3px 8px;
    font-size: 11px;
  }

  .pagination {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
