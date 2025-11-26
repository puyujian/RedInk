<template>
  <div class="container">
    <div class="page-header">
      <div>
        <h1 class="page-title">创作完成</h1>
        <p class="page-subtitle">恭喜！你的小红书图文已生成完毕，共 {{ store.images.length }} 张</p>
      </div>
      <div style="display: flex; gap: 12px;">
        <button class="btn" @click="startOver" style="background: white; border: 1px solid var(--border-color);">
          再来一篇
        </button>
        <button class="btn btn-primary" @click="downloadAll">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          一键下载
        </button>
      </div>
    </div>

    <div class="card">
      <TransitionGroup name="list" tag="div" class="grid-cols-4">
        <div v-for="image in store.images" :key="image.index" class="image-card group">
          <!-- Image Area -->
          <div
            v-if="image.url"
            style="position: relative; aspect-ratio: 3/4; overflow: hidden; cursor: pointer;"
            @click="viewImage(image.url)"
          >
            <img
              :src="image.url + '?t=' + new Date().getTime()"
              :alt="`第 ${image.index + 1} 页`"
              style="width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s;"
            />
            <!-- Regenerating Overlay -->
            <div v-if="regeneratingIndex === image.index" style="position: absolute; inset: 0; background: rgba(255,255,255,0.8); display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 10;">
               <div class="spinner" style="width: 24px; height: 24px; border-width: 2px; border-color: var(--primary); border-top-color: transparent;"></div>
               <span style="font-size: 12px; color: var(--primary); margin-top: 8px; font-weight: 600;">重绘中...</span>
            </div>

            <!-- Hover Overlay -->
            <div v-else style="position: absolute; inset: 0; background: rgba(0,0,0,0.3); opacity: 0; transition: opacity 0.2s; display: flex; align-items: center; justify-content: center; color: white; font-weight: 600;" class="hover-overlay">
              预览大图
            </div>

            <!-- 多图选择按钮 - 悬浮在右上角 -->
            <div
              v-if="image.candidates && image.candidates.length > 1"
              class="candidate-switcher"
              @click.stop
            >
              <button
                class="candidate-btn"
                @click.stop="openCandidateSelector(image)"
                :title="`${image.candidates.length} 张候选图片可选`"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="3" width="7" height="7"></rect>
                  <rect x="14" y="3" width="7" height="7"></rect>
                  <rect x="14" y="14" width="7" height="7"></rect>
                  <rect x="3" y="14" width="7" height="7"></rect>
                </svg>
                <span>{{ image.candidates.length }}</span>
              </button>
            </div>
          </div>

          <!-- Action Bar -->
          <div style="padding: 12px; border-top: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 12px; color: var(--text-sub);">Page {{ image.index + 1 }}</span>
            <div style="display: flex; gap: 8px;">
              <button
                style="border: none; background: none; color: var(--text-sub); cursor: pointer; display: flex; align-items: center;"
                title="重新生成此图"
                @click="handleRegenerate(image)"
                :disabled="regeneratingIndex === image.index"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"></path><path d="M1 20v-6h6"></path><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
              </button>
              <button
                style="border: none; background: none; color: var(--primary); cursor: pointer; font-size: 12px;"
                @click="downloadOne(image)"
              >
                下载
              </button>
            </div>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <!-- 候选图片选择弹窗 -->
    <div v-if="candidateSelectorVisible" class="candidate-modal" @click="closeCandidateSelector">
      <div class="candidate-modal-content" @click.stop>
        <div class="candidate-modal-header">
          <h3>选择图片</h3>
          <button class="close-btn" @click="closeCandidateSelector">×</button>
        </div>
        <div class="candidate-grid">
          <div
            v-for="(url, idx) in selectedImageCandidates"
            :key="idx"
            class="candidate-item"
            :class="{ selected: idx === selectedImageCurrentIndex }"
            @click="selectCandidate(idx)"
          >
            <img :src="url + '?t=' + new Date().getTime()" :alt="`候选图片 ${idx + 1}`" />
            <div class="candidate-index">{{ idx + 1 }}</div>
            <div v-if="idx === selectedImageCurrentIndex" class="selected-badge">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.image-card:hover .hover-overlay {
  opacity: 1;
}
.image-card:hover img {
  transform: scale(1.05);
}

/* 候选图片切换按钮 */
.candidate-switcher {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 5;
}

.candidate-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: rgba(0, 0, 0, 0.6);
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}

.candidate-btn:hover {
  background: var(--primary);
  transform: scale(1.05);
}

/* 候选图片选择弹窗 */
.candidate-modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.candidate-modal-content {
  background: white;
  border-radius: 12px;
  padding: 24px;
  max-width: 90vw;
  max-height: 80vh;
  overflow: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.candidate-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.candidate-modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: #f5f5f5;
  border-radius: 50%;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #e0e0e0;
}

.candidate-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 16px;
}

.candidate-item {
  position: relative;
  aspect-ratio: 3/4;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  border: 3px solid transparent;
  transition: all 0.2s;
}

.candidate-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15);
}

.candidate-item.selected {
  border-color: var(--primary);
}

.candidate-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.candidate-index {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 24px;
  height: 24px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.selected-badge {
  position: absolute;
  bottom: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  background: var(--primary);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useGeneratorStore, type GeneratedImage } from '../stores/generator'
import { regenerateImage } from '../api'

const router = useRouter()
const store = useGeneratorStore()
const regeneratingIndex = ref<number | null>(null)

// 候选图片选择相关状态
const candidateSelectorVisible = ref(false)
const selectedImageIndex = ref<number | null>(null)
const selectedImageCandidates = ref<string[]>([])
const selectedImageCurrentIndex = ref(0)

const viewImage = (url: string) => {
  window.open(url, '_blank')
}

const startOver = () => {
  store.reset()
  router.push('/')
}

const downloadOne = (image: any) => {
  if (image.url) {
    const link = document.createElement('a')
    link.href = image.url
    link.download = `rednote_page_${image.index + 1}.png`
    link.click()
  }
}

const downloadAll = () => {
  store.images.forEach((image, index) => {
    if (image.url) {
      setTimeout(() => {
        downloadOne(image)
      }, index * 300)
    }
  })
}

// 打开候选图片选择器
const openCandidateSelector = (image: GeneratedImage) => {
  if (!image.candidates || image.candidates.length <= 1) return
  selectedImageIndex.value = image.index
  selectedImageCandidates.value = image.candidates
  selectedImageCurrentIndex.value = image.selectedIndex || 0
  candidateSelectorVisible.value = true
}

// 关闭候选图片选择器
const closeCandidateSelector = () => {
  candidateSelectorVisible.value = false
  selectedImageIndex.value = null
  selectedImageCandidates.value = []
}

// 选择候选图片
const selectCandidate = (idx: number) => {
  if (selectedImageIndex.value === null) return
  store.selectCandidate(selectedImageIndex.value, idx)
  selectedImageCurrentIndex.value = idx
  closeCandidateSelector()
}

const handleRegenerate = async (image: any) => {
  if (!store.taskId || regeneratingIndex.value !== null) return

  regeneratingIndex.value = image.index
  try {
    // Find the page content from outline
    const pageContent = store.outline.pages.find(p => p.index === image.index)
    if (!pageContent) {
       alert('无法找到对应页面的内容')
       return
    }

    const result = await regenerateImage(store.taskId, pageContent)
    if (result.success && result.image_url) {
       // Update the store image url to force refresh (add timestamp in template)
       // We need to make sure the store updates reactivity
       const newUrl = result.image_url.startsWith('/api') ? result.image_url : `/api/images/${result.image_url}`
       store.updateImage(image.index, newUrl, result.candidates)
    } else {
       alert('重绘失败: ' + (result.error || '未知错误'))
    }
  } catch (e: any) {
    alert('重绘失败: ' + e.message)
  } finally {
    regeneratingIndex.value = null
  }
}
</script>
