<template>
  <div class="admin-images">
    <!-- 存储统计 -->
    <div class="stats-bar" v-if="stats">
      <div class="stat-item">
        <span class="stat-label">总图片数</span>
        <span class="stat-value">{{ stats.total_count }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">总存储</span>
        <span class="stat-value">{{ formatBytes(stats.total_size) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">今日新增</span>
        <span class="stat-value">{{ stats.today_count }}</span>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索文件名..."
          class="search-input"
          @input="debouncedSearch"
        />
        <input
          v-model="filterUserId"
          type="number"
          placeholder="用户ID"
          class="filter-input"
          @change="fetchImages"
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

    <!-- 图片网格 -->
    <div class="images-grid">
      <div
        v-for="image in images"
        :key="image.id"
        class="image-card"
        :class="{ selected: selectedIds.includes(image.id) }"
        @click="toggleSelect(image.id)"
      >
        <div class="image-checkbox">
          <input
            type="checkbox"
            :checked="selectedIds.includes(image.id)"
            @click.stop
            @change="toggleSelect(image.id)"
          />
        </div>
        <div class="image-preview" @click.stop="previewImage(image)">
          <img :src="getImageUrl(image.filename)" :alt="image.filename" />
        </div>
        <div class="image-info">
          <div class="image-filename" :title="image.filename">
            {{ truncateFilename(image.filename) }}
          </div>
          <div class="image-meta">
            <span>{{ formatBytes(image.file_size || 0) }}</span>
            <span>{{ formatDate(image.created_at) }}</span>
          </div>
          <div class="image-user" v-if="image.user">
            用户: {{ image.user.username }}
          </div>
        </div>
        <div class="image-actions">
          <button
            class="btn-action btn-view"
            title="预览"
            @click.stop="previewImage(image)"
          >
            👁️
          </button>
          <button
            class="btn-action btn-delete"
            title="删除"
            @click.stop="confirmDelete(image)"
          >
            🗑️
          </button>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="images.length === 0 && !loading" class="empty-state">
      <span class="empty-icon">🖼️</span>
      <span>暂无图片数据</span>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
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

    <!-- 图片预览弹窗 -->
    <div v-if="previewingImage" class="preview-overlay" @click="previewingImage = null">
      <div class="preview-container" @click.stop>
        <button class="btn-close-preview" @click="previewingImage = null">×</button>
        <img :src="getImageUrl(previewingImage.filename)" :alt="previewingImage.filename" />
        <div class="preview-info">
          <div>{{ previewingImage.filename }}</div>
          <div>{{ formatBytes(previewingImage.file_size || 0) }} · {{ formatDate(previewingImage.created_at) }}</div>
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
          <p v-if="imageToDelete">
            确定要删除图片 <strong>{{ truncateFilename(imageToDelete.filename) }}</strong> 吗？
          </p>
          <p v-else>
            确定要删除选中的 <strong>{{ selectedIds.length }}</strong> 张图片吗？
          </p>
          <p class="warning-text">此操作不可恢复。</p>
          <div v-if="deleteError" class="form-error">{{ deleteError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeDeleteModal">取消</button>
          <button
            class="btn btn-danger"
            :disabled="deleteSubmitting"
            @click="deleteImages"
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
import { ref, onMounted } from 'vue'
import {
  getImages,
  getImageStats,
  deleteImage,
  batchDeleteImages,
  type AdminImage,
  type ImageStats,
} from '@/api/admin'

const loading = ref(false)
const error = ref('')
const images = ref<AdminImage[]>([])
const stats = ref<ImageStats | null>(null)
const currentPage = ref(1)
const totalPages = ref(1)
const pageSize = 24

const searchQuery = ref('')
const filterUserId = ref<number | ''>('')
const selectedIds = ref<number[]>([])

const previewingImage = ref<AdminImage | null>(null)
const showDeleteModal = ref(false)
const imageToDelete = ref<AdminImage | null>(null)
const deleteSubmitting = ref(false)
const deleteError = ref('')

let searchTimeout: number | null = null
function debouncedSearch() {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = window.setTimeout(() => {
    currentPage.value = 1
    fetchImages()
  }, 300)
}

function getImageUrl(filename: string): string {
  return `/api/images/${filename}`
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

function truncateFilename(filename: string): string {
  if (filename.length > 30) {
    return filename.substring(0, 15) + '...' + filename.substring(filename.length - 12)
  }
  return filename
}

async function fetchStats() {
  try {
    const response = await getImageStats()
    if (response.success && response.stats) {
      stats.value = response.stats
    }
  } catch {
    // 忽略统计获取错误
  }
}

async function fetchImages() {
  loading.value = true
  error.value = ''
  selectedIds.value = []
  try {
    const response = await getImages({
      page: currentPage.value,
      per_page: pageSize,
      search: searchQuery.value || undefined,
      user_id: filterUserId.value ? Number(filterUserId.value) : undefined,
    })
    if (response.success) {
      images.value = response.items || []
      totalPages.value = response.pages || 1
    } else {
      error.value = response.error || '获取图片列表失败'
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
    fetchImages()
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

function previewImage(image: AdminImage) {
  previewingImage.value = image
}

function confirmDelete(image: AdminImage) {
  imageToDelete.value = image
  deleteError.value = ''
  showDeleteModal.value = true
}

function confirmBatchDelete() {
  imageToDelete.value = null
  deleteError.value = ''
  showDeleteModal.value = true
}

function closeDeleteModal() {
  showDeleteModal.value = false
  imageToDelete.value = null
  deleteError.value = ''
}

async function deleteImages() {
  deleteSubmitting.value = true
  deleteError.value = ''
  try {
    if (imageToDelete.value) {
      const response = await deleteImage(imageToDelete.value.id)
      if (!response.success) {
        deleteError.value = response.error || '删除失败'
        return
      }
    } else if (selectedIds.value.length > 0) {
      const response = await batchDeleteImages(selectedIds.value)
      if (!response.success) {
        deleteError.value = response.error || '批量删除失败'
        return
      }
    }
    closeDeleteModal()
    fetchImages()
    fetchStats()
  } catch (e: unknown) {
    deleteError.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    deleteSubmitting.value = false
  }
}

onMounted(() => {
  fetchStats()
  fetchImages()
})
</script>

<style scoped>
.admin-images {
  position: relative;
}

.stats-bar {
  display: flex;
  gap: 32px;
  background: #fff;
  padding: 20px 24px;
  border-radius: 12px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: #6b7280;
  text-transform: uppercase;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  gap: 16px;
}

.toolbar-left {
  display: flex;
  gap: 12px;
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

.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 20px;
}

.image-card {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.2s;
  position: relative;
}

.image-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.image-card.selected {
  box-shadow: 0 0 0 2px #667eea;
}

.image-checkbox {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
}

.image-checkbox input {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.image-preview {
  aspect-ratio: 1;
  overflow: hidden;
  cursor: pointer;
}

.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.image-preview:hover img {
  transform: scale(1.05);
}

.image-info {
  padding: 12px;
}

.image-filename {
  font-size: 13px;
  font-weight: 500;
  color: #1a1a2e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.image-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}

.image-user {
  font-size: 12px;
  color: #667eea;
  margin-top: 4px;
}

.image-actions {
  display: flex;
  gap: 8px;
  padding: 0 12px 12px;
}

.btn-action {
  flex: 1;
  padding: 8px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
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

.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: #9ca3af;
}

.empty-icon {
  display: block;
  font-size: 48px;
  margin-bottom: 16px;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 20px;
  gap: 16px;
  color: #6b7280;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e5e7eb;
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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

/* 预览弹窗 */
.preview-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.preview-container {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
}

.preview-container img {
  max-width: 100%;
  max-height: 80vh;
  border-radius: 8px;
}

.preview-info {
  text-align: center;
  color: #fff;
  margin-top: 16px;
  font-size: 14px;
}

.btn-close-preview {
  position: absolute;
  top: -40px;
  right: 0;
  width: 32px;
  height: 32px;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-size: 24px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-close-preview:hover {
  background: rgba(255, 255, 255, 0.3);
}

/* 删除弹窗 */
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
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.modal-sm {
  width: 400px;
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
