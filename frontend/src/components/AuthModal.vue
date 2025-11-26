<template>
  <Teleport to="body">
    <Transition name="auth-modal">
      <div v-if="visible" class="auth-modal-overlay" @click.self="handleClose">
        <div class="auth-modal">
          <!-- 头部 -->
          <header class="auth-modal-header">
            <h2 class="auth-modal-title">{{ isRegister ? '注册账号' : '登录账号' }}</h2>
            <button class="auth-modal-close" type="button" @click="handleClose" aria-label="关闭">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </header>

          <!-- Tab 切换 -->
          <div class="auth-modal-tabs">
            <button
              type="button"
              class="auth-tab-item"
              :class="{ active: !isRegister }"
              @click="switchMode('login')"
            >
              登录
            </button>
            <button
              type="button"
              class="auth-tab-item"
              :class="{ active: isRegister }"
              @click="switchMode('register')"
            >
              注册
            </button>
          </div>

          <!-- 表单 -->
          <form class="auth-modal-form" @submit.prevent="handleSubmit">
            <div class="auth-form-item">
              <label class="auth-form-label" for="auth-username">用户名</label>
              <input
                id="auth-username"
                v-model.trim="username"
                class="auth-input"
                type="text"
                placeholder="请输入用户名"
                autocomplete="username"
                :disabled="loading"
              />
            </div>

            <div v-if="isRegister" class="auth-form-item">
              <label class="auth-form-label" for="auth-email">邮箱（可选）</label>
              <input
                id="auth-email"
                v-model.trim="email"
                class="auth-input"
                type="email"
                placeholder="用于找回密码等通知"
                autocomplete="email"
                :disabled="loading"
              />
            </div>

            <div class="auth-form-item">
              <label class="auth-form-label" for="auth-password">密码</label>
              <input
                id="auth-password"
                v-model="password"
                class="auth-input"
                type="password"
                :placeholder="isRegister ? '请输入密码（至少6位）' : '请输入密码'"
                autocomplete="current-password"
                :disabled="loading"
              />
            </div>

            <!-- 错误提示 -->
            <Transition name="auth-error">
              <p v-if="formError" class="auth-form-error">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="8" x2="12" y2="12"></line>
                  <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
                {{ formError }}
              </p>
            </Transition>

            <!-- 提交按钮 -->
            <button
              type="submit"
              class="btn btn-primary auth-submit-btn"
              :disabled="!isFormValid || loading"
            >
              <span v-if="loading" class="spinner-sm"></span>
              <span>{{ isRegister ? '注册并登录' : '登录' }}</span>
            </button>

            <!-- 切换提示 -->
            <p class="auth-switch-tip">
              <template v-if="isRegister">
                已有账号？
                <button type="button" class="auth-switch-link" @click="switchMode('login')">
                  去登录
                </button>
              </template>
              <template v-else>
                还没有账号？
                <button type="button" class="auth-switch-link" @click="switchMode('register')">
                  去注册
                </button>
              </template>
            </p>
          </form>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'

// ============================================================================
// Props & Emits
// ============================================================================

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (event: 'update:visible', value: boolean): void
}>()

// ============================================================================
// Store & State
// ============================================================================

const authStore = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const email = ref('')
const password = ref('')
const loading = ref(false)
const formError = ref('')

// ============================================================================
// Computed
// ============================================================================

const isRegister = computed(() => mode.value === 'register')

const isFormValid = computed(() => {
  // 用户名必填
  if (!username.value || username.value.length < 3) {
    return false
  }

  // 密码必填
  if (!password.value) {
    return false
  }

  // 注册时密码至少6位
  if (isRegister.value && password.value.length < 6) {
    return false
  }

  return true
})

// ============================================================================
// Methods
// ============================================================================

function resetForm() {
  username.value = ''
  email.value = ''
  password.value = ''
  loading.value = false
  formError.value = ''
}

function handleClose() {
  resetForm()
  emit('update:visible', false)
}

function switchMode(nextMode: 'login' | 'register') {
  mode.value = nextMode
  formError.value = ''
}

async function handleSubmit() {
  if (!isFormValid.value || loading.value) return

  loading.value = true
  formError.value = ''

  try {
    if (isRegister.value) {
      await authStore.register({
        username: username.value,
        password: password.value,
        email: email.value || undefined,
      })
    } else {
      await authStore.login({
        username: username.value,
        password: password.value,
      })
    }
    // 成功后关闭模态框
    handleClose()
  } catch (error: any) {
    // 提取错误信息
    const message =
      error?.response?.data?.error ||
      error?.response?.data?.message ||
      error?.message ||
      (isRegister.value ? '注册失败，请稍后重试' : '登录失败，请稍后重试')
    formError.value = message
  } finally {
    loading.value = false
  }
}

// ============================================================================
// Watchers
// ============================================================================

// 关闭时重置表单
watch(
  () => props.visible,
  (val) => {
    if (!val) {
      resetForm()
    }
  }
)
</script>

<style scoped>
/* 遮罩层 */
.auth-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  backdrop-filter: blur(4px);
}

/* 模态框 */
.auth-modal {
  background: #ffffff;
  border-radius: 20px;
  width: 100%;
  max-width: 420px;
  padding: 28px 28px 32px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.25);
  animation: authModalIn 0.3s ease-out;
}

@keyframes authModalIn {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(10px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

/* 头部 */
.auth-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.auth-modal-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-main);
  margin: 0;
}

.auth-modal-close {
  border: none;
  background: #f5f5f5;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-sub);
  transition: all 0.2s;
}

.auth-modal-close:hover {
  background: #eee;
  color: var(--text-main);
}

/* Tab 切换 */
.auth-modal-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  background: #f5f5f5;
  padding: 4px;
  border-radius: 12px;
}

.auth-tab-item {
  flex: 1;
  padding: 10px 0;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  background: transparent;
  color: var(--text-sub);
  transition: all 0.2s;
}

.auth-tab-item:hover {
  color: var(--text-main);
}

.auth-tab-item.active {
  background: #ffffff;
  color: var(--primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

/* 表单 */
.auth-modal-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.auth-form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.auth-form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-sub);
}

.auth-input {
  width: 100%;
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  font-size: 15px;
  outline: none;
  transition: all 0.2s;
  background: #fafafa;
}

.auth-input:focus {
  border-color: var(--primary);
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(255, 36, 66, 0.1);
}

.auth-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 错误提示 */
.auth-form-error {
  font-size: 13px;
  color: #ff4d4f;
  background: #fff2f0;
  border: 1px solid #ffccc7;
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

/* 提交按钮 */
.auth-submit-btn {
  width: 100%;
  justify-content: center;
  margin-top: 4px;
  padding: 14px 24px;
  font-size: 15px;
  font-weight: 600;
  gap: 8px;
}

.auth-submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 切换提示 */
.auth-switch-tip {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--text-sub);
  text-align: center;
}

.auth-switch-link {
  border: none;
  background: none;
  color: var(--primary);
  cursor: pointer;
  padding: 0 4px;
  font-weight: 500;
  transition: opacity 0.2s;
}

.auth-switch-link:hover {
  opacity: 0.8;
}

/* Spinner */
.spinner-sm {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 动画过渡 */
.auth-modal-enter-active,
.auth-modal-leave-active {
  transition: all 0.3s ease;
}

.auth-modal-enter-from,
.auth-modal-leave-to {
  opacity: 0;
}

.auth-modal-enter-from .auth-modal,
.auth-modal-leave-to .auth-modal {
  transform: scale(0.95) translateY(10px);
}

.auth-error-enter-active,
.auth-error-leave-active {
  transition: all 0.2s ease;
}

.auth-error-enter-from,
.auth-error-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}

/* 移动端适配 */
@media (max-width: 768px) {
  .auth-modal-overlay {
    padding: 12px;
    align-items: flex-end;
  }

  .auth-modal {
    max-width: 100%;
    border-radius: 24px 24px 0 0;
    padding: 24px 20px 32px;
    animation: authModalInMobile 0.3s ease-out;
  }

  @keyframes authModalInMobile {
    from {
      opacity: 0;
      transform: translateY(100%);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .auth-modal-title {
    font-size: 20px;
  }

  .auth-input {
    padding: 14px 16px;
    font-size: 16px; /* 防止 iOS 自动缩放 */
  }

  .auth-submit-btn {
    padding: 16px 24px;
  }
}
</style>
