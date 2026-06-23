<template>
  <div class="preview-pane" ref="container">
    <div class="pane-head">
      <span class="pane-title">模板文档预览</span>
      <span v-if="!loading" class="pane-meta">{{ paraTexts.size }} 段</span>
    </div>
    <div v-if="loading" class="loading-msg">解析文档中...</div>
    <div ref="contentEl" class="preview-body" @click="handleClick" @mouseup="handleMouseUp"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import mammoth from 'mammoth'
import type { AnnotationItem } from '../types'

const props = defineProps<{
  fileUrl: string
  selectedParagraph: number | null
  selectedStart: number | null
  selectedEnd: number | null
  annotations: AnnotationItem[]
  docxIndices: number[]
}>()

const emit = defineEmits<{
  paragraphClick: [index: number, text: string]
  textSelect: [paraIndex: number, startChar: number, endChar: number, text: string]
  annotationClick: [paraIndex: number, startChar: number, endChar: number, zoneType: string]
}>()

const container = ref<HTMLElement>()
const contentEl = ref<HTMLElement>()
const loading = ref(false)
const paraTexts = ref<Map<number, string>>(new Map())
const mammothHTML = ref('')

function render() {
  if (!mammothHTML.value || !contentEl.value) return
  paraTexts.value = new Map()
  contentEl.value.innerHTML = buildAnnotatedHTML(mammothHTML.value)
  contentEl.value.querySelectorAll('[data-annotation]').forEach(el => {
    el.addEventListener('click', (e: Event) => {
      e.stopPropagation()
      const annEl = el as HTMLElement
      const paraEl = annEl.closest('[data-para-index]') as HTMLElement | null
      if (paraEl) {
        const paraIndex = Number(paraEl.getAttribute('data-para-index'))
        const parts = annEl.getAttribute('data-annotation')!.split(',')
        const start = Number(parts[0])
        const end = Number(parts[1])
        const zoneType = parts[2]
        emit('annotationClick', paraIndex, start, end, zoneType)
      }
    })
  })
  nextTick(() => updateHighlight())
}

watch(() => props.fileUrl, async (url) => {
  if (!url) return
  loading.value = true
  const res = await fetch(url)
  const blob = await res.arrayBuffer()
  const result = await mammoth.convertToHtml({ arrayBuffer: blob })
  mammothHTML.value = result.value
  loading.value = false
  render()
}, { immediate: true })

watch(() => props.annotations, () => { render() }, { deep: true })
watch(() => props.selectedParagraph, () => { updateHighlight() })

function buildAnnotatedHTML(mammothHTML: string): string {
  const parser = new DOMParser()
  const dom = parser.parseFromString(mammothHTML, 'text/html')
  const paragraphs = dom.querySelectorAll('p')

  paragraphs.forEach((p, i) => {
    if (!p.textContent?.trim()) return
    const fullText = p.textContent || ''
    const docxIdx = props.docxIndices[i] ?? i
    paraTexts.value.set(docxIdx, fullText)

    const row = dom.createElement('div')
    row.className = 'para-row'

    const badge = dom.createElement('span')
    badge.className = 'para-badge'
    badge.textContent = String(docxIdx)
    row.appendChild(badge)

    const body = dom.createElement('span')
    body.className = 'para-body'

    const anns = props.annotations
      .filter(a => a.paragraph_index === docxIdx)
      .sort((a, b) => a.start_char - b.start_char)

    if (anns.length > 0) {
      body.setAttribute('data-para-index', String(docxIdx))
      let pos = 0
      for (const a of anns) {
        if (pos < a.start_char) {
          body.appendChild(dom.createTextNode(fullText.slice(pos, a.start_char)))
        }
        const span = dom.createElement('span')
        span.className = a.zone_type === 'fillable' ? 'fillable-zone' : 'fixed-zone'
        span.setAttribute('data-annotation', `${a.start_char},${a.end_char},${a.zone_type}`)
        span.textContent = fullText.slice(a.start_char, a.end_char)
        body.appendChild(span)
        pos = a.end_char
      }
      if (pos < fullText.length) {
        body.appendChild(dom.createTextNode(fullText.slice(pos)))
      }
    } else {
      body.setAttribute('data-para-index', String(docxIdx))
      body.textContent = fullText
    }

    row.appendChild(body)
    p.replaceWith(row)
  })

  return dom.body.innerHTML
}

function handleClick(e: MouseEvent) {
  const el = e.target as Element
  if (el?.closest?.('[data-annotation]')) return
  const sel = window.getSelection()
  if (sel && !sel.isCollapsed) return
  const target = el?.closest?.('[data-para-index]') as HTMLElement | null
  if (!target) return
  const index = Number(target.getAttribute('data-para-index'))
  emit('paragraphClick', index, paraTexts.value.get(index) || '')
}

function handleMouseUp() {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || !sel.rangeCount) return
  const range = sel.getRangeAt(0)
  let container: Node = range.commonAncestorContainer
  if (container.nodeType === Node.TEXT_NODE && container.parentElement) {
    container = container.parentElement
  }
  const paraEl = (container as Element)?.closest?.('[data-para-index]') as HTMLElement | null
  if (!paraEl) return
  const paraIndex = Number(paraEl.getAttribute('data-para-index'))
  const selectedText = sel.toString()
  const startChar = calcOffset(paraEl, range.startContainer, range.startOffset)
  const endChar = startChar + selectedText.length
  if (startChar >= 0 && endChar > startChar) {
    emit('textSelect', paraIndex, startChar, endChar, selectedText)
  }
}

function calcOffset(root: HTMLElement, targetNode: Node, targetOffset: number): number {
  let offset = 0
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let node = walker.nextNode()
  while (node) {
    if (node === targetNode) return offset + targetOffset
    if (node.textContent) offset += node.textContent.length
    node = walker.nextNode()
  }
  return -1
}

function updateHighlight() {
  if (!contentEl.value) return
  contentEl.value.querySelectorAll('.para-body.para-selected').forEach(el => el.classList.remove('para-selected'))
  if (props.selectedParagraph !== null) {
    const el = contentEl.value.querySelector(`[data-para-index="${props.selectedParagraph}"]`) as HTMLElement | null
    if (el) el.classList.add('para-selected')
  }
}
</script>

<style scoped>
.preview-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--paper-white);
}

.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-5);
  background: var(--paper-warm);
  border-bottom: 1px solid var(--rule);
  flex-shrink: 0;
}
.pane-title {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
}
.pane-meta {
  font-size: var(--text-xs);
  color: var(--ink-muted);
}

.loading-msg {
  text-align: center;
  padding: var(--space-6);
  color: var(--ink-muted);
}

.preview-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6);
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
}

/* Paragraph rows */
.preview-body :deep(.para-row) {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin: 1px 0;
  padding: var(--space-1) 0;
  border-radius: var(--radius-sm);
  border-left: 2px solid transparent;
  transition: background .15s;
}
.preview-body :deep(.para-row:hover) {
  background: var(--paper-warm);
}
.preview-body :deep(.para-badge) {
  flex-shrink: 0;
  width: 28px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  font-size: 10px;
  font-weight: 600;
  color: var(--ink-muted);
  background: var(--paper-hover);
  border-radius: var(--radius-sm);
  user-select: none;
  font-family: var(--font-mono);
}
.preview-body :deep(.para-body) {
  flex: 1;
  cursor: pointer;
  line-height: 2;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
}
.preview-body :deep(.para-body.para-selected) {
  background: var(--ink-blue-soft);
  border-left-color: var(--ink-blue);
}

/* Zone styles */
.preview-body :deep(.fillable-zone) {
  background: var(--ink-green-soft);
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  border-bottom: 2px solid var(--ink-green);
  cursor: pointer;
}
.preview-body :deep(.fixed-zone) {
  background: var(--vermilion-soft);
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  border-bottom: 2px solid var(--vermilion);
  cursor: pointer;
}
</style>
