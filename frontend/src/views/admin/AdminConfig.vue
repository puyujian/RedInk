<template>
  <div class="admin-config">
    <!-- 当前配置 -->
    <div class="config-card">
      <div class="card-header">
        <h3>图片服务配置 (image_providers.yaml)</h3>
        <div class="header-actions">
          <button
            class="btn btn-secondary"
            @click="showHistoryModal = true"
          >
            📜 历史版本
          </button>
          <button
            class="btn btn-primary"
            :disabled="!hasChanges || saving"
            @click="saveConfig"
          >
            {{ saving ? '保存中...' : '💾 保存配置' }}
          </button>
        </div>
      </div>

      <div class="editor-container">
        <div class="editor-toolbar">
          <span class="editor-hint">使用 YAML 格式编辑配置</span>
          <button class="btn-icon" title="格式化" @click="formatYaml">
            📐
          </button>
        </div>
        <textarea
          v-model="configContent"
          class="config-editor"
          placeholder="加载配置中..."
          :disabled="loading"
          spellcheck="false"
        ></textarea>
        <div v-if="syntaxError" class="syntax-error">
          ⚠️ {{ syntaxError }}
        </div>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <span>加载配置...</span>
    </div>

    <!-- 历史版本弹窗 -->
    <div v-if="showHistoryModal" class="modal-overlay" @click.self="showHistoryModal = false">
      <div class="modal modal-lg">
        <div class="modal-header">
          <h3>配置历史版本</h3>
          <button class="btn-close" @click="showHistoryModal = false">×</button>
        </div>
        <div class="modal-body">
          <div v-if="loadingHistory" class="loading-container">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="historyVersions.length === 0" class="empty-state">
            暂无历史版本
          </div>
          <div v-else class="history-list">
            <div
              v-for="version in historyVersions"
              :key="version.id"
              class="history-item"
            >
              <div class="history-info">
                <div class="history-version">版本 {{ version.version }}</div>
                <div class="history-meta">
                  {{ formatDate(version.created_at) }}
                  <span v-if="version.created_by_username">
                    · {{ version.created_by_username }}
                  </span>
                </div>
                <div v-if="version.diff_summary" class="history-diff">
                  {{ version.diff_summary }}
                </div>
              </div>
              <div class="history-actions">
                <button
                  class="btn btn-sm btn-secondary"
                  @click="previewVersion(version)"
                >
                  预览
                </button>
                <button
                  class="btn btn-sm btn-primary"
                  @click="confirmRollback(version)"
                >
                  回滚
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 预览版本弹窗 -->
    <div v-if="previewingVersion" class="modal-overlay" @click.self="previewingVersion = null">
      <div class="modal modal-lg">
        <div class="modal-header">
          <h3>版本 {{ previewingVersion.version }} 预览</h3>
          <button class="btn-close" @click="previewingVersion = null">×</button>
        </div>
        <div class="modal-body">
          <pre class="preview-content">{{ previewingVersion.content }}</pre>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="previewingVersion = null">关闭</button>
          <button class="btn btn-primary" @click="confirmRollback(previewingVersion)">
            回滚到此版本
          </button>
        </div>
      </div>
    </div>

    <!-- 回滚确认弹窗 -->
    <div v-if="rollbackVersion" class="modal-overlay" @click.self="rollbackVersion = null">
      <div class="modal modal-sm">
        <div class="modal-header">
          <h3>确认回滚</h3>
          <button class="btn-close" @click="rollbackVersion = null">×</button>
        </div>
        <div class="modal-body">
          <p>确定要回滚到版本 <strong>{{ rollbackVersion.version }}</strong> 吗？</p>
          <p class="warning-text">当前配置将被替换，此操作会创建新的版本记录。</p>
          <div v-if="rollbackError" class="form-error">{{ rollbackError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="rollbackVersion = null">取消</button>
          <button
            class="btn btn-primary"
            :disabled="rolling"
            @click="doRollback"
          >
            {{ rolling ? '回滚中...' : '确认回滚' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 错误/成功提示 -->
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
import { ref, computed, onMounted } from 'vue'
import yaml from 'js-yaml'
import {
  getImageProvidersConfig,
  updateImageProvidersConfig,
  getConfigHistory,
  rollbackConfig,
  type ConfigVersion,
} from '@/api/admin'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')

const configContent = ref('')
const originalContent = ref('')
const syntaxError = ref('')

const showHistoryModal = ref(false)
const loadingHistory = ref(false)
const historyVersions = ref<ConfigVersion[]>([])
const previewingVersion = ref<ConfigVersion | null>(null)
const rollbackVersion = ref<ConfigVersion | null>(null)
const rolling = ref(false)
const rollbackError = ref('')

const hasChanges = computed(() => {
  return configContent.value !== originalContent.value
})

async function fetchConfig() {
  loading.value = true
  error.value = ''
  try {
    const response = await getImageProvidersConfig()
    if (response.success && response.data) {
      configContent.value = response.data.content || ''
      originalContent.value = configContent.value
    } else {
      error.value = response.error || '获取配置失败'
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    loading.value = false
  }
}

function validateYaml(): boolean {
  syntaxError.value = ''
  try {
    // 使用 js-yaml 进行专业的 YAML 语法验证
    yaml.load(configContent.value)
    return true
  } catch (e: unknown) {
    if (e instanceof yaml.YAMLException) {
      // 提取更友好的错误信息
      const line = e.mark?.line !== undefined ? e.mark.line + 1 : '?'
      syntaxError.value = `第 ${line} 行: ${e.reason || 'YAML 语法错误'}`
    } else {
      syntaxError.value = 'YAML 语法错误'
    }
    return false
  }
}

function formatYaml() {
  // 使用 js-yaml 进行专业的格式化
  try {
    const parsed = yaml.load(configContent.value)
    if (parsed) {
      configContent.value = yaml.dump(parsed, {
        indent: 2,
        lineWidth: -1, // 不自动换行
        noRefs: true,
        sortKeys: false,
      })
    }
    syntaxError.value = ''
  } catch (e: unknown) {
    if (e instanceof yaml.YAMLException) {
      const line = e.mark?.line !== undefined ? e.mark.line + 1 : '?'
      syntaxError.value = `第 ${line} 行: ${e.reason || 'YAML 语法错误，无法格式化'}`
    } else {
      syntaxError.value = '格式化失败：YAML 语法错误'
    }
  }
}

async function saveConfig() {
  if (!validateYaml()) return

  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const response = await updateImageProvidersConfig(configContent.value)
    if (response.success) {
      originalContent.value = configContent.value
      success.value = '配置保存成功'
      setTimeout(() => { success.value = '' }, 3000)
    } else {
      error.value = response.error || '保存配置失败'
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    saving.value = false
  }
}

async function fetchHistory() {
  loadingHistory.value = true
  try {
    const response = await getConfigHistory()
    if (response.success) {
      historyVersions.value = response.versions || []
    }
  } catch {
    // 忽略错误
  } finally {
    loadingHistory.value = false
  }
}

function previewVersion(version: ConfigVersion) {
  previewingVersion.value = version
}

function confirmRollback(version: ConfigVersion) {
  previewingVersion.value = null
  rollbackVersion.value = version
  rollbackError.value = ''
}

async function doRollback() {
  if (!rollbackVersion.value) return

  rolling.value = true
  rollbackError.value = ''
  try {
    const response = await rollbackConfig(rollbackVersion.value.version)
    if (response.success) {
      rollbackVersion.value = null
      showHistoryModal.value = false
      success.value = '回滚成功'
      fetchConfig()
      setTimeout(() => { success.value = '' }, 3000)
    } else {
      rollbackError.value = response.error || '回滚失败'
    }
  } catch (e: unknown) {
    rollbackError.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    rolling.value = false
  }
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

onMounted(() => {
  fetchConfig()
})

// 监听历史弹窗打开
import { watch } from 'vue'
watch(showHistoryModal, (val) => {
  if (val) fetchHistory()
})
</script>

<style scoped>
.admin-config {
  position: relative;
}

.config-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
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

.header-actions {
  display: flex;
  gap: 12px;
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
  padding: 6px 12px;
  font-size: 13px;
}

.editor-container {
  padding: 0;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.editor-hint {
  font-size: 12px;
  color: #6b7280;
}

.btn-icon {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  font-size: 16px;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.2s;
}

.btn-icon:hover {
  background: #e5e7eb;
}

.config-editor {
  width: 100%;
  min-height: 500px;
  padding: 20px 24px;
  border: none;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  background: #fff;
}

.config-editor:focus {
  outline: none;
}

.config-editor:disabled {
  background: #f9fafb;
}

.syntax-error {
  padding: 12px 24px;
  background: #fef2f2;
  color: #dc2626;
  font-size: 14px;
  border-top: 1px solid #fecaca;
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
  width: 480px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
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
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
  flex-shrink: 0;
}

/* 历史列表 */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
}

.history-version {
  font-weight: 600;
  color: #1a1a2e;
}

.history-meta {
  font-size: 13px;
  color: #6b7280;
  margin-top: 4px;
}

.history-diff {
  font-size: 12px;
  color: #667eea;
  margin-top: 4px;
}

.history-actions {
  display: flex;
  gap: 8px;
}

.preview-content {
  background: #f9fafb;
  padding: 16px;
  border-radius: 8px;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
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

/* Toast 提示 */
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

.toast-error button {
  color: #dc2626;
}

.toast-success {
  background: #d1fae5;
  color: #059669;
}

.toast-success button {
  color: #059669;
}
</style>
