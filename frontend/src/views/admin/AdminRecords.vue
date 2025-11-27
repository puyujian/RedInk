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

    <!-- 记录表格 -->
    <div class="table-container">
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
          <div class="detail-grid">
            <div class="detail-item">
              <label>ID</label>
              <span>{{ detailRecord.id }}</span>
            </div>
            <div class="detail-item">
              <label>UUID</label>
              <span>{{ detailRecord.record_uuid }}</span>
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
          <div class="detail-section" v-if="detailRecord.outline_raw">
            <h4>原始大纲</h4>
            <pre class="outline-content">{{ detailRecord.outline_raw }}</pre>
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
    if (response.success) {
      records.value = response.items || []
      totalPages.value = response.pages || 1
    } else {
      error.value = response.error || '获取记录列表失败'
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
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
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
</style>
