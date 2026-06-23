<template>
  <div class="review-layout validate-theme">
    <!-- Left panel: Template (collapsible) -->
    <div class="left-panel" :class="{ collapsed: !showTemplate }">
      <div class="panel-header">
        <span>模板原文</span>
        <el-button text size="small" @click="showTemplate = false">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
      </div>
      <div class="panel-body template-body">
        <div v-for="p in templateParagraphs" :key="'t' + p.index" class="para-block">
          <span v-for="(seg, si) in p.segments" :key="si"
            :class="seg.type === 'fillable' ? 'tpl-fillable' : ''"
          >{{ seg.text }}</span>
        </div>
      </div>
    </div>

    <!-- Toggle button when left collapsed -->
    <div v-if="!showTemplate" class="left-toggle" @click="showTemplate = true">
      <el-icon><ArrowRight /></el-icon>
      <span class="toggle-label">模板</span>
    </div>

    <!-- Center panel: Document with validation highlights -->
    <div class="center-panel">
      <div class="panel-header">
        <span>实际文档</span>
        <span class="doc-name">已上传文件</span>
      </div>
      <div class="panel-body doc-body">
        <div v-for="p in docParagraphs" :key="'d' + p.index" class="para-block" :ref="(el: any) => setParaRef(p.index, el)">
          <span v-for="(seg, si) in p.segments" :key="si"
            :class="seg.type === 'fillable' ? (seg.pass ? 'fill-pass' : 'fill-fail') : ''"
          >{{ seg.text }}</span>
        </div>
      </div>
    </div>

    <!-- Right panel: Field results -->
    <div class="right-panel">
      <div class="panel-header">
        <span>校验结果</span>
        <span class="result-summary">通过 {{ passCount }} / 共 {{ result.results.length }}</span>
      </div>
      <div class="panel-body">
        <div v-for="(r, i) in result.results" :key="i" class="field-item" :class="{ fail: !r.pass }" @click="scrollToField(i)">
          <div class="field-head">
            <span class="field-name">{{ r.field_name || '(未命名)' }}</span>
            <el-tag :type="r.pass ? 'success' : 'danger'" size="small">{{ r.pass ? '通过' : '不通过' }}</el-tag>
          </div>
          <div class="field-rule">{{ r.rule }}</div>
          <div class="field-value">值：{{ r.actual_value || '(空)' }}</div>
          <div v-if="!r.pass" class="field-reason">{{ r.reason }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import type { FieldResult, ValidateResult, ParagraphInfo } from '../types'

const props = defineProps<{ result: ValidateResult }>()

const showTemplate = ref(false)
const paraRefs = ref<Record<number, HTMLElement>>({})

function setParaRef(index: number, el: any) {
  if (el) paraRefs.value[index] = el
}

const passCount = computed(() => props.result.results.filter(r => r.pass).length)

interface TextSeg { type: 'fixed' | 'fillable'; text: string; pass?: boolean }

// Build a map: paragraph_index -> array of field results
const paraFieldsMap = computed(() => {
  const map: Record<number, FieldResult[]> = {}
  for (const r of props.result.results) {
    if (!map[r.paragraph]) map[r.paragraph] = []
    map[r.paragraph].push(r)
  }
  return map
})

// Template: show ALL paragraphs with fillable zones highlighted
const templateParagraphs = computed(() => {
  const allParas = props.result.template_paragraphs ?? []
  return allParas.map(p => ({
    index: p.index,
    segments: splitWithFields(p.text, paraFieldsMap.value[p.index] || [])
  }))
})

// Document: show ALL paragraphs with fillable zones highlighted (pass/fail)
const docParagraphs = computed(() => {
  const allParas = props.result.document_paragraphs ?? []
  return allParas.map(p => ({
    index: p.index,
    segments: splitWithFields(p.text, paraFieldsMap.value[p.index] || [], true)
  }))
})

function splitWithFields(text: string, fields: FieldResult[], markPass?: boolean): TextSeg[] {
  if (!text) return [{ type: 'fixed', text: '(空)' }]
  const sorted = [...fields].sort((a, b) => a.start_char - b.start_char)
  const segs: TextSeg[] = []
  let pos = 0
  for (const f of sorted) {
    if (f.start_char > pos) {
      segs.push({ type: 'fixed', text: text.slice(pos, f.start_char) })
    }
    segs.push({
      type: 'fillable',
      text: text.slice(f.start_char, f.end_char) || '(空)',
      pass: markPass ? f.pass : undefined
    })
    pos = f.end_char
  }
  if (pos < text.length) {
    segs.push({ type: 'fixed', text: text.slice(pos) })
  }
  return segs
}

function scrollToField(index: number) {
  const field = props.result.results[index]
  if (!field) return
  const el = paraRefs.value[field.paragraph]
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('flash-highlight')
    setTimeout(() => el.classList.remove('flash-highlight'), 1500)
  }
}
</script>

<style scoped>
/* Layout */
.review-layout {
  height: 100%;
  display: flex;
  gap: 0;
  overflow: hidden;
}

/* Left panel */
.left-panel {
  width: 280px;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  border-right: 2px solid #faecd8;
  background: #fefcf6;
  transition: width 0.25s, min-width 0.25s, opacity 0.2s;
}
.left-panel.collapsed {
  width: 0;
  min-width: 0;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
}

.left-toggle {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 28px;
  min-width: 28px;
  cursor: pointer;
  background: #fefcf6;
  border-right: 2px solid #faecd8;
  color: #e6a23c;
  font-size: 12px;
  user-select: none;
  transition: background 0.2s;
}
.left-toggle:hover { background: #fdf6ec; }
.toggle-label { letter-spacing: 2px; }

/* Center panel */
.center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #fff;
}

/* Right panel */
.right-panel {
  width: 320px;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  border-left: 2px solid #faecd8;
  background: #fffdf7;
}

/* Panel header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #fdf6ec;
  border-bottom: 1px solid #faecd8;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  flex-shrink: 0;
}

.result-summary { font-weight: 400; font-size: 12px; color: #e6a23c; }

/* Panel body */
.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  line-height: 2;
}

.template-body {
  font-size: 13px;
  color: #606266;
}
.template-body .para-block + .para-block { margin-top: 12px; padding-top: 12px; border-top: 1px dashed #faecd8; }

.doc-body {
  font-size: 15px;
  color: #303133;
  padding: 20px 24px;
}
.doc-body .para-block + .para-block { margin-top: 12px; padding-top: 12px; border-top: 1px dashed #ebeef5; }

/* Fillable highlight styles */
.tpl-fillable {
  background: #faecd8;
  padding: 1px 3px;
  border-radius: 3px;
  border-bottom: 2px dashed #e6a23c;
}

.fill-pass {
  background: #d4edda;
  padding: 1px 3px;
  border-radius: 3px;
  border-bottom: 2px solid #67c23a;
}
.fill-fail {
  background: #fdf6ec;
  padding: 1px 3px;
  border-radius: 3px;
  border-bottom: 2px solid #e6a23c;
}

.flash-highlight {
  animation: flash 0.4s ease 3;
}
@keyframes flash {
  50% { background: #f5dab1; }
}

/* Field result items */
.field-item {
  padding: 10px 12px;
  border: 1px solid #faecd8;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  background: #fff;
  transition: background 0.15s;
}
.field-item:hover { background: #fef9f0; }
.field-item.fail { border-color: #f5dab1; background: #fffdf5; }
.field-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.field-name { font-weight: 600; font-size: 13px; }
.field-rule { font-size: 12px; color: #909399; }
.field-value { font-size: 13px; color: #303133; margin-top: 4px; word-break: break-all; }
.field-reason { margin-top: 4px; font-size: 12px; color: #e6a23c; }

.doc-name { font-weight: 400; font-size: 12px; color: #909399; }
</style>
