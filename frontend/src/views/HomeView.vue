<template>
  <div class="container home-container">
    <!-- 图片网格轮播背景 -->
    <div class="showcase-background">
      <div
        class="showcase-grid"
        ref="showcaseGridRef"
        :style="{ transform: `translateY(-${scrollOffset}px)` }"
      >
        <div v-for="(image, index) in showcaseImages" :key="index" class="showcase-item">
          <img :src="`/assets/showcase/${image}`" :alt="`封面 ${index + 1}`" />
        </div>
      </div>
      <div class="showcase-overlay"></div>
    </div>

    <!-- 登录提示横幅 -->
    <div v-if="showLoginHint && !authStore.isAuthenticated" class="login-hint-banner">
      <div class="hint-content">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
        <span>登录后可保存创作历史，随时查看和管理您的作品</span>
      </div>
      <div class="hint-actions">
        <button class="btn-hint-action" @click="router.push({ path: '/', query: { showAuth: 'login' } })">立即登录</button>
        <button class="btn-hint-close" @click="showLoginHint = false">×</button>
      </div>
    </div>

    <!-- Hero Area -->
    <div class="hero-section">
      <div class="hero-content">
        <div class="brand-pill">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
          AI 驱动的迪迦创作助手
        </div>
        <div class="platform-slogan">
          让传播不再需要门槛，让创作从未如此简单
        </div>
        <h1 class="page-title">灵感一触即发</h1>
        <p class="page-subtitle">输入你的创意主题，让 AI 帮你生成爆款标题、正文和封面图</p>
      </div>

      <!-- Composer Input (Modern Style) -->
      <div class="composer-container" :class="{ 'is-focused': isInputFocused, 'has-content': topic.trim() || uploadedImages.length > 0 }">
        <!-- 已上传图片预览 -->
        <Transition name="attachments-slide">
          <div v-if="uploadedImages.length > 0" class="composer-attachments">
            <TransitionGroup name="image-pop" tag="div" class="attachments-list">
              <div
                v-for="(img, idx) in uploadedImages"
                :key="img.preview"
                class="attachment-item"
              >
                <img :src="img.preview" :alt="`图片 ${idx + 1}`" />
                <button class="attachment-remove" @click="removeImage(idx)" type="button">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              </div>
            </TransitionGroup>
            <span class="attachments-hint">参考图片</span>
          </div>
        </Transition>

        <!-- 主输入区域 -->
        <div class="composer-main">
          <textarea
            ref="textareaRef"
            v-model="topic"
            class="composer-input"
            placeholder="输入你的创意主题..."
            @keydown.enter.prevent="handleEnter"
            @input="adjustHeight"
            @focus="isInputFocused = true"
            @blur="isInputFocused = false"
            :disabled="loading"
            rows="1"
          ></textarea>

          <!-- 操作按钮组 -->
          <div class="composer-actions">
            <label class="action-btn upload-btn" :class="{ 'has-files': uploadedImages.length > 0 }" title="上传参考图片">
              <input
                type="file"
                accept="image/*"
                multiple
                @change="handleImageUpload"
                :disabled="loading"
              />
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
              <span v-if="uploadedImages.length > 0" class="upload-count">{{ uploadedImages.length }}</span>
            </label>

            <button
              class="action-btn send-btn"
              @click="handleGenerate"
              :disabled="!topic.trim() || loading"
              :class="{ 'is-ready': topic.trim() && !loading }"
              type="button"
            >
              <span v-if="loading" class="send-spinner"></span>
              <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 2L11 13"></path>
                <path d="M22 2L15 22L11 13L2 9L22 2Z"></path>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick Scenarios & Dashboard -->
    <div class="content-section">
    <!-- Dashboard Grid -->
    <div class="dashboard-grid">
      
      <!-- Recent Activity (Mockup) -->
      <div class="card feature-card">
        <div class="card-header">
          <div class="header-left">
             <div class="icon-box purple">
               <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
             </div>
             <h3 class="section-title-sm">最近创作</h3>
          </div>
          <button class="btn-text" @click="router.push('/history')">全部记录</button>
        </div>
        
        <div v-if="recentRecords.length > 0" class="recent-list">
          <div v-for="record in recentRecords" :key="record.id" class="recent-item" @click="loadRecord(record)">
            <div class="recent-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" color="#666"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            </div>
            <div class="recent-info">
              <div class="recent-title">{{ record.title }}</div>
              <div class="recent-date">{{ formatDate(record.updated_at) }}</div>
            </div>
            <div class="recent-arrow">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
            </div>
          </div>
        </div>
        <div v-else class="empty-state-mini">
          <p>暂无最近记录</p>
        </div>
      </div>

      <!-- Trending -->
      <div class="card feature-card">
        <div class="card-header">
          <div class="header-left">
             <div class="icon-box orange">
               <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>
             </div>
             <h3 class="section-title-sm">全站热搜</h3>
          </div>
          <span class="refresh-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"></path><path d="M1 20v-6h6"></path><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
          </span>
        </div>
        <div class="trend-list">
          <div class="trend-item">
            <span class="trend-rank rank-1">1</span>
            <span class="trend-name">#OOTD 每日穿搭</span>
            <span class="trend-hot">
               <svg width="12" height="12" viewBox="0 0 24 24" fill="#FF4D4F" stroke="#FF4D4F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.1.2-2.2.5-3.3a7 7 0 0 0 3 2.8Z"/></svg>
               234w
            </span>
          </div>
          <div class="trend-item">
            <span class="trend-rank rank-2">2</span>
            <span class="trend-name">#探店日记</span>
            <span class="trend-hot">
               <svg width="12" height="12" viewBox="0 0 24 24" fill="#FF6B81" stroke="#FF6B81" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.1.2-2.2.5-3.3a7 7 0 0 0 3 2.8Z"/></svg>
               189w
            </span>
          </div>
          <div class="trend-item">
            <span class="trend-rank rank-3">3</span>
            <span class="trend-name">#低脂减肥餐</span>
            <span class="trend-hot">
               <svg width="12" height="12" viewBox="0 0 24 24" fill="#FF9CA8" stroke="#FF9CA8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.1.2-2.2.5-3.3a7 7 0 0 0 3 2.8Z"/></svg>
               156w
            </span>
          </div>
          <div class="trend-item">
            <span class="trend-rank">4</span>
            <span class="trend-name">#家居改造</span>
            <span class="trend-hot">120w</span>
          </div>
        </div>
      </div>
    </div>
    </div>

    <div v-if="error" class="error-toast">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGeneratorStore } from '../stores/generator'
import { generateOutline, getHistoryList, getHistory } from '../api'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const store = useGeneratorStore()

const topic = ref('')
const loading = ref(false)
const error = ref('')
const showLoginHint = ref(false)
const recentRecords = ref<any[]>([])
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const isExpanded = ref(false)
const isInputFocused = ref(false)

// 监听登录状态变化，自动刷新最近创作
watch(() => authStore.isAuthenticated, (newValue) => {
  if (newValue) {
    showLoginHint.value = false
    error.value = ''
    loadRecent()
  } else {
    // 退出登录时清空最近记录，或者重新加载（如果是显示公开记录的话）
    // 这里假设退出登录后不显示个人的最近创作
    recentRecords.value = []
    loadRecent() // 尝试加载，后端可能返回空或公开数据
  }
})

// 图片网格轮播相关
const showcaseImages = ref<string[]>([])
const scrollOffset = ref(0)
const showcaseGridRef = ref<HTMLElement | null>(null)
let scrollInterval: ReturnType<typeof setInterval> | null = null
let sectionHeight = 0

// 计算单组真实高度
const calcSectionHeight = () => {
  const el = showcaseGridRef.value
  if (!el) return
  // 拼接了 3 组,除以 3 得到单组真实高度,避免硬编码
  const newHeight = el.scrollHeight / 3
  // 只在高度变化时更新,避免不必要的重复计算
  if (newHeight > 0 && newHeight !== sectionHeight) {
    sectionHeight = newHeight
  }
}

// 加载展示图片列表
const loadShowcaseImages = async () => {
  try {
    const response = await fetch('/assets/showcase_manifest.json')
    const data = await response.json()
    const originalImages = data.covers || []

    // 复制图片数组3次以实现无缝循环
    showcaseImages.value = [...originalImages, ...originalImages, ...originalImages]

    await nextTick()

    // 初次计算高度
    calcSectionHeight()

    // 延迟再次计算,确保图片加载完成
    setTimeout(() => {
      calcSectionHeight()
    }, 500)

    // 启动平滑滚动动画
    if (showcaseImages.value.length > 0) {
      scrollInterval = setInterval(() => {
        // 定期检查高度变化(每秒一次)
        if (Math.random() < 0.033) { // 约 1/30 秒 ≈ 每秒一次
          calcSectionHeight()
        }
        scrollOffset.value += 1

        // 到达第三组时回退一组高度,始终停留在中间副本,实现无缝循环
        if (sectionHeight > 0 && scrollOffset.value >= sectionHeight * 2) {
          scrollOffset.value -= sectionHeight
        }
      }, 30) // 每30ms移动1px,实现流畅滚动
    }
  } catch (e) {
    console.error('加载展示图片失败:', e)
  }
}

// 图片上传相关
interface UploadedImage {
  file: File
  preview: string
}
const uploadedImages = ref<UploadedImage[]>([])

const adjustHeight = () => {
  const el = textareaRef.value
  if (!el) return
  
  el.style.height = 'auto'
  const newHeight = Math.max(64, Math.min(el.scrollHeight, 200)) // Min 64px, Max 200px
  el.style.height = newHeight + 'px'
  
  isExpanded.value = newHeight > 64
}

const handleEnter = (e: KeyboardEvent) => {
  if (e.shiftKey) return // Allow multiline
  handleGenerate()
}

// 处理图片上传
const handleImageUpload = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files) return

  const files = Array.from(target.files)
  files.forEach((file) => {
    // 限制最多 5 张图片
    if (uploadedImages.value.length >= 5) {
      error.value = '最多只能上传 5 张图片'
      return
    }
    // 创建预览 URL
    const preview = URL.createObjectURL(file)
    uploadedImages.value.push({ file, preview })
  })

  // 清空 input，允许重复选择同一文件
  target.value = ''
}

// 移除图片
const removeImage = (index: number) => {
  const img = uploadedImages.value[index]
  // 释放预览 URL
  URL.revokeObjectURL(img.preview)
  uploadedImages.value.splice(index, 1)
}

const loadRecent = async () => {
  try {
    const res = await getHistoryList(1, 4)
    if (res.success) {
      recentRecords.value = res.records
    }
  } catch (e) {
    // ignore
  }
}

const formatDate = (str: string) => {
  const d = new Date(str)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, '0')}`
}

const loadRecord = async (record: any) => {
   // Simple load for edit
   try {
     const res = await getHistory(record.id)
     if (res.success && res.record) {
        store.setTopic(res.record.title)
        store.setOutline(res.record.outline.raw, res.record.outline.pages)
        store.recordId = res.record.id
        router.push('/outline')
     }
   } catch(e) {
     console.error(e)
   }
}

const handleGenerate = async () => {
  if (!topic.value.trim()) return

  // 检查登录状态
  if (!authStore.isAuthenticated) {
    showLoginHint.value = true
    error.value = '请先登录后继续创作，登录后可保存历史记录'
    return
  }

  loading.value = true
  error.value = ''

  try {
    // 获取上传的图片文件列表
    const imageFiles = uploadedImages.value.map(img => img.file)

    const result = await generateOutline(
      topic.value.trim(),
      imageFiles.length > 0 ? imageFiles : undefined
    )

    if (result.success && result.pages) {
      store.setTopic(topic.value.trim())
      store.setOutline(result.outline || '', result.pages)
      store.recordId = null  // 重置历史记录ID,确保创建新记录

      // 如果有上传图片，保存到 store 中用于图片生成
      if (imageFiles.length > 0) {
        store.userImages = imageFiles
      } else {
        store.userImages = []
      }

      // 清理预览 URL
      uploadedImages.value.forEach(img => URL.revokeObjectURL(img.preview))
      uploadedImages.value = []

      router.push('/outline')
    } else {
      error.value = result.error || '生成大纲失败'
    }
  } catch (err: any) {
    error.value = err.message || '网络错误，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // 检查是否因未登录被重定向
  if (route.query.login_required === '1') {
    showLoginHint.value = true
    error.value = '请先登录后继续创作'
  }

  loadRecent()
  loadShowcaseImages()

  // 监听窗口大小变化,重新计算高度
  window.addEventListener('resize', calcSectionHeight)
})

onUnmounted(() => {
  if (scrollInterval) {
    clearInterval(scrollInterval)
  }
  // 清理事件监听
  window.removeEventListener('resize', calcSectionHeight)
})
</script>

<style scoped>
/* 图片网格轮播背景 */
.showcase-background {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100vh;
  z-index: -1;
  overflow: hidden;
}

.showcase-grid {
  display: grid;
  grid-template-columns: repeat(11, 1fr);
  gap: 16px;
  padding: 20px;
  width: 100%;
  will-change: transform;
}

.showcase-item {
  width: 100%;
  aspect-ratio: 3 / 4;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.showcase-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.showcase-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0.7) 0%,
    rgba(255, 255, 255, 0.65) 30%,
    rgba(255, 255, 255, 0.6) 100%
  );
  backdrop-filter: blur(2px);
}

.home-container {
  max-width: 1100px;
  padding-top: 10px;
  position: relative;
  z-index: 1;
}

/* 登录提示横幅 */
.login-hint-banner {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 16px 24px;
  border-radius: 16px;
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
  animation: slideDown 0.4s ease-out;
}

.hint-content {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.hint-content svg {
  flex-shrink: 0;
}

.hint-content span {
  font-size: 15px;
  font-weight: 500;
}

.hint-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-hint-action {
  background: rgba(255, 255, 255, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  padding: 8px 20px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-hint-action:hover {
  background: rgba(255, 255, 255, 0.35);
  transform: translateY(-1px);
}

.btn-hint-close {
  background: none;
  border: none;
  color: white;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  padding: 4px 8px;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.btn-hint-close:hover {
  opacity: 1;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Section Headers */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
  padding: 0 4px;
}

.section-header h3 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-main);
}

.link-more {
  font-size: 13px;
  color: var(--text-sub);
  cursor: pointer;
}
.link-more:hover { color: var(--primary); }

/* Hero Section */
.hero-section {
  text-align: center;
  margin-bottom: 40px;
  padding: 50px 60px;
  animation: fadeIn 0.6s ease-out;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
  backdrop-filter: blur(10px);
}

/* Content Section */
.content-section {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 24px;
  padding: 40px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
  backdrop-filter: blur(10px);
}

.hero-content {
  margin-bottom: 36px;
}

.brand-pill {
  display: inline-block;
  padding: 6px 16px;
  background: rgba(255, 36, 66, 0.08);
  color: var(--primary);
  border-radius: 100px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 20px;
  letter-spacing: 0.5px;
}

.platform-slogan {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 24px;
  line-height: 1.6;
  letter-spacing: 0.5px;
}

.page-subtitle {
  font-size: 16px;
  color: var(--text-sub);
  margin-top: 12px;
}

/* Dashboard Grid */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
  animation: slideUp 0.6s ease-out 0.2s backwards;
}

.feature-card {
  height: 100%;
  min-height: 280px;
  display: flex;
  flex-direction: column;
  padding: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-title-sm {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
}

.icon-box {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.icon-box.purple {
  background: linear-gradient(135deg, #9F7AEA 0%, #805AD5 100%);
  box-shadow: 0 4px 12px rgba(128, 90, 213, 0.2);
}

.icon-box.orange {
  background: linear-gradient(135deg, #F6AD55 0%, #ED8936 100%);
  box-shadow: 0 4px 12px rgba(237, 137, 54, 0.2);
}

.btn-text {
  background: none;
  border: none;
  color: var(--text-sub);
  font-size: 13px;
  cursor: pointer;
}
.btn-text:hover { color: var(--primary); }

/* Recent List */
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 12px;
  background: #F9FAFB;
  cursor: pointer;
  transition: all 0.2s;
}

.recent-item:hover {
  background: #F0F2F5;
  transform: translateX(2px);
}

.recent-icon {
  width: 32px;
  height: 32px;
  background: white;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.03);
}

.recent-info {
  flex: 1;
  overflow: hidden;
}

.recent-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recent-date {
  font-size: 12px;
  color: var(--text-sub);
}

.recent-arrow {
  color: var(--text-placeholder);
  font-size: 16px;
}

.empty-state-mini {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-placeholder);
  font-size: 14px;
  background: #FAFAFA;
  border-radius: 12px;
  border: 1px dashed #eee;
}

/* Trend List */
.trend-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.trend-item {
  display: flex;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #F5F5F5;
}
.trend-item:last-child { border-bottom: none; }

.trend-rank {
  width: 24px;
  text-align: center;
  font-weight: 800;
  font-size: 16px;
  margin-right: 12px;
  color: var(--text-placeholder);
  font-style: italic;
}

.trend-rank.rank-1 { color: #FF2442; }
.trend-rank.rank-2 { color: #FF6B81; }
.trend-rank.rank-3 { color: #FF9CA8; }

.trend-name {
  font-weight: 500;
  color: var(--text-main);
  flex: 1;
  font-size: 14px;
}

.trend-hot {
  font-size: 12px;
  color: var(--text-sub);
}

/* Animations */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.error-toast {
  position: fixed;
  bottom: 32px;
  /* 相对于主内容区居中：页面中心 + 侧边栏宽度的一半 */
  left: calc(50% + 130px); /* 备用值 */
  left: calc(50% + var(--sidebar-width, 260px) / 2);
  transform: translateX(-50%);
  background: #FF4D4F;
  color: white;
  padding: 12px 24px;
  border-radius: 50px;
  box-shadow: 0 8px 24px rgba(255, 77, 79, 0.3);
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 1000;
  animation: slideUp 0.3s ease-out;
}

/* ============================================
   Responsive - Tablet (768px - 1024px)
   ============================================ */
@media (max-width: 1024px) {
  .home-container {
    max-width: 100%;
    padding: 10px 16px;
  }

  .hero-section {
    padding: 40px 40px;
    border-radius: 20px;
  }

  .content-section {
    padding: 28px;
    border-radius: 20px;
  }

  .showcase-grid {
    grid-template-columns: repeat(7, 1fr);
    gap: 12px;
    padding: 16px;
  }

  /* Tablet 也需要相对于主内容区居中 */
  .error-toast {
    left: calc(50% + 130px); /* 备用值 */
    left: calc(50% + var(--sidebar-width, 260px) / 2);
  }
}

/* ============================================
   Responsive - Mobile (< 768px)
   ============================================ */
@media (max-width: 768px) {
  .home-container {
    padding: 8px 12px;
    padding-top: 4px;
  }

  /* 背景网格优化 */
  .showcase-grid {
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    padding: 10px;
  }

  .showcase-item {
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }

  .showcase-overlay {
    background: linear-gradient(
      to bottom,
      rgba(255, 255, 255, 0.85) 0%,
      rgba(255, 255, 255, 0.8) 50%,
      rgba(255, 255, 255, 0.75) 100%
    );
    backdrop-filter: blur(3px);
  }

  /* Hero 区域优化 */
  .hero-section {
    padding: 24px 20px 28px;
    margin-bottom: 16px;
    border-radius: 20px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
  }

  .hero-content {
    margin-bottom: 24px;
  }

  .brand-pill {
    padding: 5px 12px;
    font-size: 12px;
    margin-bottom: 14px;
  }

  .brand-pill svg {
    width: 14px;
    height: 14px;
  }

  .platform-slogan {
    font-size: 15px;
    margin-bottom: 16px;
    line-height: 1.5;
  }

  .page-title {
    font-size: 26px !important;
  }

  .page-subtitle {
    font-size: 14px;
    margin-top: 8px;
    line-height: 1.6;
  }

  /* 登录提示横幅优化 */
  .login-hint-banner {
    flex-direction: column;
    gap: 14px;
    padding: 16px 18px;
    border-radius: 14px;
    margin-bottom: 16px;
  }

  .hint-content {
    gap: 10px;
    text-align: left;
  }

  .hint-content svg {
    width: 18px;
    height: 18px;
  }

  .hint-content span {
    font-size: 14px;
    line-height: 1.5;
  }

  .hint-actions {
    width: 100%;
    justify-content: space-between;
  }

  .btn-hint-action {
    flex: 1;
    text-align: center;
    padding: 10px 16px;
    font-size: 14px;
  }

  .btn-hint-close {
    padding: 8px 12px;
    font-size: 22px;
  }

  /* 内容区域优化 */
  .content-section {
    padding: 20px 16px;
    border-radius: 20px;
  }

  /* 仪表板网格优化 */
  .dashboard-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .feature-card {
    min-height: auto;
    padding: 18px;
    border-radius: 16px;
  }

  .card-header {
    margin-bottom: 14px;
  }

  .header-left {
    gap: 10px;
  }

  .icon-box {
    width: 32px;
    height: 32px;
    border-radius: 8px;
  }

  .icon-box svg {
    width: 16px;
    height: 16px;
  }

  .section-title-sm {
    font-size: 15px;
  }

  .btn-text {
    font-size: 13px;
    padding: 6px 10px;
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.03);
  }

  /* 最近创作列表优化 - 触控友好 */
  .recent-list {
    gap: 10px;
  }

  .recent-item {
    padding: 14px;
    gap: 14px;
    border-radius: 14px;
    min-height: 64px; /* 确保足够的触控区域 */
    -webkit-tap-highlight-color: transparent;
    touch-action: manipulation;
  }

  .recent-item:active {
    background: #EDF2F7;
    transform: scale(0.98);
  }

  .recent-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
  }

  .recent-title {
    font-size: 15px;
    margin-bottom: 3px;
  }

  .recent-date {
    font-size: 12px;
  }

  .recent-arrow {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.04);
  }

  /* 热搜列表优化 */
  .trend-list {
    gap: 6px;
  }

  .trend-item {
    padding: 14px 8px;
    border-radius: 10px;
    min-height: 52px;
    -webkit-tap-highlight-color: transparent;
    touch-action: manipulation;
  }

  .trend-item:active {
    background: #F5F5F5;
  }

  .trend-rank {
    font-size: 15px;
    width: 22px;
    margin-right: 10px;
  }

  .trend-name {
    font-size: 14px;
  }

  .trend-hot {
    font-size: 12px;
    display: flex;
    align-items: center;
  }

  /* 空状态优化 */
  .empty-state-mini {
    min-height: 100px;
    border-radius: 14px;
    font-size: 13px;
  }

  /* 错误提示优化 */
  .error-toast {
    bottom: 24px;
    /* 移动端侧边栏是覆盖层，所以相对于整个页面居中 */
    left: 50%;
    transform: translateX(-50%);
    max-width: calc(100% - 32px);
    padding: 14px 20px;
    border-radius: 14px;
    font-size: 14px;
  }

  .error-toast svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }
}

/* ============================================
   Responsive - Small Mobile (< 428px)
   ============================================ */
@media (max-width: 428px) {
  .home-container {
    padding: 6px 10px;
  }

  .showcase-grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    padding: 8px;
  }

  .hero-section {
    padding: 20px 16px 24px;
    border-radius: 16px;
  }

  .brand-pill {
    padding: 4px 10px;
    font-size: 11px;
    margin-bottom: 12px;
  }

  .platform-slogan {
    font-size: 14px;
    margin-bottom: 12px;
  }

  .page-title {
    font-size: 22px !important;
    line-height: 1.3;
  }

  .page-subtitle {
    font-size: 13px;
  }

  .login-hint-banner {
    padding: 14px 16px;
    border-radius: 12px;
    gap: 12px;
  }

  .hint-content span {
    font-size: 13px;
  }

  .btn-hint-action {
    padding: 8px 14px;
    font-size: 13px;
  }

  .content-section {
    padding: 16px 14px;
    border-radius: 16px;
  }

  .feature-card {
    padding: 16px;
    border-radius: 14px;
  }

  .card-header {
    margin-bottom: 12px;
  }

  .recent-item {
    padding: 12px;
    gap: 12px;
    border-radius: 12px;
  }

  .recent-icon {
    width: 36px;
    height: 36px;
    border-radius: 8px;
  }

  .recent-icon svg {
    width: 16px;
    height: 16px;
  }

  .recent-title {
    font-size: 14px;
  }

  .trend-item {
    padding: 12px 6px;
  }
}

/* ============================================
   Safe Area - iOS 刘海屏适配
   ============================================ */
@supports (padding: max(0px)) {
  .home-container {
    padding-left: max(12px, env(safe-area-inset-left));
    padding-right: max(12px, env(safe-area-inset-right));
  }

  .error-toast {
    bottom: max(24px, env(safe-area-inset-bottom));
    /* iOS 移动端也是整个页面居中 */
    left: 50%;
    transform: translateX(-50%);
    max-width: calc(100% - max(32px, env(safe-area-inset-left) + env(safe-area-inset-right)));
  }
}

/* ============================================
   Touch & Interaction Enhancements
   ============================================ */
@media (hover: none) and (pointer: coarse) {
  /* 触屏设备优化 */
  .recent-item,
  .trend-item,
  .btn-text,
  .btn-hint-action {
    transition: transform 0.15s ease, background 0.15s ease;
  }

  .recent-item:hover {
    transform: none;
    background: #F9FAFB;
  }

  .scenario-card:hover {
    transform: none;
    box-shadow: var(--shadow-sm);
  }
}

/* ============================================
   Reduced Motion - 减少动画
   ============================================ */
@media (prefers-reduced-motion: reduce) {
  .hero-section,
  .dashboard-grid,
  .login-hint-banner,
  .error-toast {
    animation: none;
  }

  .showcase-grid {
    transform: none !important;
  }

  .recent-item,
  .trend-item,
  .feature-card {
    transition: none;
  }
}
</style>
