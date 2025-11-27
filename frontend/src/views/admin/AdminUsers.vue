<template>
  <div class="admin-users">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索用户名或邮箱..."
          class="search-input"
          @input="debouncedSearch"
        />
        <select v-model="filterRole" class="filter-select" @change="fetchUsers">
          <option value="">所有角色</option>
          <option value="user">普通用户</option>
          <option value="admin">管理员</option>
          <option value="pro">专业版</option>
        </select>
        <select v-model="filterStatus" class="filter-select" @change="fetchUsers">
          <option value="">所有状态</option>
          <option value="active">已启用</option>
          <option value="inactive">已禁用</option>
        </select>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-primary" @click="showCreateModal = true">
          <span>+</span> 新建用户
        </button>
      </div>
    </div>

    <!-- 用户表格 -->
    <div class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>邮箱</th>
            <th>角色</th>
            <th>状态</th>
            <th>注册时间</th>
            <th>最后登录</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.id }}</td>
            <td>
              <span class="username">{{ user.username }}</span>
            </td>
            <td>{{ user.email || '-' }}</td>
            <td>
              <span :class="['role-badge', `role-${user.role}`]">
                {{ roleLabels[user.role] || user.role }}
              </span>
            </td>
            <td>
              <span :class="['status-badge', user.is_active ? 'active' : 'inactive']">
                {{ user.is_active ? '已启用' : '已禁用' }}
              </span>
            </td>
            <td>{{ formatDate(user.created_at) }}</td>
            <td>{{ user.last_login_at ? formatDate(user.last_login_at) : '-' }}</td>
            <td>
              <div class="action-buttons">
                <button
                  class="btn-action btn-edit"
                  title="编辑"
                  @click="openEditModal(user)"
                >
                  ✏️
                </button>
                <button
                  v-if="user.is_active"
                  class="btn-action btn-disable"
                  title="禁用"
                  @click="toggleUserStatus(user)"
                >
                  🚫
                </button>
                <button
                  v-else
                  class="btn-action btn-enable"
                  title="启用"
                  @click="toggleUserStatus(user)"
                >
                  ✅
                </button>
                <button
                  class="btn-action btn-delete"
                  title="删除"
                  @click="confirmDelete(user)"
                >
                  🗑️
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="users.length === 0 && !loading">
            <td colspan="8" class="empty-row">暂无用户数据</td>
          </tr>
        </tbody>
      </table>

      <!-- 加载状态 -->
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

    <!-- 创建/编辑用户弹窗 -->
    <div v-if="showCreateModal || showEditModal" class="modal-overlay" @click.self="closeModals">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ showEditModal ? '编辑用户' : '新建用户' }}</h3>
          <button class="btn-close" @click="closeModals">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>用户名 *</label>
            <input
              v-model="formData.username"
              type="text"
              placeholder="请输入用户名"
              :disabled="showEditModal"
            />
          </div>
          <div class="form-group">
            <label>邮箱</label>
            <input
              v-model="formData.email"
              type="email"
              placeholder="请输入邮箱（可选）"
            />
          </div>
          <div class="form-group" v-if="!showEditModal">
            <label>密码 *</label>
            <input
              v-model="formData.password"
              type="password"
              placeholder="请输入密码"
            />
          </div>
          <div class="form-group">
            <label>角色</label>
            <select v-model="formData.role">
              <option value="user">普通用户</option>
              <option value="admin">管理员</option>
              <option value="pro">专业版</option>
            </select>
          </div>
          <div v-if="formError" class="form-error">{{ formError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeModals">取消</button>
          <button
            class="btn btn-primary"
            :disabled="formSubmitting"
            @click="submitForm"
          >
            {{ formSubmitting ? '提交中...' : '确定' }}
          </button>
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
          <p>确定要删除用户 <strong>{{ userToDelete?.username }}</strong> 吗？</p>
          <p class="warning-text">此操作不可恢复，用户的所有数据将被删除。</p>
          <div v-if="deleteError" class="form-error">{{ deleteError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showDeleteModal = false">取消</button>
          <button
            class="btn btn-danger"
            :disabled="deleteSubmitting"
            @click="deleteUser"
          >
            {{ deleteSubmitting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-toast">
      {{ error }}
      <button @click="error = ''">×</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getUsers,
  createUser,
  updateUser,
  deleteUser as deleteUserApi,
  updateUserStatus,
  type AdminUser,
} from '@/api/admin'

// 状态
const loading = ref(false)
const error = ref('')
const users = ref<AdminUser[]>([])
const currentPage = ref(1)
const totalPages = ref(1)
const pageSize = 20

// 用于防止竞态条件的 token
let fetchToken = 0

// 筛选
const searchQuery = ref('')
const filterRole = ref('')
const filterStatus = ref('')

// 弹窗状态
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showDeleteModal = ref(false)
const formSubmitting = ref(false)
const formError = ref('')
const deleteSubmitting = ref(false)
const deleteError = ref('')
const userToDelete = ref<AdminUser | null>(null)
const editingUser = ref<AdminUser | null>(null)

// 表单数据
const formData = ref({
  username: '',
  email: '',
  password: '',
  role: 'user',
})

// 角色标签映射
const roleLabels: Record<string, string> = {
  user: '普通用户',
  admin: '管理员',
  pro: '专业版',
}

// 防抖搜索
let searchTimeout: number | null = null
function debouncedSearch() {
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }
  searchTimeout = window.setTimeout(() => {
    currentPage.value = 1
    fetchUsers()
  }, 300)
}

// 获取用户列表
async function fetchUsers() {
  // 递增 token 防止竞态条件
  const currentToken = ++fetchToken
  loading.value = true
  error.value = ''
  try {
    const response = await getUsers({
      page: currentPage.value,
      per_page: pageSize,
      search: searchQuery.value || undefined,
      role: filterRole.value || undefined,
      is_active: filterStatus.value === 'active' ? true : filterStatus.value === 'inactive' ? false : undefined,
    })
    // 检查是否为最新请求，防止旧请求覆盖新数据
    if (currentToken !== fetchToken) return
    if (response.success) {
      users.value = response.items || []
      totalPages.value = response.pages || 1
    } else {
      error.value = response.error || '获取用户列表失败'
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

// 跳转页面
function goToPage(page: number) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    fetchUsers()
  }
}

// 格式化日期
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

// 打开编辑弹窗
function openEditModal(user: AdminUser) {
  editingUser.value = user
  formData.value = {
    username: user.username,
    email: user.email || '',
    password: '',
    role: user.role,
  }
  formError.value = ''
  showEditModal.value = true
}

// 关闭所有弹窗
function closeModals() {
  showCreateModal.value = false
  showEditModal.value = false
  editingUser.value = null
  formData.value = {
    username: '',
    email: '',
    password: '',
    role: 'user',
  }
  formError.value = ''
}

// 提交表单
async function submitForm() {
  formError.value = ''

  // 验证
  if (!formData.value.username.trim()) {
    formError.value = '请输入用户名'
    return
  }

  if (!showEditModal.value && !formData.value.password) {
    formError.value = '请输入密码'
    return
  }

  formSubmitting.value = true
  try {
    if (showEditModal.value && editingUser.value) {
      // 编辑用户
      const response = await updateUser(editingUser.value.id, {
        email: formData.value.email || undefined,
        role: formData.value.role,
      })
      if (!response.success) {
        formError.value = response.error || '更新用户失败'
        return
      }
    } else {
      // 创建用户
      const response = await createUser({
        username: formData.value.username,
        email: formData.value.email || undefined,
        password: formData.value.password,
        role: formData.value.role,
      })
      if (!response.success) {
        formError.value = response.error || '创建用户失败'
        return
      }
    }
    closeModals()
    fetchUsers()
  } catch (e: unknown) {
    formError.value = e instanceof Error ? e.message : '操作失败'
  } finally {
    formSubmitting.value = false
  }
}

// 切换用户状态
async function toggleUserStatus(user: AdminUser) {
  try {
    const response = await updateUserStatus(user.id, !user.is_active)
    if (response.success) {
      user.is_active = !user.is_active
    } else {
      error.value = response.error || '操作失败'
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '网络错误'
  }
}

// 确认删除
function confirmDelete(user: AdminUser) {
  userToDelete.value = user
  deleteError.value = ''
  showDeleteModal.value = true
}

// 删除用户
async function deleteUser() {
  if (!userToDelete.value) return

  deleteSubmitting.value = true
  deleteError.value = ''
  try {
    const response = await deleteUserApi(userToDelete.value.id)
    if (response.success) {
      showDeleteModal.value = false
      userToDelete.value = null
      fetchUsers()
    } else {
      deleteError.value = response.error || '删除失败'
    }
  } catch (e: unknown) {
    deleteError.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    deleteSubmitting.value = false
  }
}

onMounted(() => {
  fetchUsers()
})
</script>

<style scoped>
.admin-users {
  position: relative;
}

/* 工具栏 */
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
  width: 240px;
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.filter-select {
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  background: #fff;
  cursor: pointer;
}

/* 按钮 */
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
  gap: 8px;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-secondary {
  background: #f3f4f6;
  color: #374151;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.btn-danger {
  background: #ef4444;
  color: #fff;
}

.btn-danger:hover {
  background: #dc2626;
}

/* 表格 */
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

.data-table td {
  font-size: 14px;
  color: #1a1a2e;
}

.data-table tbody tr:hover {
  background: #f9fafb;
}

.username {
  font-weight: 500;
}

.empty-row {
  text-align: center !important;
  color: #9ca3af;
  padding: 48px !important;
}

/* 角色徽章 */
.role-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.role-user {
  background: #e0e7ff;
  color: #4338ca;
}

.role-admin {
  background: #fef3c7;
  color: #d97706;
}

.role-pro {
  background: #d1fae5;
  color: #059669;
}

/* 状态徽章 */
.status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.active {
  background: #d1fae5;
  color: #059669;
}

.status-badge.inactive {
  background: #fee2e2;
  color: #dc2626;
}

/* 操作按钮 */
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

.btn-edit {
  background: #e0e7ff;
}

.btn-edit:hover {
  background: #c7d2fe;
}

.btn-disable {
  background: #fef3c7;
}

.btn-disable:hover {
  background: #fde68a;
}

.btn-enable {
  background: #d1fae5;
}

.btn-enable:hover {
  background: #a7f3d0;
}

.btn-delete {
  background: #fee2e2;
}

.btn-delete:hover {
  background: #fecaca;
}

/* 分页 */
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
  transition: all 0.2s;
}

.btn-page:hover:not(:disabled) {
  background: #f3f4f6;
}

.btn-page:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 14px;
  color: #6b7280;
}

/* 加载状态 */
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
  to {
    transform: rotate(360deg);
  }
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
  color: #1a1a2e;
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
  transition: all 0.2s;
}

.btn-close:hover {
  background: #f3f4f6;
  color: #374151;
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

/* 表单 */
.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-group input:disabled {
  background: #f9fafb;
  cursor: not-allowed;
}

.form-error {
  background: #fef2f2;
  color: #dc2626;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 14px;
  margin-top: 16px;
}

.warning-text {
  color: #dc2626;
  font-size: 14px;
  margin-top: 8px;
}

/* 错误提示 */
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
