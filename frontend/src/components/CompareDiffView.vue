<template>
  <div class="review-layout compare-theme">
    <!-- Left panel: Template (collapsible) -->
    <div class="left-panel" :class="{ collapsed: !showTemplate }">
      <div class="panel-header">
        <span>模板原文</span>
        <el-button text size="small" @click="showTemplate = false">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
      </div>
      <div class="panel-body template-body">{{ result.template_text }}</div>
    </div>

    <!-- Toggle button when left collapsed -->
    <div v-if="!showTemplate" class="left-toggle" @click="showTemplate = true">
      <el-icon><ArrowRight /></el-icon>
      <span class="toggle-label">模板</span>
    </div>

    <!-- Center panel: Document with inline diffs -->
    <div class="center-panel">
      <div class="panel-header">
        <span>实际文档</span>
        <span class="doc-name">已上传文件</span>
      </div>
      <div class="panel-body doc-body" ref="docBody">
        <span v-for="(seg, i) in docSegments" :key="i"
          :class="'seg-' + seg.type"
          :ref="(el: any) => setSegRef(i, el)"
        >{{ seg.text }}</span>
      </div>
    </div>

    <!-- Right panel: Violations -->
    <div class="right-panel">
      <div class="panel-header">
        <span>差异详情</span>
        <el-tag v-if="violations.length" type="danger" size="small">{{ violations.length }} 处</el-tag>
        <el-tag v-else type="success" size="small">无篡改</el-tag>
      </div>
      <div class="panel-body">
        <div v-if="!violations.length" class="no-violations">
          <el-icon color="#67c23a" :size="32"><CircleCheckFilled /></el-icon>
          <p>未发现篡改</p>
        </div>
        <div v-for="(v, i) in violations" :key="i" class="vio-item" @click="scrollToViolation(i)">
          <div class="vio-type">
            <el-tag type="danger" size="small">篡改</el-tag>
          </div>
          <div class="vio-detail">
            <div class="vio-row tpl">模板：{{ truncate(v.template_text) }}</div>
            <div class="vio-row act">实际：{{ truncate(v.actual_text) }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowLeft, ArrowRight, CircleCheckFilled } from '@element-plus/icons-vue'
import type { CompareResult } from '../types'

const props = defineProps<{ result: CompareResult }>()

const showTemplate = ref(false)
const docBody = ref<HTMLDivElement | null>(null)
const segRefs = ref<Record<number, HTMLElement>>({})

function setSegRef(i: number, el: any) {
  if (el) segRefs.value[i] = el
}

const violations = computed(() => props.result.violations ?? [])

interface DocSeg { type: string; text: string }

const docSegments = computed<DocSeg[]>(() => {
  const diffs = props.result.diffs ?? []
  const docText = props.result.document_text ?? ''
  if (!diffs.length && docText) return [{ type: 'equal', text: docText }]
  if (!diffs.length) return []

  const segs: DocSeg[] = []
  let pos = 0
  for (const d of diffs) {
    const [i1, i2] = d.doc_range
    if (d.type === 'delete') continue
    // Text before this diff (gap fill with equal)
    if (pos < i1) {
      segs.push({ type: 'equal', text: docText.slice(pos, i1) })
    }
    segs.push({ type: d.type, text: docText.slice(i1, i2) || d.value })
    pos = i2
  }
  if (pos < docText.length) {
    segs.push({ type: 'equal', text: docText.slice(pos) })
  }
  return segs
})

function truncate(text: string): string {
  return text && text.length > 25 ? text.slice(0, 25) + '…' : text || '(空)'
}

function scrollToViolation(index: number) {
  // Find the diff segment that matches this violation
  const diffs = props.result.diffs ?? []
  if (index >= diffs.length) return

  const diff = diffs[index]
  // Find the corresponding segment ref
  let segIdx = 0
  for (let i = 0; i <= index; i++) {
    if (diffs[i].type === 'delete') continue
    segIdx = i
  }

  const el = segRefs.value[segIdx]
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
  border-right: 2px solid #fde2e2;
  background: #fefafa;
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
  background: #fefafa;
  border-right: 2px solid #fde2e2;
  color: #f56c6c;
  font-size: 12px;
  user-select: none;
  transition: background 0.2s;
}
.left-toggle:hover { background: #fef0f0; }
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
  border-left: 2px solid #fde2e2;
  background: #fffbfb;
}

/* Panel header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #fef0f0;
  border-bottom: 1px solid #fde2e2;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  flex-shrink: 0;
}

/* Panel body */
.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  line-height: 2;
}

.template-body {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 13px;
  color: #606266;
}

.doc-body {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 15px;
  color: #303133;
  padding: 20px 24px;
}

/* Diff segment styles */
.seg-equal { color: #303133; }
.seg-insert {
  background: #d4edda;
  border-bottom: 2px solid #67c23a;
  padding: 1px 2px;
  border-radius: 2px;
}
.seg-replace {
  background: #fce4e4;
  border-bottom: 2px solid #f89898;
  padding: 1px 2px;
  border-radius: 2px;
}

.flash-highlight {
  animation: flash 0.4s ease 3;
}
@keyframes flash {
  50% { background: #fab6b6; }
}

/* Violation items */
.vio-item {
  padding: 10px 12px;
  border: 1px solid #fde2e2;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  display: flex;
  gap: 8px;
  align-items: flex-start;
  background: #fff;
  transition: background 0.15s;
}
.vio-item:hover { background: #fef0f0; }
.vio-type { flex-shrink: 0; }
.vio-detail { min-width: 0; }
.vio-row { font-size: 13px; line-height: 1.8; word-break: break-all; }
.vio-row.tpl { color: #909399; }
.vio-row.act { color: #f56c6c; }

.no-violations {
  text-align: center;
  padding: 32px 0;
  color: #67c23a;
}
.no-violations p { margin-top: 8px; font-size: 14px; }

.doc-name { font-weight: 400; font-size: 12px; color: #909399; }
</style>
