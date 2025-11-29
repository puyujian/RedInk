/**
 * 草稿恢复 Composable
 * 用于在多个页面中恢复未保存的草稿
 */
import { ref } from 'vue'
import { useGeneratorStore } from '../stores/generator'
import { useAuthStore } from '../stores/auth'
import { createHistory } from '../api'

const PENDING_DRAFT_KEY = 'redink_pending_draft'
const savingDraft = ref(false)

// 辅助函数：将 File 转换为 base64
const readFileAsDataUrl = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

// 辅助函数：持久化待保存的草稿到 localStorage
const persistPendingDraft = (payload: any) => {
  try {
    localStorage.setItem(PENDING_DRAFT_KEY, JSON.stringify(payload))
  } catch (e) {
    console.error('Failed to persist pending draft:', e)
  }
}

// 辅助函数：清除待保存的草稿
const clearPendingDraft = () => {
  try {
    localStorage.removeItem(PENDING_DRAFT_KEY)
  } catch (e) {
    console.error('Failed to clear pending draft:', e)
  }
}

// 带重试的草稿保存函数
const saveDraftWithRetry = async (payload: {
  recordId: string
  topic: string
  outline: { raw: string; pages: any[] }
  userImages?: string[]
}): Promise<string> => {
  const delays = [0, 1000, 3000] // 立即尝试，1秒后重试，3秒后再重试

  for (let i = 0; i < delays.length; i++) {
    try {
      if (i > 0) {
        await new Promise(resolve => setTimeout(resolve, delays[i]))
      }

      const res = await createHistory(
        payload.topic,
        payload.outline,
        undefined,
        payload.userImages,
        payload.recordId
      )

      if (res.success && res.record_id) {
        return res.record_id
      }

      throw new Error(res.error || '草稿保存失败')
    } catch (err) {
      if (i === delays.length - 1) {
        // 最后一次重试也失败了
        throw err
      }
      // 继续下一次重试
    }
  }

  throw new Error('草稿保存失败')
}

/**
 * 使用草稿恢复功能
 */
export function useDraftRecovery() {
  const store = useGeneratorStore()
  const authStore = useAuthStore()

  /**
   * 恢复待保存的草稿（在页面加载时调用）
   */
  const resumePendingDraft = async () => {
    if (store.recordId || !authStore.isAuthenticated) return

    try {
      const raw = localStorage.getItem(PENDING_DRAFT_KEY)
      if (!raw) return

      const payload = JSON.parse(raw)
      savingDraft.value = true

      const rid = await saveDraftWithRetry(payload)
      store.recordId = rid
      clearPendingDraft()
      console.log('Successfully saved pending draft:', rid)
    } catch (e) {
      console.error('Failed to resume pending draft:', e)
      // 保留 pending draft，等待用户网络恢复或下次访问
    } finally {
      savingDraft.value = false
    }
  }

  /**
   * 保存草稿（带重试和 localStorage 备份）
   */
  const saveDraft = async (
    topic: string,
    outline: { raw: string; pages: any[] },
    imageFiles: File[] = []
  ): Promise<void> => {
    const clientRecordId = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).substring(2)}`

    savingDraft.value = true

    // 异步处理：后台转换图片并保存
    Promise.resolve().then(async () => {
      // 转换用户图片为 base64（如果有）
      let userImagesBase64: string[] = []
      if (imageFiles.length > 0) {
        try {
          // 限制图片大小，避免 localStorage 超限
          const MAX_IMAGE_SIZE = 1024 * 1024 // 1MB per image
          const validImages = imageFiles.filter(file => file.size <= MAX_IMAGE_SIZE)

          if (validImages.length < imageFiles.length) {
            console.warn(`Skipped ${imageFiles.length - validImages.length} images exceeding 1MB`)
          }

          userImagesBase64 = await Promise.all(validImages.map(readFileAsDataUrl))
        } catch (e) {
          console.error('Failed to convert images to base64:', e)
        }
      }

      return saveDraftWithRetry({
        recordId: clientRecordId,
        topic,
        outline,
        userImages: userImagesBase64.length > 0 ? userImagesBase64 : undefined
      })
    })
      .then((rid) => {
        store.recordId = rid
        clearPendingDraft()
        console.log('Draft saved successfully:', rid)
      })
      .catch((err) => {
        console.error('Failed to save draft:', err)

        // 检查 payload 大小，避免超出 localStorage 限制
        const payload = {
          recordId: clientRecordId,
          topic,
          outline,
          userImages: [] as string[] // 失败时不保存图片，只保存大纲
        }

        const payloadSize = JSON.stringify(payload).length
        const MAX_STORAGE_SIZE = 4 * 1024 * 1024 // 4MB 限制

        if (payloadSize < MAX_STORAGE_SIZE) {
          persistPendingDraft(payload)
        } else {
          console.error('Payload too large for localStorage:', payloadSize)
        }

        throw err // 重新抛出错误，让调用者处理
      })
      .finally(() => {
        savingDraft.value = false
      })
  }

  return {
    savingDraft,
    resumePendingDraft,
    saveDraft,
    clearPendingDraft
  }
}
