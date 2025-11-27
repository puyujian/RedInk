<template>
  <div class="admin-records">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索标题..."
          class="search-input"
          @input="debouncedSearch"
        />
        <select v-model="filterStatus" class="filter-select" @change="fetchRecords">
          <option value="">所有状态</option>
          <option value="completed">已完成</option>
          <option value="generating">生成中</option>
          <option value="draft">草稿</option>
          <option value="partial">部分完成</option>
        </select>
        <input
          v-model="filterUserId"
          type="number"
          placeholder="用户ID"
          class="filter-input"
          @change="fetchRecords"
        />
      </div>
      <div class="toolbar-right">
        <button
          v-if="selectedIds.length > 0"
          class="btn btn-danger"
          @click="confirmBatchDelete"
        >
          批量删除 ({{ selectedIds.length }})
        </button>
      </div>
    </div>

    <!-- 桌面端表格视图 -->
    <div class="table-container desktop-only">
      <table class="data-table">
        <thead>
          <tr>
            <th class="checkbox-col">
              <input
                type="checkbox"
                :checked="isAllSelected"
                @change="toggleSelectAll"
              />
            </th>
            <th>ID</th>
            <th>标题</th>
            <th>用户</th>
            <th>状态</th>
            <th>页数</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in records" :key="record.id">
            <td class="checkbox-col">
              <input
                type="checkbox"
                :checked="selectedIds.includes(record.id)"
                @change="toggleSelect(record.id)"
              />
            </td>
            <td>{{ record.id }}</td>
            <td>
              <div class="record-title">
                <img
                  v-if="record.thumbnail_url"
                  :src="record.thumbnail_url"
                  class="thumbnail"
                  alt="缩略图"
                />
                <span>{{ record.title }}</span>
              </div>
            </td>
            <td>
              <span v-if="record.user">{{ record.user.username }}</span>
              <span v-else class="text-muted">匿名</span>
            </td>
            <td>
              <span :class="['status-badge', `status-${record.status}`]">
                {{ statusLabels[record.status] || record.status }}
              </span>
            </td>
            <td>{{ record.page_count }}</td>
            <td>{{ formatDate(record.created_at) }}</td>
            <td>
              <div class="action-buttons">
                <button
                  class="btn-action btn-view"
                  title="查看详情"
                  @click="viewRecord(record)"
                >
                  👁️
                </button>
                <button
                  class="btn-action btn-delete"
                  title="删除"
                  @click="confirmDelete(record)"
                >
                  🗑️
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="records.length === 0 && !loading">
            <td colspan="8" class="empty-row">暂无记录数据</td>
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
        v-for="record in records"
        :key="record.id"
        class="record-card"
        :class="{ selected: selectedIds.includes(record.id) }"
        @click="toggleSelect(record.id)"
      >
        <div class="card-checkbox">
          <input
            type="checkbox"
            :checked="selectedIds.includes(record.id)"
            @click.stop
            @change="toggleSelect(record.id)"
          />
        </div>
        <div class="card-header">
          <img
            v-if="record.thumbnail_url"
            :src="record.thumbnail_url"
            class="card-thumbnail"
            alt="缩略图"
          />
          <div v-else class="card-thumbnail-placeholder">📄</div>
          <div class="card-title-section">
            <div class="card-title">{{ record.title }}</div>
            <div class="card-subtitle">
              <span v-if="record.user">{{ record.user.username }}</span>
              <span v-else class="text-muted">匿名</span>
              <span class="separator">·</span>
              <span>{{ record.page_count }} 页</span>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="card-meta">
            <span :class="['status-badge', `status-${record.status}`]">
              {{ statusLabels[record.status] || record.status }}
            </span>
            <span class="card-date">{{ formatDateShort(record.created_at) }}</span>
          </div>
        </div>
        <div class="card-actions">
          <button
            class="btn-card-action btn-view"
            @click.stop="viewRecord(record)"
          >
            👁️ 详情
          </button>
          <button
            class="btn-card-action btn-delete"
            @click.stop="confirmDelete(record)"
          >
            🗑️ 删除
          </button>
        </div>
      </div>

      <!-- 移动端空状态 -->
      <div v-if="records.length === 0 && !loading" class="empty-state-mobile">
        <span class="empty-icon">📝</span>
        <span>暂无记录数据</span>
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

    <!-- 查看详情弹窗 -->
    <div v-if="showDetailModal" class="modal-overlay" @click.self="showDetailModal = false">
      <div class="modal modal-lg">
        <div class="modal-header">
          <h3>记录详情</h3>
          <button class="btn-close" @click="showDetailModal = false">×</button>
        </div>
        <div class="modal-body" v-if="detailRecord">
          <!-- 基本信息 -->
          <div class="detail-grid">
            <div class="detail-item">
              <label>ID</label>
              <span>{{ detailRecord.id }}</span>
            </div>
            <div class="detail-item">
              <label>UUID</label>
              <span class="uuid-text">{{ detailRecord.record_uuid }}</span>
            </div>
            <div class="detail-item">
              <label>标题</label>
              <span>{{ detailRecord.title }}</span>
            </div>
            <div class="detail-item">
              <label>状态</label>
              <span :class="['status-badge', `status-${detailRecord.status}`]">
                {{ statusLabels[detailRecord.status] || detailRecord.status }}
              </span>
            </div>
            <div class="detail-item">
              <label>用户</label>
              <span>{{ detailRecord.user?.username || '匿名' }}</span>
            </div>
            <div class="detail-item">
              <label>页数</label>
              <span>{{ detailRecord.page_count }}</span>
            </div>
            <div class="detail-item">
              <label>创建时间</label>
              <span>{{ formatDate(detailRecord.created_at) }}</span>
            </div>
            <div class="detail-item">
              <label>更新时间</label>
              <span>{{ formatDate(detailRecord.updated_at) }}</span>
            </div>
          </div>

          <!-- 生成的图片 -->
          <div class="detail-section">
            <h4>生成的图片 ({{ getGeneratedImages().length }})</h4>
            <div v-if="getGeneratedImages().length > 0" class="images-grid">
              <div
                v-for="(img, idx) in getGeneratedImages()"
                :key="idx"
                class="image-item"
              >
                <img :src="`/api/images/${img}`" :alt="`Page ${idx + 1}`" loading="lazy" />
                <div class="image-footer">
                  <span>P{{ idx + 1 }}</span>
                  <a :href="`/api/images/${img}`" download class="download-link">下载</a>
                </div>
              </div>
            </div>
            <div v-else class="empty-hint">
              <span>暂无生成的图片</span>
              <span class="hint-sub" v-if="detailRecord.status === 'draft'">（草稿状态，尚未生成）</span>
              <span class="hint-sub" v-else-if="detailRecord.status === 'generating'">（正在生成中...）</span>
            </div>
          </div>

          <!-- 大纲页面 -->
          <div class="detail-section" v-if="getOutlinePages().length > 0">
            <h4>大纲内容 ({{ getOutlinePages().length }} 页)</h4>
            <div class="outline-pages">
              <div
                v-for="(page, idx) in getOutlinePages()"
                :key="idx"
                class="outline-page-card"
              >
                <div class="outline-page-header">
                  <span class="page-badge">P{{ idx + 1 }}</span>
                  <span v-if="page.type" :class="['type-badge', `type-${page.type}`]">
                    {{ getPageTypeName(page.type) }}
                  </span>
                  <span class="word-count">{{ page.content?.length || 0 }} 字</span>
                </div>
                <div class="outline-page-content">{{ page.content }}</div>
              </div>
            </div>
          </div>

          <!-- 原始输入 -->
          <div class="detail-section" v-if="getOutlineRaw()">
            <h4>原始输入</h4>
            <pre class="outline-content">{{ getOutlineRaw() }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteModal" class="modal-overlay" @click.self="showDeleteModal = false">
      <div class="modal modal-sm">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button class="btn-close" @click="showDeleteModal = false">×</button>
        </div>
        <div class="modal-body">
          <p v-if="recordToDelete">
            确定要删除记录 <strong>{{ recordToDelete.title }}</strong> 吗？
          </p>
          <p v-else>
            确定要删除选中的 <strong>{{ selectedIds.length }}</strong> 条记录吗？
          </p>
          <p class="warning-text">此操作不可恢复，相关图片也将被删除。</p>
          <div v-if="deleteError" class="form-error">{{ deleteError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeDeleteModal">取消</button>
          <button
            class="btn btn-danger"
            :disabled="deleteSubmitting"
            @click="deleteRecords"
          >
            {{ deleteSubmitting ? '删除中...' : '确认删除' }}
          </button>
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
import { ref, computed, onMounted } from 'vue'
import {
  getRecords,
  getRecordDetail,
  deleteRecord,
  batchDeleteRecords,
  type AdminRecord,
} from '@/api/admin'

const loading = ref(false)
const error = ref('')
const records = ref<AdminRecord[]>([])
const currentPage = ref(1)
const totalPages = ref(1)
const pageSize = 20

const searchQuery = ref('')
const filterStatus = ref('')
const filterUserId = ref<number | ''>('')

const selectedIds = ref<number[]>([])
const showDetailModal = ref(false)
const detailRecord = ref<AdminRecord | null>(null)
const showDeleteModal = ref(false)
const recordToDelete = ref<AdminRecord | null>(null)
const deleteSubmitting = ref(false)
const deleteError = ref('')

// 用于防止竞态条件的 token
let fetchToken = 0

const statusLabels: Record<string, string> = {
  draft: '草稿',
  generating: '生成中',
  completed: '已完成',
  partial: '部分完成',
}

const isAllSelected = computed(() => {
  return records.value.length > 0 && selectedIds.value.length === records.value.length
})

let searchTimeout: number | null = null
function debouncedSearch() {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = window.setTimeout(() => {
    currentPage.value = 1
    fetchRecords()
  }, 300)
}

async function fetchRecords() {
  // 递增 token 防止竞态条件
  const currentToken = ++fetchToken
  loading.value = true
  error.value = ''
  selectedIds.value = []
  try {
    const response = await getRecords({
      page: currentPage.value,
      per_page: pageSize,
      search: searchQuery.value || undefined,
      status: filterStatus.value || undefined,
      user_id: filterUserId.value ? Number(filterUserId.value) : undefined,
    })
    // 检查是否为最新请求，防止旧请求覆盖新数据
    if (currentToken !== fetchToken) return
    if (response.success) {
      records.value = response.items || []
      totalPages.value = response.pages || 1
    } else {
      error.value = response.error || '获取记录列表失败'
    }
  } catch (e: unknown) {
    if (currentToken !== fetchToken) return
    error.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    if (currentToken === fetchToken) {
      loading.value = false
    }
  }
}

function goToPage(page: number) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    fetchRecords()
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

function toggleSelectAll() {
  if (isAllSelected.value) {
    selectedIds.value = []
  } else {
    selectedIds.value = records.value.map(r => r.id)
  }
}

function toggleSelect(id: number) {
  const index = selectedIds.value.indexOf(id)
  if (index === -1) {
    selectedIds.value.push(id)
  } else {
    selectedIds.value.splice(index, 1)
  }
}

async function viewRecord(record: AdminRecord) {
  try {
    const response = await getRecordDetail(record.id)
    if (response.success && response.record) {
      detailRecord.value = response.record
      showDetailModal.value = true
    } else {
      error.value = response.error || '获取详情失败'
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '网络错误'
  }
}

function confirmDelete(record: AdminRecord) {
  recordToDelete.value = record
  deleteError.value = ''
  showDeleteModal.value = true
}

function confirmBatchDelete() {
  recordToDelete.value = null
  deleteError.value = ''
  showDeleteModal.value = true
}

function closeDeleteModal() {
  showDeleteModal.value = false
  recordToDelete.value = null
  deleteError.value = ''
}

async function deleteRecords() {
  deleteSubmitting.value = true
  deleteError.value = ''
  try {
    if (recordToDelete.value) {
      const response = await deleteRecord(recordToDelete.value.id)
      if (!response.success) {
        deleteError.value = response.error || '删除失败'
        return
      }
    } else if (selectedIds.value.length > 0) {
      const response = await batchDeleteRecords(selectedIds.value)
      if (!response.success) {
        deleteError.value = response.error || '批量删除失败'
        return
      }
    }
    closeDeleteModal()
    fetchRecords()
  } catch (e: unknown) {
    deleteError.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    deleteSubmitting.value = false
  }
}

// 获取生成的图片列表
function getGeneratedImages(): string[] {
  if (!detailRecord.value) return []

  // 优先从 images_json 获取
  if (detailRecord.value.images_json) {
    const imagesJson = detailRecord.value.images_json as {
      generated?: string[]
      task_id?: string
    }
    if (imagesJson.generated && imagesJson.generated.length > 0) {
      return imagesJson.generated.filter(img => img) // 过滤空值
    }
  }

  return []
}

// 获取大纲页面列表
interface OutlinePage {
  type?: string
  content?: string
  index?: number
}

function getOutlinePages(): OutlinePage[] {
  if (!detailRecord.value) return []

  // 优先从 outline_json 获取
  if (detailRecord.value.outline_json) {
    const outlineJson = detailRecord.value.outline_json as {
      pages?: OutlinePage[]
      raw?: string
    }
    if (outlineJson.pages && outlineJson.pages.length > 0) {
      return outlineJson.pages
    }
  }

  return []
}

// 获取原始输入
function getOutlineRaw(): string {
  if (!detailRecord.value) return ''

  // 优先从 outline_json.raw 获取
  if (detailRecord.value.outline_json) {
    const outlineJson = detailRecord.value.outline_json as { raw?: string }
    if (outlineJson.raw) {
      return outlineJson.raw
    }
  }

  // 降级到 outline_raw
  return detailRecord.value.outline_raw || ''
}

// 获取页面类型名称
function getPageTypeName(type: string): string {
  const names: Record<string, string> = {
    cover: '封面',
    content: '内容',
    summary: '总结'
  }
  return names[type] || '内容'
}

onMounted(() => {
  fetchRecords()
})
</script>

<style scoped>
.admin-records {
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

.search-input {
  width: 200px;
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
}

.search-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.filter-select,
.filter-input {
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  background: #fff;
}

.filter-input {
  width: 100px;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-danger {
  background: #ef4444;
  color: #fff;
}

.btn-danger:hover {
  background: #dc2626;
}

.btn-secondary {
  background: #f3f4f6;
  color: #374151;
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
  padding: 16px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.data-table th {
  background: #f9fafb;
  font-weight: 600;
  color: #374151;
  font-size: 14px;
}

.checkbox-col {
  width: 40px;
  text-align: center !important;
}

.record-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.thumbnail {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  object-fit: cover;
}

.text-muted {
  color: #9ca3af;
}

.status-badge {
  display: inline-block;
  position: static;  /* 覆盖全局 history.css 中的 position: absolute */
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.status-completed {
  background: #d1fae5;
  color: #059669;
}

.status-generating {
  background: #fef3c7;
  color: #d97706;
}

.status-draft {
  background: #e5e7eb;
  color: #6b7280;
}

.status-partial {
  background: #dbeafe;
  color: #2563eb;
}

.action-buttons {
  display: flex;
  gap: 8px;
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

.btn-delete {
  background: #fee2e2;
}

.btn-delete:hover {
  background: #fecaca;
}

.empty-row {
  text-align: center !important;
  color: #9ca3af;
  padding: 48px !important;
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
  width: 480px;
  max-width: 90vw;
  max-height: 90vh;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
}

.modal-sm {
  width: 400px;
}

.modal-lg {
  width: 720px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
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
  min-height: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
  flex-shrink: 0;
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

.outline-content {
  background: #f9fafb;
  padding: 16px;
  border-radius: 8px;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.warning-text {
  color: #dc2626;
  font-size: 14px;
  margin-top: 8px;
}

.form-error {
  background: #fef2f2;
  color: #dc2626;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 14px;
  margin-top: 16px;
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

/* UUID文本样式 */
.uuid-text {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  word-break: break-all;
}

/* 图片网格样式 */
.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 16px;
  margin-top: 12px;
}

.image-item {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
}

.image-item img {
  width: 100%;
  aspect-ratio: 3/4;
  object-fit: cover;
  display: block;
}

.image-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  font-size: 12px;
  background: #fff;
  border-top: 1px solid #e5e7eb;
}

.download-link {
  color: #667eea;
  text-decoration: none;
  cursor: pointer;
}

.download-link:hover {
  text-decoration: underline;
}

/* 大纲页面样式 */
.outline-pages {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.outline-page-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #e5e7eb;
}

.outline-page-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.page-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 24px;
  padding: 0 8px;
  background: #667eea;
  color: white;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
}

.type-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  background: #e5e7eb;
  color: #6b7280;
}

.type-badge.type-cover {
  background: #dbeafe;
  color: #2563eb;
}

.type-badge.type-content {
  background: #f3e8ff;
  color: #7c3aed;
}

.type-badge.type-summary {
  background: #d1fae5;
  color: #059669;
}

.word-count {
  margin-left: auto;
  font-size: 11px;
  color: #9ca3af;
}

.outline-page-content {
  font-size: 14px;
  line-height: 1.7;
  color: #374151;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 空状态提示 */
.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px dashed #e5e7eb;
  color: #9ca3af;
  font-size: 14px;
  margin-top: 12px;
}

.empty-hint .hint-sub {
  font-size: 12px;
  color: #d1d5db;
  margin-top: 4px;
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

.record-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  position: relative;
  transition: all 0.2s;
}

.record-card.selected {
  box-shadow: 0 0 0 2px #667eea;
  background: #f8f9ff;
}

.card-checkbox {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 2;
}

.card-checkbox input {
  width: 20px;
  height: 20px;
  cursor: pointer;
}

.card-header {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.card-thumbnail {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
}

.card-thumbnail-placeholder {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
}

.card-title-section {
  flex: 1;
  min-width: 0;
  padding-right: 30px;
}

.card-title {
  font-weight: 600;
  color: #1a1a2e;
  font-size: 15px;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-subtitle {
  font-size: 13px;
  color: #6b7280;
}

.card-subtitle .separator {
  margin: 0 6px;
}

.card-body {
  margin-bottom: 12px;
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-date {
  font-size: 12px;
  color: #9ca3af;
}

.card-actions {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

.btn-card-action {
  flex: 1;
  padding: 10px 16px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-card-action.btn-view {
  background: #e0e7ff;
  color: #4338ca;
}

.btn-card-action.btn-view:hover {
  background: #c7d2fe;
}

.btn-card-action.btn-delete {
  background: #fee2e2;
  color: #dc2626;
}

.btn-card-action.btn-delete:hover {
  background: #fecaca;
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

  .toolbar-right {
    display: flex;
    justify-content: flex-end;
  }

  .search-input {
    flex: 1;
    min-width: 150px;
  }

  .modal-lg {
    width: 90vw;
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
  .toolbar-left {
    gap: 8px;
  }

  .search-input {
    width: 100%;
    flex: none;
    order: 1;
  }

  .filter-select {
    flex: 1;
    min-width: 0;
    order: 2;
  }

  .filter-input {
    width: 80px;
    order: 3;
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
    gap: 8px;
  }

  .btn-page {
    padding: 10px 16px;
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
    flex-direction: column;
    gap: 8px;
  }

  .modal-footer .btn {
    width: 100%;
    justify-content: center;
  }

  /* 详情弹窗 */
  .detail-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .images-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  .outline-page-card {
    padding: 12px;
  }

  .outline-page-header {
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
    padding-bottom: 10px;
  }

  .outline-page-content {
    font-size: 13px;
    line-height: 1.6;
  }

  /* 错误提示 */
  .error-toast {
    left: 16px;
    right: 16px;
    bottom: 16px;
    padding: 14px 16px;
  }
}

/* 小屏手机适配 */
@media (max-width: 480px) {
  .record-card {
    padding: 14px;
  }

  .card-thumbnail,
  .card-thumbnail-placeholder {
    width: 48px;
    height: 48px;
  }

  .card-thumbnail-placeholder {
    font-size: 20px;
  }

  .card-title {
    font-size: 14px;
  }

  .card-subtitle {
    font-size: 12px;
  }

  .btn-card-action {
    padding: 8px 12px;
    font-size: 12px;
  }

  .images-grid {
    grid-template-columns: 1fr;
  }

  .pagination {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
