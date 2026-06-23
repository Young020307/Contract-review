<template>
  <div class="workbench">
    <div class="workbench-left">
      <DocxPreview :file-url="docxUrl" />
    </div>
    <div class="workbench-right">
      <AnnotationToolbar
        :current-paragraph="currentParagraph"
        :para-text="paraText"
        :annotations="annotations"
        :saving="saving"
        @mark-as="markAs"
        @apply-rule="handleApplyRule"
        @save="handleSave"
        @select-para="handleSelectPara"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTemplate, saveAnnotations, getAnnotations } from '../api'
import type { AnnotationItem, ValidationRule } from '../types'
import DocxPreview from '../components/DocxPreview.vue'
import AnnotationToolbar from '../components/AnnotationToolbar.vue'

const route = useRoute()
const templateId = Number(route.params.id)
const docxUrl = ref('')
const currentParagraph = ref<number | null>(null)
const paraText = ref('')
const annotations = ref<AnnotationItem[]>([])
const saving = ref(false)

onMounted(async () => {
  // Verify template exists (will throw 404 if not found)
  await getTemplate(templateId)
  docxUrl.value = `/api/documents/proxy-template/${templateId}`
  // Load existing annotations
  try {
    const existing = await getAnnotations(templateId)
    annotations.value = existing.map(a => ({
      paragraph_index: a.paragraph_index,
      zone_type: a.zone_type as 'fixed' | 'fillable',
      rules: a.rules ? JSON.parse(a.rules) : undefined
    }))
  } catch { /* no existing annotations */ }
})

function handleSelectPara(index: number) {
  currentParagraph.value = index
}

function markAs(zone: 'fixed' | 'fillable') {
  if (currentParagraph.value === null) return
  const existing = annotations.value.findIndex(a => a.paragraph_index === currentParagraph.value)
  const item: AnnotationItem = { paragraph_index: currentParagraph.value!, zone_type: zone }
  if (existing >= 0) {
    annotations.value[existing] = item
  } else {
    annotations.value.push(item)
  }
}

function handleApplyRule(rule: ValidationRule, paraIndex: number) {
  const existing = annotations.value.findIndex(a => a.paragraph_index === paraIndex)
  if (existing >= 0) {
    annotations.value[existing].rules = rule
  } else {
    annotations.value.push({ paragraph_index: paraIndex, zone_type: 'fillable', rules: rule })
  }
}

async function handleSave() {
  saving.value = true
  await saveAnnotations(templateId, annotations.value)
  saving.value = false
  ElMessage.success('标注已保存')
}
</script>

<style scoped>
.workbench { display: flex; gap: 16px; height: calc(100vh - 100px); }
.workbench-left { flex: 1; overflow-y: auto; }
.workbench-right { width: 360px; flex-shrink: 0; }
</style>
