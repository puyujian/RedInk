<template>
  <div class="admin-registration">
    <!-- 注册设置卡片 -->
    <div class="settings-card">
      <div class="card-header">
        <h3>注册设置</h3>
        <button
          class="btn btn-secondary"
          @click="showHistoryModal = true"
        >
          📜 修改历史
        </button>
      </div>

      <div class="settings-form">
        <!-- 注册开关 -->
        <div class="form-group">
          <div class="form-row">
            <div class="form-label">
              <span>启用注册</span>
              <span class="form-hint">关闭后新用户无法注册</span>
            </div>
            <label class="switch">
              <input type="checkbox" v-model="settings.enabled" />
              <span class="slider"></span>
            </label>
          </div>
        </div>

        <!-- 默认角色 -->
        <div class="form-group">
          <div class="form-row">
            <div class="form-label">
              <span>新用户默认角色</span>
              <span class="form-hint">注册用户的初始权限等级</span>
            </div>
            <select v-model="settings.default_role" class="form-select">
              <option value="user">普通用户</option>
              <option value="pro">专业版用户</option>
            </select>
          </div>
        </div>

        <!-- 邀请码开关 -->
        <div class="form-group">
          <div class="form-row">
            <div class="form-label">
              <span>需要邀请码</span>
              <span class="form-hint">启用后用户注册时必须提供邀请码</span>
            </div>
            <label class="switch">
              <input type="checkbox" v-model="settings.invite_required" />
              <span class="slider"></span>
            </label>
          </div>
        </div>

        <!-- 邀请码 -->
        <div class="form-group" v-if="settings.invite_required">
          <div class="form-row">
            <div class="form-label">
              <span>邀请码</span>
              <span class="form-hint">用户注册时需要输入的邀请码</span>
            </div>
            <div class="input-group">
              <input
                v-model="settings.invite_code"
                type="text"
                class="form-input"
                placeholder="请设置邀请码"
              />
              <button class="btn btn-sm btn-secondary" @click="generateInviteCode">
                🎲 生成
              </button>
            </div>
          </div>
        </div>

        <!-- 邮箱验证（保留但标记为即将推出） -->
        <div class="form-group disabled">
          <div class="form-row">
            <div class="form-label">
              <span>需要邮箱验证 <span class="badge-soon">即将推出</span></span>
              <span class="form-hint">启用后用户需验证邮箱才能使用</span>
            </div>
            <label class="switch">
              <input type="checkbox" v-model="settings.email_verification_required" disabled />
              <span class="slider"></span>
            </label>
          </div>
        </div>

        <!-- 注册速率限制 -->
        <div class="form-group">
          <div class="form-row">
            <div class="form-label">
              <span>每小时注册限制</span>
              <span class="form-hint">0 表示不限制，防止恶意批量注册</span>
            </div>
            <input
              v-model.number="settings.rate_limit_per_hour"
              type="number"
              class="form-input form-input-sm"
              min="0"
              max="1000"
            />
          </div>
        </div>
      </div>

      <div class="card-footer">
        <div class="footer-info" v-if="settings.updated_at">
          最后更新: {{ formatDate(settings.updated_at) }}
          <span v-if="settings.updated_by_username">
            · {{ settings.updated_by_username }}
          </span>
        </div>
        <button
          class="btn btn-primary"
          :disabled="!hasChanges || saving"
          @click="saveSettings"
        >
          {{ saving ? '保存中...' : '💾 保存设置' }}
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <span>加载设置...</span>
    </div>

    <!-- 修改历史弹窗 -->
    <div v-if="showHistoryModal" class="modal-overlay" @click.self="showHistoryModal = false">
      <div class="modal modal-lg">
        <div class="modal-header">
          <h3>注册设置修改历史</h3>
          <button class="btn-close" @click="showHistoryModal = false">×</button>
        </div>
        <div class="modal-body">
          <div v-if="loadingHistory" class="loading-container">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="historyLogs.length === 0" class="empty-state">
            暂无修改记录
          </div>
          <div v-else class="history-list">
            <div
              v-for="log in historyLogs"
              :key="log.id"
              class="history-item"
            >
              <div class="history-info">
                <div class="history-action">{{ log.action }}</div>
                <div class="history-meta">
                  {{ formatDate(log.created_at) }}
                  <span v-if="log.actor_username">· {{ log.actor_username }}</span>
                </div>
                <div v-if="log.details" class="history-details">
                  <pre>{{ formatDetails(log.details) }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 提示 -->
    <div v-if="error" class="toast toast-error">
      {{ error }}
      <button @click="error = ''">×</button>
    </div>
    <div v-if="success" class="toast toast-success">
      {{ success }}
      <button @click="success = ''">×</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import {
  getRegistrationSettings,
  updateRegistrationSettings,
  getRegistrationHistory,
  type RegistrationSetting,
  type AuditLogEntry,
} from '@/api/admin'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')

const settings = reactive<RegistrationSetting>({
  enabled: true,
  default_role: 'user',
  invite_required: false,
  invite_code: '',
  email_verification_required: false,
  rate_limit_per_hour: 0,
  updated_at: '',
  updated_by_username: '',
})

const originalSettings = ref<string>('')

const showHistoryModal = ref(false)
const loadingHistory = ref(false)
const historyLogs = ref<AuditLogEntry[]>([])

const hasChanges = computed(() => {
  return JSON.stringify({
    enabled: settings.enabled,
    default_role: settings.default_role,
    invite_required: settings.invite_required,
    invite_code: settings.invite_code,
    email_verification_required: settings.email_verification_required,
    rate_limit_per_hour: settings.rate_limit_per_hour,
  }) !== originalSettings.value
})

async function fetchSettings() {
  loading.value = true
  error.value = ''
  try {
    const response = await getRegistrationSettings()
    if (response.success && response.settings) {
      Object.assign(settings, response.settings)
      originalSettings.value = JSON.stringify({
        enabled: settings.enabled,
        default_role: settings.default_role,
        invite_required: settings.invite_required,
        invite_code: settings.invite_code,
        email_verification_required: settings.email_verification_required,
        rate_limit_per_hour: settings.rate_limit_per_hour,
      })
    } else {
      error.value = response.error || '获取设置失败'
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const response = await updateRegistrationSettings({
      enabled: settings.enabled,
      default_role: settings.default_role,
      invite_required: settings.invite_required,
      invite_code: settings.invite_code || undefined,
      email_verification_required: settings.email_verification_required,
      rate_limit_per_hour: settings.rate_limit_per_hour,
    })
    if (response.success) {
      originalSettings.value = JSON.stringify({
        enabled: settings.enabled,
        default_role: settings.default_role,
        invite_required: settings.invite_required,
        invite_code: settings.invite_code,
        email_verification_required: settings.email_verification_required,
        rate_limit_per_hour: settings.rate_limit_per_hour,
      })
      success.value = '设置保存成功'
      setTimeout(() => { success.value = '' }, 3000)
    } else {
      error.value = response.error || '保存设置失败'
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    saving.value = false
  }
}

function generateInviteCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  let code = ''
  for (let i = 0; i < 8; i++) {
    code += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  settings.invite_code = code
}

async function fetchHistory() {
  loadingHistory.value = true
  try {
    const response = await getRegistrationHistory()
    if (response.success) {
      historyLogs.value = response.logs || []
    }
  } catch {
    // 忽略错误
  } finally {
    loadingHistory.value = false
  }
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2)
}

onMounted(() => {
  fetchSettings()
})

watch(showHistoryModal, (val) => {
  if (val) fetchHistory()
})
</script>

<style scoped>
.admin-registration {
  position: relative;
  max-width: 800px;
}

.settings-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.card-header h3 {
  margin: 0;
  font-size: 16px;
  color: #1a1a2e;
}

.settings-form {
  padding: 24px;
}

.form-group {
  padding: 20px 0;
  border-bottom: 1px solid #f3f4f6;
}

.form-group:last-child {
  border-bottom: none;
}

.form-group.disabled {
  opacity: 0.6;
}

.form-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
}

.form-label {
  flex: 1;
}

.form-label > span:first-child {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #1a1a2e;
}

.form-hint {
  display: block;
  font-size: 13px;
  color: #6b7280;
  margin-top: 4px;
}

.badge-soon {
  display: inline-block;
  padding: 2px 8px;
  background: #e5e7eb;
  color: #6b7280;
  font-size: 11px;
  border-radius: 4px;
  margin-left: 8px;
}

/* 开关 */
.switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 26px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #e5e7eb;
  transition: 0.3s;
  border-radius: 26px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 20px;
  width: 20px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

input:checked + .slider {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

input:checked + .slider:before {
  transform: translateX(22px);
}

input:disabled + .slider {
  cursor: not-allowed;
}

/* 表单输入 */
.form-select {
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  min-width: 150px;
  background: #fff;
}

.form-input {
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
}

.form-input-sm {
  width: 100px;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.input-group {
  display: flex;
  gap: 8px;
}

.input-group .form-input {
  flex: 1;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #f9fafb;
  border-top: 1px solid #e5e7eb;
}

.footer-info {
  font-size: 13px;
  color: #6b7280;
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

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f3f4f6;
  color: #374151;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.btn-sm {
  padding: 8px 12px;
  font-size: 13px;
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
  to { transform: rotate(360deg); }
}

.loading-container {
  padding: 40px;
  display: flex;
  justify-content: center;
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

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-item {
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
}

.history-action {
  font-weight: 600;
  color: #1a1a2e;
}

.history-meta {
  font-size: 13px;
  color: #6b7280;
  margin-top: 4px;
}

.history-details {
  margin-top: 12px;
}

.history-details pre {
  background: #fff;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  overflow-x: auto;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
}

/* Toast */
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 16px 24px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  display: flex;
  align-items: center;
  gap: 16px;
  z-index: 1001;
}

.toast button {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
}

.toast-error {
  background: #fef2f2;
  color: #dc2626;
}

.toast-success {
  background: #d1fae5;
  color: #059669;
}

/* ==================== 响应式布局 ==================== */

/* 平板适配 */
@media (max-width: 1024px) {
  .admin-registration {
    max-width: 100%;
  }

  .modal-lg {
    width: 90vw;
  }
}

/* 移动端适配 */
@media (max-width: 768px) {
  /* 卡片头部 */
  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 16px 20px;
  }

  .card-header .btn {
    width: 100%;
    justify-content: center;
  }

  /* 表单区域 */
  .settings-form {
    padding: 16px 20px;
  }

  .form-group {
    padding: 16px 0;
  }

  /* 表单行：垂直堆叠 */
  .form-row {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .form-label {
    flex: none;
  }

  .form-label > span:first-child {
    font-size: 14px;
  }

  .form-hint {
    font-size: 12px;
    margin-top: 2px;
  }

  /* 开关靠左对齐 */
  .switch {
    align-self: flex-start;
  }

  /* 表单控件全宽 */
  .form-select {
    width: 100%;
    min-width: unset;
  }

  .form-input {
    width: 100%;
  }

  .form-input-sm {
    width: 100%;
  }

  /* 输入组 */
  .input-group {
    flex-direction: column;
    gap: 10px;
  }

  .input-group .btn {
    width: 100%;
    justify-content: center;
  }

  /* 卡片底部 */
  .card-footer {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    padding: 16px 20px;
  }

  .footer-info {
    text-align: center;
    font-size: 12px;
  }

  .card-footer .btn {
    width: 100%;
    justify-content: center;
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

  /* 历史列表 */
  .history-item {
    padding: 14px;
  }

  .history-action {
    font-size: 14px;
  }

  .history-meta {
    font-size: 12px;
  }

  .history-details pre {
    font-size: 11px;
    padding: 10px;
  }

  /* Toast */
  .toast {
    left: 16px;
    right: 16px;
    bottom: 16px;
    padding: 14px 16px;
    font-size: 13px;
  }
}

/* 小屏手机适配 */
@media (max-width: 480px) {
  .card-header h3 {
    font-size: 15px;
  }

  .form-label > span:first-child {
    font-size: 13px;
  }

  .form-hint {
    font-size: 11px;
  }

  .btn {
    padding: 10px 16px;
    font-size: 13px;
  }

  .btn-sm {
    padding: 8px 12px;
    font-size: 12px;
  }

  /* 开关尺寸调整 */
  .switch {
    width: 44px;
    height: 24px;
  }

  .slider:before {
    height: 18px;
    width: 18px;
  }

  input:checked + .slider:before {
    transform: translateX(20px);
  }
}
</style>
