<template>
  <div class="workbench">
    <div class="wb-left">
      <DocxPreview
        :file-url="docxUrl"
        :selected-paragraph="currentParagraph"
        :selected-start="selectedStart"
        :selected-end="selectedEnd"
        :annotations="annotations"
        :docx-indices="docxIndices"
        :focused-zone="focusedZone"
        @paragraph-click="handleParagraphClick"
        @text-select="handleTextSelect"
        @annotation-click="handleAnnotationClick"
      />
    </div>
    <div class="wb-right">
      <AnnotationToolbar
        :current-paragraph="currentParagraph"
        :para-text="paraText"
        :annotations="annotations"
        :saving="saving"
        :selected-text="selectedText"
        :selected-start="selectedStart"
        :selected-end="selectedEnd"
        :clicked-annotation="clickedAnnotation"
        @mark-selection="handleMarkSelection"
        @save="handleSave"
        @select-para="handleParagraphClick"
        @remove-annotation="handleRemoveAnnotation"
        @cancel-annotation="handleCancelAnnotation"
        @update-annotation="handleUpdateAnnotation"
        @focus-annotation="handleFocusAnnotation"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTemplate, saveAnnotations, getAnnotations } from '../api'
import type { AnnotationItem, ParagraphInfo } from '../types'
import DocxPreview from '../components/DocxPreview.vue'
import AnnotationToolbar from '../components/AnnotationToolbar.vue'

const route = useRoute()
const router = useRouter()
const templateId = Number(route.params.id)
const docxUrl = ref('')
const currentParagraph = ref<number | null>(null)
const paraText = ref('')
const selectedText = ref('')
const selectedStart = ref<number | null>(null)
const selectedEnd = ref<number | null>(null)
const annotations = ref<AnnotationItem[]>([])
const docxIndices = ref<number[]>([])
const clickedAnnotation = ref<{ paraIndex: number; startChar: number; zoneType: string } | null>(null)
const focusedZone = ref<{ paraIndex: number; startChar: number } | null>(null)
const saving = ref(false)

onMounted(async () => {
  const template = await getTemplate(templateId)
  docxUrl.value = `/api/documents/proxy-template/${templateId}`
  docxIndices.value = template.paragraphs.map(p => p.index)
  const detected = autoAnnotateUnderscores(template.paragraphs)
  try {
    const existing = await getAnnotations(templateId)
    if (existing.length > 0) {
      const existingKeys = new Set(existing.map((a: any) => `${a.paragraph_index}_${a.start_char}`))
      const merged: AnnotationItem[] = existing.map((a: any) => ({
        paragraph_index: a.paragraph_index,
        start_char: a.start_char,
        end_char: a.end_char,
        zone_type: a.zone_type as 'fixed' | 'fillable',
        rules: a.rules ? JSON.parse(a.rules) : undefined
      }))
      for (const d of detected) {
        if (!existingKeys.has(`${d.paragraph_index}_${d.start_char}`)) {
          merged.push(d)
        }
      }
      annotations.value = merged
    } else {
      annotations.value = detected
      const fillCount = detected.filter(a => a.zone_type === 'fillable').length
      const fixedCount = detected.filter(a => a.zone_type === 'fixed').length
      ElMessage.success(`已自动标注：${fillCount} 个填充区 + ${fixedCount} 个固定区，请完善后保存`)
    }
  } catch { /* no existing annotations */ }
})

function autoAnnotateUnderscores(paragraphs: ParagraphInfo[]): AnnotationItem[] {
  const result: AnnotationItem[] = []
  for (const para of paragraphs) {
    const text = para.text
    const fillableRanges: [number, number][] = []
    // 1) underscore characters in text
    const regex = /_+/g
    let match: RegExpExecArray | null
    while ((match = regex.exec(text)) !== null) {
      fillableRanges.push([match.index, match.index + match[0].length])
    }
    // 2) text with underline formatting from DOCX
    for (const [s, e] of para.underline_ranges || []) {
      // skip purely underscore spans (already covered above)
      const slice = text.slice(s, e)
      if (/^_+$/.test(slice)) continue
      fillableRanges.push([s, e])
    }
    // 3) table cells only: trailing "：" with no fillable → zero-width fillable
    if (para.is_table_cell && text.length > 0 && /[：:]\s*$/.test(text)) {
      const lastFillableEnd = fillableRanges.length > 0
        ? Math.max(...fillableRanges.map(r => r[1]))
        : -1
      if (lastFillableEnd < text.length) {
        fillableRanges.push([text.length, text.length])
      }
    }
    // merge overlapping / adjacent ranges
    const merged = mergeRanges(fillableRanges)
    for (const [start, end] of merged) {
      result.push({ paragraph_index: para.index, start_char: start, end_char: end, zone_type: 'fillable' })
    }
    if (merged.length > 0) {
      let pos = 0
      for (const [start, end] of merged) {
        if (pos < start) {
          result.push({ paragraph_index: para.index, start_char: pos, end_char: start, zone_type: 'fixed' })
        }
        pos = end
      }
      if (pos < text.length) {
        result.push({ paragraph_index: para.index, start_char: pos, end_char: text.length, zone_type: 'fixed' })
      }
    } else {
      result.push({ paragraph_index: para.index, start_char: 0, end_char: text.length, zone_type: 'fixed' })
    }
  }
  return result
}

function mergeRanges(ranges: [number, number][]): [number, number][] {
  if (!ranges.length) return []
  const sorted = [...ranges].sort((a, b) => a[0] - b[0])
  const merged: [number, number][] = [sorted[0]]
  for (let i = 1; i < sorted.length; i++) {
    const prev = merged[merged.length - 1]
    if (sorted[i][0] <= prev[1]) {
      prev[1] = Math.max(prev[1], sorted[i][1])
    } else {
      merged.push([...sorted[i]])
    }
  }
  return merged
}

function handleParagraphClick(index: number, text?: string) {
  currentParagraph.value = index
  selectedStart.value = null
  selectedEnd.value = null
  selectedText.value = ''
  clickedAnnotation.value = null
  if (text !== undefined) paraText.value = text
}

function handleAnnotationClick(paraIndex: number, startChar: number, _endChar: number, zoneType: string, text: string) {
  currentParagraph.value = paraIndex
  paraText.value = text
  selectedStart.value = null
  selectedEnd.value = null
  selectedText.value = ''
  clickedAnnotation.value = { paraIndex, startChar, zoneType }
  focusedZone.value = { paraIndex, startChar }
}

function handleFocusAnnotation(paraIndex: number, startChar: number) {
  focusedZone.value = { paraIndex, startChar }
}

function handleCancelAnnotation(paraIndex: number, startChar: number) {
  annotations.value = annotations.value.filter(
    a => !(a.paragraph_index === paraIndex && a.start_char === startChar)
  )
  clickedAnnotation.value = null
}

function handleUpdateAnnotation(item: AnnotationItem) {
  const idx = annotations.value.findIndex(
    a => a.paragraph_index === item.paragraph_index && a.start_char === item.start_char
  )
  if (idx >= 0) annotations.value[idx] = { ...item }
  clickedAnnotation.value = null
}

function handleTextSelect(paraIndex: number, startChar: number, endChar: number, text: string) {
  currentParagraph.value = paraIndex
  selectedStart.value = startChar
  selectedEnd.value = endChar
  selectedText.value = text
}

function handleMarkSelection(item: AnnotationItem) {
  const existing = annotations.value.findIndex(
    a => a.paragraph_index === item.paragraph_index && a.start_char === item.start_char
  )
  if (existing >= 0) {
    annotations.value[existing] = item
  } else {
    annotations.value.push(item)
  }
  selectedStart.value = null
  selectedEnd.value = null
  selectedText.value = ''
}

function handleRemoveAnnotation(paraIndex: number, startChar: number) {
  annotations.value = annotations.value.filter(
    a => !(a.paragraph_index === paraIndex && a.start_char === startChar)
  )
}

async function handleSave() {
  saving.value = true
  await saveAnnotations(templateId, annotations.value)
  saving.value = false
  ElMessage.success('标注已保存')
  router.push('/')
}
</script>

<style scoped>
.workbench {
  display: flex;
  gap: 0;
  height: 100%;
}

.wb-left {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

.wb-right {
  width: 380px;
  flex-shrink: 0;
  border-left: 1px solid var(--rule);
}
</style>
