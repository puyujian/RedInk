<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon users">👥</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total_users }}</div>
          <div class="stat-label">总用户数</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon records">📝</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total_records }}</div>
          <div class="stat-label">生成记录</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon images">🖼️</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total_images }}</div>
          <div class="stat-label">图片总数</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon storage">💾</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatBytes(stats.total_storage_bytes) }}</div>
          <div class="stat-label">存储空间</div>
        </div>
      </div>
    </div>

    <!-- 详细统计 -->
    <div class="details-grid">
      <!-- 今日统计 -->
      <div class="detail-card">
        <h3 class="card-title">今日统计</h3>
        <div class="detail-list">
          <div class="detail-item">
            <span class="detail-label">新增用户</span>
            <span class="detail-value">{{ stats.users_today }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">新增记录</span>
            <span class="detail-value">{{ stats.records_today }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">新增图片</span>
            <span class="detail-value">{{ stats.images_today }}</span>
          </div>
        </div>
      </div>

      <!-- 用户统计 -->
      <div class="detail-card">
        <h3 class="card-title">用户统计</h3>
        <div class="detail-list">
          <div class="detail-item">
            <span class="detail-label">活跃用户</span>
            <span class="detail-value success">{{ stats.active_users }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">禁用用户</span>
            <span class="detail-value danger">{{ stats.inactive_users }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">VIP用户数</span>
            <span class="detail-value">{{ stats.pro_count }}</span>
          </div>
        </div>
      </div>

      <!-- 记录状态 -->
      <div class="detail-card">
        <h3 class="card-title">记录状态</h3>
        <div class="detail-list">
          <div class="detail-item">
            <span class="detail-label">已完成</span>
            <span class="detail-value success">{{ stats.completed_records }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">生成中</span>
            <span class="detail-value warning">{{ stats.generating_records }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">草稿</span>
            <span class="detail-value">{{ stats.draft_records }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <span>加载统计数据...</span>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-message">
      <span>{{ error }}</span>
      <button @click="fetchStats" class="btn-retry">重试</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getDashboardStats, type DashboardStats } from '@/api/admin'

const loading = ref(false)
const error = ref('')

// 默认统计数据（防御性编程）
const defaultStats: DashboardStats = {
  total_users: 0,
  active_users: 0,
  inactive_users: 0,
  pro_count: 0,
  users_today: 0,
  total_records: 0,
  completed_records: 0,
  generating_records: 0,
  draft_records: 0,
  records_today: 0,
  total_images: 0,
  images_today: 0,
  total_storage_bytes: 0,
}

const stats = ref<DashboardStats>({ ...defaultStats })

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

async function fetchStats() {
  loading.value = true
  error.value = ''
  try {
    const response = await getDashboardStats()
    if (response.success && response.stats) {
      // 使用扩展运算符安全合并数据，确保所有字段都有值
      stats.value = { ...defaultStats, ...response.stats }
    } else {
      // 失败时重置为默认值
      stats.value = { ...defaultStats }
      error.value = response.error || '获取统计数据失败'
    }
  } catch (e: unknown) {
    // 异常时也重置为默认值
    stats.value = { ...defaultStats }
    error.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchStats()
})
</script>

<style scoped>
.dashboard {
  position: relative;
}

/* 统计卡片网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  margin-bottom: 24px;
}

.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-icon.users {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.stat-icon.records {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.stat-icon.images {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.stat-icon.storage {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a2e;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #6b7280;
  margin-top: 4px;
}

/* 详细统计网格 */
.details-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.detail-card {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 16px 0;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.detail-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detail-label {
  font-size: 14px;
  color: #6b7280;
}

.detail-value {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a2e;
}

.detail-value.success {
  color: #10b981;
}

.detail-value.warning {
  color: #f59e0b;
}

.detail-value.danger {
  color: #ef4444;
}

/* 加载状态 */
.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  border-radius: 12px;
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
  to {
    transform: rotate(360deg);
  }
}

/* 错误消息 */
.error-message {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #dc2626;
  margin-top: 24px;
}

.btn-retry {
  padding: 8px 16px;
  background: #dc2626;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-retry:hover {
  background: #b91c1c;
}

/* ==================== 响应式布局 ==================== */

/* 平板适配 */
@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .details-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 移动端适配 */
@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .details-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .stat-card {
    padding: 16px;
    gap: 12px;
  }

  .stat-icon {
    width: 48px;
    height: 48px;
    font-size: 20px;
  }

  .stat-value {
    font-size: 24px;
  }

  .stat-label {
    font-size: 13px;
  }

  .detail-card {
    padding: 16px;
  }

  .card-title {
    font-size: 15px;
    margin-bottom: 12px;
    padding-bottom: 10px;
  }

  .detail-value {
    font-size: 16px;
  }

  .error-message {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .btn-retry {
    width: 100%;
  }
}

/* 小屏手机适配 */
@media (max-width: 480px) {
  .stat-card {
    padding: 14px;
  }

  .stat-icon {
    width: 44px;
    height: 44px;
    font-size: 18px;
    border-radius: 10px;
  }

  .stat-value {
    font-size: 22px;
  }
}
</style>
