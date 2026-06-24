<template>
  <div class="toolbar">
    <div class="tb-head">
      <h3 class="tb-title">标注工具</h3>
      <p class="tb-hint">点击段落，拖选文字进行区域标记</p>
    </div>

    <!-- Current paragraph info -->
    <div v-if="currentParagraph !== null" class="info-block">
      <div class="info-label">段落 {{ currentParagraph }}</div>
      <p class="info-text">{{ paraText }}</p>
    </div>

    <!-- Selection actions -->
    <div v-if="currentParagraph !== null" class="actions-area">
      <div v-if="selectedText" class="sel-block">
        <p class="sel-label">已选中</p>
        <p class="sel-text">"{{ selectedText }}"</p>
        <p class="sel-range">字符 {{ selectedStart }}–{{ selectedEnd }}</p>
        <div class="btn-row">
          <button class="mark-btn fixed" @click="mark('fixed')">标记为固定区</button>
          <button class="mark-btn fillable" @click="mark('fillable')">标记为填充区</button>
          <button class="mark-btn variable" @click="mark('variable')">标记为可变条款</button>
        </div>
      </div>
      <p v-else class="tb-hint">拖选文字标记范围</p>

      <!-- Clicked annotation -->
      <div v-if="clickedAnnotation" class="sel-block clicked">
        <p class="info-label">已标注区域</p>
        <p class="sel-range">段落{{ clickedAnnotation.paraIndex }} · 字符{{ clickedAnnotation.startChar }}</p>
        <div class="btn-row">
          <button v-if="clickedAnnotation.zoneType === 'fillable'" class="mark-btn edit" @click="editClickedAnnotation">编辑规则</button>
          <button class="mark-btn cancel" @click="cancelCurrentAnnotation">取消标注</button>
        </div>
      </div>

      <button class="mark-btn whole" @click="markWholePara('fixed')">标记整段为固定区</button>

      <!-- Rules config -->
      <div v-if="showFillableRules" class="rules-box">
        <h4 class="rules-title">{{ editingAnnotation ? `编辑规则` : '填写校验规则' }}</h4>
        <el-form label-width="72px" size="small">
          <el-form-item label="字段名称">
            <el-input v-model="rules.field_name" placeholder="如：公司名称" />
          </el-form-item>
          <el-form-item label="必填">
            <el-switch v-model="rules.required" />
          </el-form-item>
          <el-form-item label="最少字数">
            <el-input-number v-model="rules.min_chars" :min="0" :max="500" />
          </el-form-item>
          <el-form-item label="最多字数">
            <el-input-number v-model="rules.max_chars" :min="1" :max="1000" />
          </el-form-item>
          <el-form-item label="字符类型">
            <el-select v-model="rules.allowed_chars">
              <el-option label="不限制" value="any" />
              <el-option label="仅中文" value="chinese" />
              <el-option label="仅数字" value="number" />
              <el-option label="字母/数字/中文" value="alphanumeric" />
              <el-option label="正则表达式" value="regex" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="rules.allowed_chars === 'regex'" label="正则">
            <el-input v-model="rules.regex" placeholder="如: ^1[3-9]\d{9}$" />
          </el-form-item>
          <el-form-item label="允许值">
            <div class="av-list">
              <el-tag v-for="(v, i) in rules.allowed_values" :key="i" closable size="small"
                @close="removeAllowedValue(i)">{{ v }}</el-tag>
              <span v-if="rules.allowed_values.length === 0" class="av-empty">暂无，请在下方添加</span>
            </div>
            <div class="av-input-row">
              <el-input v-model="allowedValueInput" placeholder="输入允许值后回车" size="small"
                @keyup.enter="addAllowedValue" />
              <el-button @click="addAllowedValue" size="small" :disabled="!allowedValueInput.trim()">添加</el-button>
            </div>
          </el-form-item>
          <el-form-item label="匹配字段">
            <el-select v-model="rules.match_fields" multiple clearable placeholder="选择需一致的字段"
              size="small" style="width:100%">
              <el-option v-for="name in availableMatchFields" :key="name" :label="name" :value="name" />
            </el-select>
          </el-form-item>
          <el-divider style="margin:8px 0">金额大写关联</el-divider>
          <el-form-item label="大写字段">
            <el-select v-model="rules.amount_match_field" clearable placeholder="选择关联的大写字段"
              size="small" style="width:100%">
              <el-option v-for="name in availableMatchFields" :key="name" :label="name" :value="name" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="rules.amount_match_field" label="数字单位">
            <el-select v-model="rules.amount_unit" size="small" style="width:100%">
              <el-option label="元（×1）" :value="1" />
              <el-option label="千元（×1000）" :value="1000" />
              <el-option label="万元（×10000）" :value="10000" />
            </el-select>
          </el-form-item>
          <el-divider style="margin:8px 0">勾选类规则</el-divider>
          <el-form-item label="单选组名">
            <el-input v-model="rules.radio_group" placeholder="输入组名，同组互斥" size="small" />
          </el-form-item>
          <el-form-item label="管辖段落">
            <el-select v-model="rules.dependent_paras" multiple clearable
              placeholder="选择从属段落号" size="small" style="width:100%">
              <el-option v-for="idx in paraIndices" :key="idx"
                :label="'段落 ' + idx" :value="idx" />
            </el-select>
          </el-form-item>
          <div class="btn-row">
            <el-button type="primary" @click="confirmFillable">确认规则</el-button>
            <el-button @click="showFillableRules = false">取消</el-button>
          </div>
        </el-form>
      </div>
    </div>

    <div class="tb-divider"></div>

    <!-- Annotation list -->
    <div v-show="!showFillableRules" class="ann-section">
      <h4 class="ann-title">已标注列表 <span class="ann-count">{{ annotations.length }}</span></h4>
      <div class="ann-filter">
        <button :class="['ann-fbtn', { active: annFilter === 'all' }]" @click="annFilter = 'all'">
          全部 <span class="fbtn-num">{{ annotations.length }}</span>
        </button>
        <button :class="['ann-fbtn', 'fbtn-fillable', { active: annFilter === 'fillable' }]" @click="annFilter = 'fillable'">
          填充 <span class="fbtn-num">{{ fillableCount }}</span>
        </button>
        <button :class="['ann-fbtn', 'fbtn-fixed', { active: annFilter === 'fixed' }]" @click="annFilter = 'fixed'">
          固定 <span class="fbtn-num">{{ fixedCount }}</span>
        </button>
        <button :class="['ann-fbtn', 'fbtn-variable', { active: annFilter === 'variable' }]" @click="annFilter = 'variable'">
          可变 <span class="fbtn-num">{{ variableCount }}</span>
        </button>
      </div>
      <div class="ann-list">
        <div v-if="filteredAnnotations.length === 0" class="ann-empty">暂无标注</div>
        <div v-for="a in filteredAnnotations" :key="`${a.paragraph_index}_${a.start_char}`"
          class="ann-item" :ref="(el: any) => setAnnRef(a.paragraph_index, a.start_char, el)"
          @click="handleAnnItemClick(a)">
          <span class="ann-tag" :class="a.zone_type">
            {{ a.zone_type === 'fixed' ? '固定' : a.zone_type === 'variable' ? '可变' : '填充' }}
          </span>
          <span class="ann-loc">段{{ a.paragraph_index }} [{{ a.start_char }},{{ a.end_char }}]</span>
          <span v-if="a.rules?.field_name" class="ann-field">{{ a.rules.field_name }}</span>
          <button class="ann-del" @click.stop="$emit('removeAnnotation', a.paragraph_index, a.start_char)">
            <el-icon :size="14"><Delete /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <el-button type="primary" @click="save" :loading="saving" size="large" style="width:100%">
      保存标注
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import type { AnnotationItem, ValidationRule } from '../types'

const props = defineProps<{
  currentParagraph: number | null
  paraText: string
  annotations: AnnotationItem[]
  saving: boolean
  selectedText: string
  selectedStart: number | null
  selectedEnd: number | null
  clickedAnnotation: { paraIndex: number; startChar: number; zoneType: string } | null
  paraIndices: number[]
}>()

const emit = defineEmits<{
  markSelection: [item: AnnotationItem]
  save: []
  selectPara: [index: number]
  removeAnnotation: [paraIndex: number, startChar: number]
  cancelAnnotation: [paraIndex: number, startChar: number]
  updateAnnotation: [item: AnnotationItem]
  focusAnnotation: [paraIndex: number, startChar: number]
}>()

const showFillableRules = ref(false)
const editingAnnotation = ref<{ paraIndex: number; startChar: number } | null>(null)
const annFilter = ref<'all' | 'fillable' | 'fixed' | 'variable'>('all')
const allowedValueInput = ref('')

const fillableCount = computed(() => props.annotations.filter(a => a.zone_type === 'fillable').length)
const fixedCount = computed(() => props.annotations.filter(a => a.zone_type === 'fixed').length)
const variableCount = computed(() => props.annotations.filter(a => a.zone_type === 'variable').length)
const filteredAnnotations = computed(() => {
  if (annFilter.value === 'all') return props.annotations
  return props.annotations.filter(a => a.zone_type === annFilter.value)
})

const availableMatchFields = computed(() => {
  const ownName = editingAnnotation.value
    ? props.annotations.find(a => a.paragraph_index === editingAnnotation.value!.paraIndex && a.start_char === editingAnnotation.value!.startChar)?.rules?.field_name
    : rules.value.field_name
  const names: string[] = []
  for (const a of props.annotations) {
    if (a.zone_type === 'fillable' && a.rules?.field_name && a.rules.field_name !== ownName) {
      names.push(a.rules.field_name)
    }
  }
  return [...new Set(names)]
})

const rules = ref<ValidationRule>({
  required: true, min_chars: 1, max_chars: 200,
  allowed_chars: 'any', regex: '', field_name: '',
  allowed_values: [], match_fields: [],
  radio_group: '',
  dependent_paras: [],
  amount_match_field: '',
  amount_unit: 1
})

const annRefs = ref<Record<string, HTMLElement>>({})
function setAnnRef(paraIndex: number, startChar: number, el: any) {
  if (el) annRefs.value[`${paraIndex}_${startChar}`] = el
}

watch(() => props.clickedAnnotation, (val) => {
  if (!val) return
  nextTick(() => {
    const key = `${val.paraIndex}_${val.startChar}`
    const el = annRefs.value[key]
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('ann-flash')
      setTimeout(() => el.classList.remove('ann-flash'), 1200)
    }
  })
  if (val.zoneType === 'fillable') {
    const ann = props.annotations.find(
      a => a.paragraph_index === val.paraIndex && a.start_char === val.startChar
    )
    if (ann?.rules) {
      rules.value = Object.assign(
        { required: true, min_chars: 1, max_chars: 200, allowed_chars: 'any', regex: '', field_name: '', allowed_values: [], match_fields: [], radio_group: '', dependent_paras: [], amount_match_field: '', amount_unit: 1 },
        ann.rules
      )
    } else {
      rules.value = { required: true, min_chars: 1, max_chars: 200, allowed_chars: 'any', regex: '', field_name: '', allowed_values: [], match_fields: [], radio_group: '', dependent_paras: [], amount_match_field: '', amount_unit: 1 }
    }
    editingAnnotation.value = { paraIndex: val.paraIndex, startChar: val.startChar }
    showFillableRules.value = true
  }
})

watch(() => props.selectedText, () => { showFillableRules.value = false })

function mark(zone: 'fixed' | 'fillable' | 'variable') {
  if (props.currentParagraph === null) return
  if (props.selectedStart === null || props.selectedEnd === null) return
  editingAnnotation.value = null
  if (zone === 'fillable') {
    showFillableRules.value = true
    return
  }
  emit('markSelection', {
    paragraph_index: props.currentParagraph,
    start_char: props.selectedStart,
    end_char: props.selectedEnd,
    zone_type: zone
  })
}

function markWholePara(zone: 'fixed' | 'fillable' | 'variable') {
  if (props.currentParagraph === null) return
  if (zone === 'fillable') {
    showFillableRules.value = true
    return
  }
  emit('markSelection', {
    paragraph_index: props.currentParagraph,
    start_char: 0,
    end_char: props.paraText.length,
    zone_type: zone
  })
}

function editClickedAnnotation() {
  if (!props.clickedAnnotation) return
  const ann = props.annotations.find(
    a => a.paragraph_index === props.clickedAnnotation!.paraIndex && a.start_char === props.clickedAnnotation!.startChar
  )
  if (ann?.rules) {
    rules.value = Object.assign(
      { required: true, min_chars: 1, max_chars: 200, allowed_chars: 'any', regex: '', field_name: '', allowed_values: [], match_fields: [], radio_group: '', dependent_paras: [], amount_match_field: '', amount_unit: 1 },
      ann.rules
    )
  } else {
    rules.value = { required: true, min_chars: 1, max_chars: 200, allowed_chars: 'any', regex: '', field_name: '', allowed_values: [], match_fields: [], radio_group: '', dependent_paras: [], amount_match_field: '', amount_unit: 1 }
  }
  editingAnnotation.value = { paraIndex: props.clickedAnnotation.paraIndex, startChar: props.clickedAnnotation.startChar }
  showFillableRules.value = true
}

function cancelCurrentAnnotation() {
  if (!props.clickedAnnotation) return
  emit('cancelAnnotation', props.clickedAnnotation.paraIndex, props.clickedAnnotation.startChar)
}

function confirmFillable() {
  if (editingAnnotation.value) {
    const ann = props.annotations.find(
      a => a.paragraph_index === editingAnnotation.value!.paraIndex && a.start_char === editingAnnotation.value!.startChar
    )
    if (ann) {
      emit('updateAnnotation', { ...ann, rules: { ...rules.value } })
    }
    editingAnnotation.value = null
  } else {
    if (props.currentParagraph === null) return
    if (props.selectedStart === null || props.selectedEnd === null) return
    emit('markSelection', {
      paragraph_index: props.currentParagraph,
      start_char: props.selectedStart,
      end_char: props.selectedEnd,
      zone_type: 'fillable',
      rules: { ...rules.value }
    })
  }
  showFillableRules.value = false
}

function handleAnnItemClick(a: AnnotationItem) {
  emit('selectPara', a.paragraph_index)
  emit('focusAnnotation', a.paragraph_index, a.start_char)
  if (a.zone_type === 'fillable') {
    if (a.rules) {
      rules.value = Object.assign(
        { required: true, min_chars: 1, max_chars: 200, allowed_chars: 'any', regex: '', field_name: '', allowed_values: [], match_fields: [], radio_group: '', dependent_paras: [], amount_match_field: '', amount_unit: 1 },
        a.rules
      )
    } else {
      rules.value = { required: true, min_chars: 1, max_chars: 200, allowed_chars: 'any', regex: '', field_name: '', allowed_values: [], match_fields: [], radio_group: '', dependent_paras: [], amount_match_field: '', amount_unit: 1 }
    }
    editingAnnotation.value = { paraIndex: a.paragraph_index, startChar: a.start_char }
    showFillableRules.value = true
  }
}

function addAllowedValue() {
  const v = allowedValueInput.value.trim()
  if (!v) return
  if (!rules.value.allowed_values.includes(v)) {
    rules.value.allowed_values.push(v)
  }
  allowedValueInput.value = ''
}

function removeAllowedValue(index: number) {
  rules.value.allowed_values.splice(index, 1)
}

function save() { emit('save') }
</script>

<style scoped>
.toolbar {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--paper-warm);
  overflow-y: auto;
}

.tb-head {
  padding: var(--space-4) var(--space-4) var(--space-2);
  flex-shrink: 0;
}
.tb-title {
  font-family: var(--font-display);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--ink);
  margin: 0 0 var(--space-1);
}
.tb-hint {
  color: var(--ink-muted);
  font-size: var(--text-xs);
  margin: 0;
}

/* Info blocks */
.info-block {
  padding: var(--space-3) var(--space-4);
  margin: 0 var(--space-3);
  background: var(--paper-white);
  border: 1px solid var(--rule);
  border-radius: var(--radius-md);
}
.info-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  margin-bottom: var(--space-1);
}
.info-text {
  font-size: var(--text-sm);
  color: var(--ink-soft);
  word-break: break-all;
  margin: 0;
  line-height: 1.6;
}

.actions-area {
  padding: var(--space-3);
}

/* Selection blocks */
.sel-block {
  padding: var(--space-3);
  background: var(--ink-blue-soft);
  border: 1px solid #d4e0ed;
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
}
.sel-block.clicked {
  background: var(--primary-soft);
  border-color: var(--primary-border);
}
.sel-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--ink-blue);
  margin: 0 0 var(--space-1);
}
.clicked .sel-label { color: var(--primary); }
.sel-text {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  margin: 0;
}
.sel-range {
  font-size: var(--text-xs);
  color: var(--ink-muted);
  margin: var(--space-1) 0;
}

.btn-row {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
  flex-wrap: wrap;
}

/* Custom mark buttons */
.mark-btn {
  padding: 5px 12px;
  font-size: var(--text-xs);
  font-weight: 600;
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all .15s;
  background: var(--paper-white);
  color: var(--ink-soft);
}
.mark-btn:hover { background: var(--paper-hover); }
.mark-btn.fixed { border-color: var(--primary); color: var(--primary); }
.mark-btn.fixed:hover { background: var(--primary-soft); }
.mark-btn.fillable { border-color: var(--ink-green); color: var(--ink-green); }
.mark-btn.fillable:hover { background: var(--ink-green-soft); }
.mark-btn.variable { border-color: #d97706; color: #d97706; }
.mark-btn.variable:hover { background: #fef3c7; }
.mark-btn.edit { border-color: var(--ink-blue); color: var(--ink-blue); }
.mark-btn.edit:hover { background: var(--ink-blue-soft); }
.mark-btn.cancel { border-color: var(--ink-muted); color: var(--ink-muted); }
.mark-btn.whole {
  border-style: dashed;
  width: 100%;
  margin-top: var(--space-1);
}

/* Rules box */
.rules-box {
  margin-top: var(--space-3);
  padding: var(--space-3);
  background: var(--paper-white);
  border: 1px solid var(--rule);
  border-radius: var(--radius-md);
}
.rules-title {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  margin: 0 0 var(--space-3);
}

/* Allowed values */
.av-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}
.av-empty {
  font-size: var(--text-xs);
  color: var(--ink-muted);
}
.av-input-row {
  display: flex;
  gap: 6px;
}
.av-input-row .el-button {
  flex-shrink: 0;
}

.tb-divider {
  height: 1px;
  background: var(--rule);
  margin: var(--space-2) var(--space-4);
  flex-shrink: 0;
}

/* Annotation list */
.ann-section {
  padding: 0 var(--space-3);
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.ann-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  margin: 0 0 var(--space-1);
  flex-shrink: 0;
}

.ann-filter {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
  flex-shrink: 0;
}
.ann-fbtn {
  flex: 1;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
  background: var(--paper-white);
  color: var(--ink-muted);
  cursor: pointer;
  transition: all .15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
}
.ann-fbtn:hover { border-color: var(--ink-muted); color: var(--ink); }
.ann-fbtn.active { color: var(--paper-white); border-color: var(--ink); background: var(--ink); }
.fbtn-fillable.active { border-color: var(--ink-green); background: var(--ink-green); }
.fbtn-fixed.active { border-color: var(--primary); background: var(--primary); }
.fbtn-variable.active { border-color: #d97706; background: #d97706; }
.fbtn-num { font-size: 10px; font-weight: 500; opacity: .75; }

.ann-count {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--ink-muted);
  background: var(--paper-hover);
  padding: 1px 7px;
  border-radius: 10px;
}

.ann-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.ann-empty {
  color: var(--ink-muted);
  font-size: var(--text-xs);
  text-align: center;
  padding: var(--space-5) 0;
}

.ann-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-2);
  cursor: pointer;
  border-radius: var(--radius-sm);
  margin-bottom: 2px;
  transition: background .15s;
}
.ann-item:hover { background: var(--paper-white); }

.ann-tag {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}
.ann-tag.fixed { background: var(--primary-soft); color: var(--primary); }
.ann-tag.fillable { background: var(--ink-green-soft); color: var(--ink-green); }
.ann-tag.variable { background: #fef3c7; color: #d97706; }

.ann-loc {
  font-size: var(--text-xs);
  color: var(--ink-soft);
  font-family: var(--font-mono);
}
.ann-field {
  font-size: var(--text-xs);
  color: var(--ink);
  font-weight: 500;
}
.ann-del {
  margin-left: auto;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--ink-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all .15s;
}
.ann-del:hover { color: var(--primary); background: var(--primary-soft); }

.ann-flash {
  animation: annFlash .4s ease 3;
}
@keyframes annFlash {
  50% { background: var(--primary-soft); }
}

/* Save button area */
.toolbar > .el-button {
  margin: var(--space-3) var(--space-4);
  flex-shrink: 0;
}
</style>
