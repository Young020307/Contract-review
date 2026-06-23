<template>
  <div class="preview-container" ref="container">
    <div v-if="loading" class="loading">解析文档中...</div>
    <div v-html="htmlContent" class="preview-content"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import mammoth from 'mammoth'

const props = defineProps<{ fileUrl: string }>()
const htmlContent = ref('')
const loading = ref(false)

watch(() => props.fileUrl, async (url) => {
  if (!url) return
  loading.value = true
  const res = await fetch(url)
  const blob = await res.arrayBuffer()
  const result = await mammoth.convertToHtml({ arrayBuffer: blob })
  htmlContent.value = result.value
  loading.value = false
}, { immediate: true })
</script>

<style scoped>
.preview-container { height: 100%; overflow-y: auto; padding: 24px; background: #fff; border: 1px solid #e4e7ed; }
.preview-content { max-width: 800px; margin: 0 auto; }
.loading { text-align: center; padding: 40px; color: #909399; }
</style>
