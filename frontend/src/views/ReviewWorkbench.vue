<template>
  <div class="review-page">
    <!-- Setup form -->
    <div v-if="!showResult" class="setup-card">
      <h2 class="setup-title">审查工作台</h2>
      <el-form label-width="96px">
        <el-form-item label="选择模板">
          <el-select v-model="selectedTemplateId" placeholder="请选择模板" size="large">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="上传业务文件">
          <el-upload
            ref="uploadRef"
            drag
            multiple
            :auto-upload="false"
            :show-file-list="false"
            accept=".docx"
            :disabled="!selectedTemplateId"
            @change="handleFilesChange"
          >
            <el-icon :size="40"><UploadFilled /></el-icon>
            <div class="upload-text">将文件拖拽到此处，或<em>点击选择</em></div>
            <template #tip>
              <div class="upload-tip">支持 .docx 格式，可一次选择多个文件</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="uploadedDocs.length" label="已上传">
          <div class="file-tags">
            <el-tag
              v-for="(doc, idx) in uploadedDocs"
              :key="doc.id"
              closable
              :disable-transitions="false"
              @close="removeUploadedDoc(idx)"
            >{{ doc.name }}</el-tag>
          </div>
        </el-form-item>
        <el-form-item label="审查流程">
          <el-radio-group v-model="reviewMode" :disabled="!uploadedDocs.length">
            <el-radio value="compare">篡改比对</el-radio>
            <el-radio value="validate">数据校验</el-radio>
            <el-radio value="both">全部执行</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <div style="width:100%;text-align:center">
            <el-button type="primary" @click="startReview" :disabled="!uploadedDocs.length" :loading="reviewing" size="large">
              开始审查
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </div>

    <!-- Result view -->
    <div v-if="showResult" class="unified-review">
      <!-- Document tabs -->
      <div class="doc-tabs-bar">
        <button
          v-for="(doc, idx) in uploadedDocs"
          :key="doc.id"
          :class="['doc-tab', { active: idx === activeDocIdx }]"
          @click="activeDocIdx = idx"
        >{{ doc.name }}</button>
      </div>
      <div class="review-panels">
      <!-- Left: Template (collapsible) -->
      <div class="left-panel" :class="{ collapsed: !showTemplate }">
        <div class="panel-head">
          <span>模板原文</span>
          <el-button text size="small" @click="showTemplate = false">
            <el-icon><ArrowLeft /></el-icon>
          </el-button>
        </div>
        <div class="panel-body template-body">
          <template v-if="validateResult">
            <div v-for="p in templateParagraphs" :key="'t' + p.index" class="para-block">
              <span v-for="(seg, si) in p.segments" :key="si"
                :class="seg.type === 'fillable' ? 'tpl-fillable' : ''"
              >{{ seg.text }}</span>
            </div>
          </template>
          <template v-else-if="compareResult">
            {{ compareResult.template_text }}
          </template>
        </div>
      </div>

      <!-- Toggle when collapsed -->
      <div v-if="!showTemplate" class="left-toggle" @click="showTemplate = true">
        <el-icon><ArrowRight /></el-icon>
        <span class="toggle-label">模板</span>
      </div>

      <!-- Center: Document -->
      <div class="center-panel">
        <div class="panel-head">
          <span>实际文档</span>
          <span class="doc-meta">{{ activeDoc?.name }}</span>
        </div>
        <div class="panel-body doc-body" ref="docBody">
          <template v-for="item in displayItems" :key="item.key">
            <div v-if="item.type === 'placeholder'" class="deleted-placeholder">
              <span class="placeholder-text">该条款已删除</span>
            </div>
            <div v-else class="para-block"
              :ref="(el: any) => setParaRef(item.para.index, el)">
              <span v-for="(seg, si) in item.para.segments" :key="si"
                :class="segClass(seg.type)"
                :style="seg.type !== 'fixed' ? 'cursor:pointer' : ''"
                @click="seg.type !== 'fixed' && onSegmentClick(seg, item.para.index)"
              >{{ seg.type === 'diff-delete' ? '▍' : seg.text }}</span>
            </div>
          </template>
        </div>
      </div>

      <!-- Right: Results -->
      <div class="right-panel">
        <!-- Filter stamps -->
        <div class="filter-bar">
          <button :class="['stamp-btn', 'stamp-tamper', { active: resultFilter === 'tamper' }]"
            @click="resultFilter = 'tamper'" :disabled="!compareResult">
            篡改<span v-if="compareResult" class="stamp-num">{{ compareResult.violations.length }}</span>
          </button>
          <button :class="['stamp-btn', 'stamp-validate', { active: resultFilter === 'validate' }]"
            @click="resultFilter = 'validate'" :disabled="!validateResult">
            校验<span v-if="validateResult" class="stamp-num">{{ validateResult.results.length }}</span>
          </button>
          <button :class="['stamp-btn', 'stamp-all', { active: resultFilter === 'all' }]"
            @click="resultFilter = 'all'" :disabled="!compareResult && !validateResult">
            全部
          </button>
        </div>

        <!-- Comparison results -->
        <div v-if="compareResult && (resultFilter === 'tamper' || resultFilter === 'all')" class="result-block compare-block">
          <div class="block-head">
            <span>篡改比对</span>
            <el-tag v-if="compareResult.violations.length" type="danger" size="small">
              {{ compareResult.violations.length }} 处
            </el-tag>
            <el-tag v-else type="success" size="small">无篡改</el-tag>
          </div>
          <div class="block-body">
            <div v-if="!compareResult.violations.length" class="empty-state">
              <el-icon color="var(--ink-green)" :size="28"><CircleCheckFilled /></el-icon>
              <p>未发现篡改</p>
            </div>
            <div v-for="(v, i) in compareResult.violations" :key="'v' + i"
              class="vio-item" :ref="(el: any) => setVioRef(i, el)" @click="scrollToViolation(i)">
              <span class="vio-stamp" :class="'stamp-' + v.type">{{ stampLabel(v.type) }}</span>
              <div class="vio-body">
                <div class="vio-row tpl">模板：{{ v.type === 'insert' ? '(空)' : truncate(v.template_text) }}</div>
                <div class="vio-row act">实际：{{ v.type === 'delete' ? '(空)' : truncate(v.actual_text) }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Validation results -->
        <div v-if="validateResult && (resultFilter === 'validate' || resultFilter === 'all')" class="result-block validate-block">
          <div class="block-head">
            <span>数据校验</span>
            <span class="vali-summary">通过 {{ passCount }} / {{ validateResult.results.length }}</span>
          </div>
          <div class="block-body">
            <div v-for="(r, i) in validateResult.results" :key="'f' + i"
              class="field-item" :class="r.pass ? 'field-ok' : 'field-ng'"
              :ref="(el: any) => setFieldRef(i, el)" @click="scrollToField(i)">
              <div class="field-head">
                <span class="field-name">{{ r.field_name || '(未命名)' }}</span>
                <span class="field-badge" :class="r.pass ? 'badge-ok' : 'badge-ng'">
                  {{ r.pass ? '通过' : '不通过' }}
                </span>
              </div>
              <div class="field-rule">{{ r.rule }}</div>
              <div class="field-value">值：{{ r.actual_value || '(空)' }}</div>
              <div v-if="!r.pass" class="field-reason">{{ r.reason }}</div>
            </div>
          </div>
        </div>
      </div>
      </div><!-- .review-panels -->
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, CircleCheckFilled, UploadFilled } from '@element-plus/icons-vue'
import { listTemplates, uploadDocument, reviewCompare, reviewValidate } from '../api'
import type { TemplateInfo, DocumentInfo, CompareResult, ValidateResult, DiffSegment, FieldResult, ParagraphInfo } from '../types'

// State
const templates = ref<TemplateInfo[]>([])
const selectedTemplateId = ref<number | null>(null)
const uploadedDocs = ref<DocumentInfo[]>([])
const activeDocIdx = ref(0)
const reviewMode = ref<'compare' | 'validate' | 'both'>('compare')
const reviewing = ref(false)
const showResult = ref(false)

// Per-document review results
const docResults = reactive<Record<number, { compare: CompareResult | null; validate: ValidateResult | null }>>({})

const activeDoc = computed(() => uploadedDocs.value[activeDocIdx.value] || null)
const compareResult = computed(() => docResults[activeDoc.value?.id ?? 0]?.compare ?? null)
const validateResult = computed(() => docResults[activeDoc.value?.id ?? 0]?.validate ?? null)

const showTemplate = ref(false)
const resultFilter = ref<'tamper' | 'validate' | 'all'>('all')
const docBody = ref<HTMLDivElement | null>(null)
const paraRefs = ref<Record<number, HTMLElement>>({})
const vioRefs = ref<Record<number, HTMLElement>>({})
const fieldRefs = ref<Record<number, HTMLElement>>({})

function setVioRef(i: number, el: any) { if (el) vioRefs.value[i] = el }
function setFieldRef(i: number, el: any) { if (el) fieldRefs.value[i] = el }
function setParaRef(index: number, el: any) { if (el) paraRefs.value[index] = el }

onMounted(async () => { templates.value = await listTemplates() })

async function handleFilesChange(file: any) {
  if (!selectedTemplateId.value) return
  const tid = selectedTemplateId.value
  try {
    const doc = await uploadDocument(file.raw, tid)
    uploadedDocs.value.push(doc)
    ElMessage.success(`${file.name} 上传成功`)
  } catch {
    ElMessage.error(`${file.name} 上传失败`)
  }
}

function removeUploadedDoc(idx: number) {
  const doc = uploadedDocs.value[idx]
  if (!doc) return
  delete docResults[doc.id]
  uploadedDocs.value.splice(idx, 1)
  if (activeDocIdx.value >= uploadedDocs.value.length) {
    activeDocIdx.value = Math.max(0, uploadedDocs.value.length - 1)
  }
}

async function startReview() {
  if (!selectedTemplateId.value || !uploadedDocs.value.length) return
  reviewing.value = true
  const tid = selectedTemplateId.value
  for (const doc of uploadedDocs.value) {
    const did = doc.id
    const entry: { compare: CompareResult | null; validate: ValidateResult | null } = { compare: null, validate: null }
    if (reviewMode.value === 'compare' || reviewMode.value === 'both') {
      entry.compare = await reviewCompare(tid, did)
    }
    if (reviewMode.value === 'validate' || reviewMode.value === 'both') {
      entry.validate = await reviewValidate(tid, did)
    }
    docResults[did] = entry
  }
  showResult.value = true
  reviewing.value = false
}

const passCount = computed(() => {
  if (!validateResult.value) return 0
  return validateResult.value.results.filter(r => r.pass).length
})

// ---- Paragraph segmentation ----
interface TextSeg { type: 'fixed' | 'fillable'; text: string; pass?: boolean; fieldIdx?: string }

const templateParagraphs = computed(() => {
  const tps = validateResult.value?.template_paragraphs ?? []
  const fieldMap = buildTemplateFieldMap()
  return tps.map(p => ({
    index: p.index,
    segments: splitByFields(p.text, fieldMap[p.index] || [])
  }))
})

const docParagraphs = computed<ParagraphInfo[]>(() => {
  if (validateResult.value?.document_paragraphs?.length) return validateResult.value.document_paragraphs
  return activeDoc.value?.paragraphs ?? []
})

interface DocSeg { text: string; type: string; fieldIdx?: string; vioDocStart?: number }
interface RenderedPara { index: number; segments: DocSeg[] }

const renderedParagraphs = computed<RenderedPara[]>(() => {
  const paras = docParagraphs.value
  if (!paras.length) return []
  const fieldMap = buildFieldMap()
  const diffs = compareResult.value?.diffs ?? []
  const hasCompare = !!compareResult.value && (resultFilter.value === 'tamper' || resultFilter.value === 'all')
  const hasValidate = !!validateResult.value && (resultFilter.value === 'validate' || resultFilter.value === 'all')
  const globalOffsets: number[] = []
  let offset = 0
  for (const p of paras) { globalOffsets.push(offset); offset += p.text.length + 1 }
  return paras.map((p, pi) => {
    const fields = fieldMap[p.index] || []
    return { index: p.index, segments: buildUnifiedSegs(p.text, globalOffsets[pi], hasCompare ? diffs : [], hasValidate ? fields : []) }
  })
})

const displayItems = computed(() => {
  const mapping = validateResult.value?.paragraph_mapping
  if (!mapping) {
    return renderedParagraphs.value.map(p => ({ key: `p-${p.index}`, type: 'para' as const, para: p }))
  }
  // Reverse mapping: doc_index -> tpl_index
  const revMap: Record<number, number> = {}
  for (const [tplStr, doc] of Object.entries(mapping)) {
    if (doc !== null) revMap[doc as number] = Number(tplStr)
  }
  const items: Array<
    { key: string; type: 'para'; para: typeof renderedParagraphs.value[0] }
    | { key: string; type: 'placeholder'; templateIndex: number }
  > = []
  let lastTpl = -1
  for (const p of docParagraphs.value) {
    const tplIdx = revMap[p.index]
    if (tplIdx !== undefined) {
      for (let d = lastTpl + 1; d < tplIdx; d++) {
        items.push({ key: `del-${d}`, type: 'placeholder', templateIndex: d })
      }
      lastTpl = tplIdx
    }
    const rp = renderedParagraphs.value.find(r => r.index === p.index)
    if (rp) items.push({ key: `p-${p.index}`, type: 'para', para: rp })
  }
  const tplCount = validateResult.value?.template_paragraphs?.length ?? 0
  for (let d = lastTpl + 1; d < tplCount; d++) {
    items.push({ key: `del-${d}`, type: 'placeholder', templateIndex: d })
  }
  return items
})

function buildTemplateFieldMap(): Record<number, FieldResult[]> {
  const map: Record<number, FieldResult[]> = {}
  if (!validateResult.value) return map
  for (const r of validateResult.value.results) {
    if (!map[r.paragraph]) map[r.paragraph] = []
    map[r.paragraph].push(r)
  }
  return map
}

function buildFieldMap(): Record<number, FieldResult[]> {
  const map: Record<number, FieldResult[]> = {}
  if (!validateResult.value) return map
  const mapping = validateResult.value.paragraph_mapping ?? {}
  for (const r of validateResult.value.results) {
    const docPi = mapping[r.paragraph] ?? r.paragraph
    if (!map[docPi]) map[docPi] = []
    map[docPi].push(r)
  }
  return map
}

function splitByFields(text: string, fields: FieldResult[]): TextSeg[] {
  if (!text) return [{ type: 'fixed', text: '(空)' }]
  const sorted = [...fields].sort((a, b) => a.start_char - b.start_char)
  const segs: TextSeg[] = []
  let pos = 0
  for (const f of sorted) {
    if (f.start_char > pos) segs.push({ type: 'fixed', text: text.slice(pos, f.start_char) })
    segs.push({ type: 'fillable', text: text.slice(f.start_char, f.end_char) || '(空)', pass: f.pass, fieldIdx: f.paragraph + '_' + f.start_char })
    pos = f.end_char
  }
  if (pos < text.length) segs.push({ type: 'fixed', text: text.slice(pos) })
  return segs
}

function buildUnifiedSegs(paraText: string, paraGlobalStart: number, diffs: DiffSegment[], fields: FieldResult[]): DocSeg[] {
  const rawSegs = splitByFields(paraText, fields)
  if (!diffs.length) {
    return rawSegs.map(s => ({
      text: s.text,
      type: s.type === 'fillable' ? (s.pass ? 'field-pass' : 'field-fail') : 'fixed',
      fieldIdx: s.type === 'fillable' ? s.fieldIdx : undefined
    }))
  }
  const result: DocSeg[] = []
  for (const seg of rawSegs) {
    if (seg.type === 'fillable') {
      result.push({ text: seg.text, type: seg.pass ? 'field-pass' : 'field-fail', fieldIdx: seg.fieldIdx })
    } else {
      const subSegs = splitByDiffs(seg.text, paraGlobalStart, diffs)
      result.push(...subSegs.map(s => ({ text: s.text, type: s.type, vioDocStart: s.vioDocStart })))
    }
  }
  return result
}

function splitByDiffs(text: string, paraGlobalStart: number, diffs: DiffSegment[]): { text: string; type: string; vioDocStart?: number }[] {
  interface LocalDiff { start: number; end: number; type: string; vioDocStart?: number }
  const locals: LocalDiff[] = []
  for (const d of diffs) {
    if (d.type === 'equal') continue
    const ls = d.doc_range[0] - paraGlobalStart
    const le = d.doc_range[1] - paraGlobalStart
    if (d.type === 'delete') {
      if (ls >= 0 && ls <= text.length) locals.push({ start: ls, end: ls, type: 'diff-delete', vioDocStart: d.doc_range[0] })
      continue
    }
    if (le > 0 && ls < text.length) {
      locals.push({ start: Math.max(0, ls), end: Math.min(text.length, le), type: 'diff-' + d.type, vioDocStart: d.doc_range[0] })
    }
  }
  if (!locals.length) return [{ text, type: 'fixed' }]
  const segs: { text: string; type: string; vioDocStart?: number }[] = []
  let pos = 0
  for (const d of locals) {
    if (d.start > pos) segs.push({ text: text.slice(pos, d.start), type: 'fixed' })
    if (d.end > pos) segs.push({ text: text.slice(Math.max(pos, d.start), d.end), type: d.type, vioDocStart: d.vioDocStart })
    pos = Math.max(pos, d.end)
  }
  if (pos < text.length) segs.push({ text: text.slice(pos), type: 'fixed' })
  return segs
}

function segClass(type: string): Record<string, boolean> {
  const map: Record<string, Record<string, boolean>> = {
    'diff-insert': { 'seg-insert': true },
    'diff-replace': { 'seg-replace': true },
    'diff-delete': { 'seg-delete': true },
    'field-pass': { 'field-pass': true },
    'field-fail': { 'field-fail': true },
  }
  return map[type] || {}
}

function stampLabel(type: string): string {
  const map: Record<string, string> = { insert: '新增', delete: '删除', replace: '替换' }
  return map[type] || '变更'
}

function truncate(text: string): string {
  return text && text.length > 25 ? text.slice(0, 25) + '…' : text || '(空)'
}

// ---- Scroll navigation ----
function scrollToViolation(index: number) {
  if (!compareResult.value) return
  const violations = compareResult.value.violations ?? []
  if (index >= violations.length) return
  const v = violations[index]
  const dr = v.doc_range
  const paras = docParagraphs.value
  let prevPara: ParagraphInfo | null = null
  let goff = 0
  for (const p of paras) {
    const pend = goff + p.text.length
    if (dr[0] >= goff && dr[0] <= pend) {
      // Delete at paragraph boundary -> scroll to previous paragraph
      const targetIdx = (v.type === 'delete' && dr[0] === goff && prevPara)
        ? prevPara.index : p.index
      const el = paraRefs.value[targetIdx]
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        el.classList.add('flash-red')
        setTimeout(() => el.classList.remove('flash-red'), 1500)
      }
      return
    }
    prevPara = p
    goff = pend + 1
  }
}

function scrollToField(index: number) {
  if (!validateResult.value) return
  const field = validateResult.value.results[index]
  if (!field) return
  const mapping = validateResult.value?.paragraph_mapping ?? {}
  const docPi = mapping[field.paragraph] ?? field.paragraph
  const el = paraRefs.value[docPi]
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('flash-amber')
    setTimeout(() => el.classList.remove('flash-amber'), 1500)
  }
}

function onSegmentClick(seg: DocSeg, _paraIndex: number) {
  if (seg.fieldIdx) {
    const results = validateResult.value?.results ?? []
    for (let i = 0; i < results.length; i++) {
      const r = results[i]
      if (r.paragraph + '_' + r.start_char === seg.fieldIdx) {
        const el = fieldRefs.value[i]
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
          el.classList.add('flash-amber')
          setTimeout(() => el.classList.remove('flash-amber'), 1500)
        }
        break
      }
    }
  }
  if (seg.vioDocStart != null) {
    const violations = compareResult.value?.violations ?? []
    for (let i = 0; i < violations.length; i++) {
      if (violations[i].doc_range[0] === seg.vioDocStart) {
        const el = vioRefs.value[i]
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
          el.classList.add('flash-red')
          setTimeout(() => el.classList.remove('flash-red'), 1500)
        }
        break
      }
    }
  }
}
</script>

<style scoped>
/* ---- Page ---- */
.review-page { height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; }

/* ---- Setup ---- */
.setup-card {
  width: 620px;
  margin: var(--space-8) auto;
  align-self: center;
  padding: var(--space-6) var(--space-8);
  background: var(--paper-white);
  border: 1px solid var(--rule);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

/* Drag-and-drop upload */
.setup-card :deep(.el-upload-dragger) {
  padding: var(--space-3) var(--space-5);
  height: auto;
}
.upload-text {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--ink-muted);
}
.upload-text em {
  color: var(--ink-blue);
  font-style: normal;
}
.upload-tip {
  margin-top: var(--space-1);
  font-size: var(--text-xs);
  color: var(--ink-soft);
}
.file-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.setup-title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--ink);
  margin: 0 0 var(--space-5);
  text-align: center;
}

.setup-card :deep(.el-form-item:last-child) {
  margin-left: 0;
}
.setup-card :deep(.el-form-item:last-child .el-form-item__content) {
  margin-left: 0 !important;
  justify-content: center;
}

/* ---- Document tabs ---- */
.doc-tabs-bar {
  display: flex;
  flex-shrink: 0;
  gap: 0;
  background: var(--paper-white);
  border-bottom: 1px solid var(--rule);
  overflow-x: auto;
}
.doc-tab {
  padding: var(--space-2) var(--space-4);
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--ink-muted);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all .15s;
}
.doc-tab:hover { color: var(--ink); background: var(--paper-hover); }
.doc-tab.active {
  color: var(--ink);
  border-bottom-color: var(--ink);
  font-weight: 600;
}

/* ---- Review panels (3-col after tabs) ---- */
.review-panels {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ---- Unified review layout ---- */
.unified-review {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  width: 100%;
}

/* Left panel */
.left-panel {
  width: 280px;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--rule);
  background: var(--paper-warm);
  transition: width .25s, min-width .25s, opacity .2s;
}
.left-panel.collapsed {
  width: 0; min-width: 0; overflow: hidden; opacity: 0; pointer-events: none;
}
.left-toggle {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 28px;
  min-width: 28px;
  cursor: pointer;
  background: var(--paper-warm);
  border-right: 1px solid var(--rule);
  color: var(--ink-muted);
  font-size: var(--text-xs);
  user-select: none;
  transition: background .15s;
}
.left-toggle:hover { background: var(--paper-hover); color: var(--ink); }
.toggle-label { letter-spacing: 3px; }

/* Center panel */
.center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--paper-white);
}

/* Right panel */
.right-panel {
  width: 350px;
  min-width: 350px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-left: 1px solid var(--rule);
  background: var(--paper-warm);
}

/* Panel heads */
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  background: var(--paper-warm);
  border-bottom: 1px solid var(--rule);
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  flex-shrink: 0;
}
.center-panel .panel-head { background: var(--paper-white); }
.doc-meta { font-family: var(--font-body); font-weight: 400; font-size: var(--text-xs); color: var(--ink-muted); }

/* Panel bodies */
.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4);
  line-height: 2;
}
.template-body {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: var(--text-sm);
  color: var(--ink-soft);
}
.template-body .para-block + .para-block {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px dashed var(--rule);
}
.doc-body {
  font-family: var(--font-display);
  font-size: 16px;
  color: var(--ink);
  padding: var(--space-5) var(--space-6);
  line-height: 1.9;
}
.doc-body .para-block + .para-block {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px dashed var(--rule-light);
}

.deleted-placeholder {
  padding: var(--space-3) var(--space-2);
  margin: var(--space-3) 0;
  border: 1px dashed var(--vermilion);
  border-left: 3px solid var(--vermilion);
  background: var(--vermilion-soft);
  border-radius: var(--radius-sm);
  text-align: center;
}
.placeholder-text {
  font-size: var(--text-sm);
  color: var(--vermilion);
  font-weight: 500;
}
.deleted-placeholder + .para-block {
  border-top: none;
  margin-top: 0;
  padding-top: 0;
}

/* Template fillable mark */
.tpl-fillable {
  background: var(--amber-soft);
  padding: 1px 3px;
  border-radius: var(--radius-sm);
  border-bottom: 2px dashed var(--amber);
}

/* ---- Diff segments ---- */
.seg-insert {
  background: var(--vermilion-soft);
  border-bottom: 2px solid var(--vermilion);
  padding: 1px 2px;
  border-radius: 2px;
}
.seg-delete {
  display: inline-block;
  color: var(--paper-white);
  background: var(--vermilion);
  font-size: 10px;
  font-weight: 700;
  padding: 0 3px;
  border-radius: var(--radius-sm);
  margin: 0 1px;
}
.seg-replace {
  background: var(--vermilion-soft);
  border-bottom: 2px solid var(--vermilion);
  padding: 1px 2px;
  border-radius: 2px;
}

/* Field segments */
.field-pass {
  background: var(--ink-green-soft);
  padding: 1px 3px;
  border-radius: var(--radius-sm);
  border-bottom: 2px solid var(--ink-green);
}
.field-fail {
  background: var(--amber-soft);
  padding: 1px 3px;
  border-radius: var(--radius-sm);
  border-bottom: 2px solid var(--amber);
}

/* Flash animations */
.flash-red { animation: flashRed 0.4s ease 3; }
@keyframes flashRed { 50% { background: var(--vermilion-soft); } }
.flash-amber { animation: flashAmber 0.4s ease 3; }
@keyframes flashAmber { 50% { background: var(--amber-soft); } }

/* ---- Filter bar: stamp buttons ---- */
.filter-bar {
  display: flex;
  flex-shrink: 0;
  padding: var(--space-3) var(--space-3) 0;
  gap: var(--space-2);
}
.stamp-btn {
  flex: 1;
  padding: var(--space-2) var(--space-2);
  border: 1.5px solid var(--rule);
  background: var(--paper-white);
  color: var(--ink-soft);
  font-size: var(--text-xs);
  font-weight: 600;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all .15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  position: relative;
}
.stamp-btn:hover:not(:disabled) { border-color: var(--ink-muted); color: var(--ink); }
.stamp-btn:disabled { opacity: .3; cursor: not-allowed; }
.stamp-btn.active { color: var(--paper-white); }

.stamp-tamper.active { background: var(--vermilion); border-color: var(--vermilion); }
.stamp-validate.active { background: var(--amber); border-color: var(--amber); }
.stamp-all.active { background: var(--ink); border-color: var(--ink); }

.stamp-num {
  font-size: 10px;
  font-weight: 500;
  opacity: .7;
  min-width: 16px;
}

/* ---- Result blocks ---- */
.result-block {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.result-block + .result-block { border-top: 3px solid var(--rule); }

.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  flex-shrink: 0;
}
.compare-block .block-head { background: var(--vermilion-soft); border-bottom: 1px solid var(--vermilion-border); }
.validate-block .block-head { background: var(--amber-soft); border-bottom: 1px solid var(--amber-border); }
.vali-summary { font-weight: 400; font-size: var(--text-xs); color: var(--amber); }

.block-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3);
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: var(--space-5) 0;
  color: var(--ink-green);
}
.empty-state p { margin-top: var(--space-2); font-size: var(--text-sm); }

/* Violation items */
.vio-item {
  padding: var(--space-3);
  border: 1px solid var(--vermilion-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
  cursor: pointer;
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  background: var(--paper-white);
  transition: all .15s;
}
.vio-item:hover { background: var(--vermilion-soft); }
.vio-stamp {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 22px;
  padding: 0 5px;
  font-size: 10px;
  font-weight: 700;
  border: 1.5px solid;
  border-radius: var(--radius-sm);
  transform: rotate(-3deg);
}
.vio-stamp.stamp-insert { color: var(--ink-blue); border-color: var(--ink-blue); }
.vio-stamp.stamp-delete { color: var(--vermilion); border-color: var(--vermilion); }
.vio-stamp.stamp-replace { color: var(--amber); border-color: var(--amber); }
.vio-body { min-width: 0; }
.vio-row { font-size: var(--text-xs); line-height: 1.8; word-break: break-all; }
.vio-row.tpl { color: var(--ink-muted); }
.vio-row.act { color: var(--vermilion); }

/* Field items */
.field-item {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
  cursor: pointer;
  background: var(--paper-white);
  transition: all .15s;
}
.field-ok { border: 1px solid var(--ink-green-border); border-left: 3px solid var(--ink-green); }
.field-ok:hover { background: var(--ink-green-soft); }
.field-ng { border: 1px solid var(--amber-border); border-left: 3px solid var(--amber); }
.field-ng:hover { background: var(--amber-soft); }

.field-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-1); }
.field-name { font-weight: 600; font-size: var(--text-sm); }
.field-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 10px;
}
.badge-ok { background: var(--ink-green-soft); color: var(--ink-green); }
.badge-ng { background: var(--amber-soft); color: var(--amber); }

.field-rule { font-size: var(--text-xs); color: var(--ink-muted); }
.field-value { font-size: var(--text-sm); color: var(--ink); margin-top: var(--space-1); word-break: break-all; }
.field-reason { margin-top: var(--space-1); font-size: var(--text-xs); color: var(--vermilion); }
</style>
