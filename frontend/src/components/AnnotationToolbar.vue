<template>
  <div class="toolbar">
    <h3>标注工具</h3>
    <p class="hint">点击段落选中，然后选择区域类型</p>

    <div class="zone-actions">
      <el-button :type="selectedZone === 'fixed' ? 'danger' : 'default'" @click="markAs('fixed')">
        标记为固定区
      </el-button>
      <el-button :type="selectedZone === 'fillable' ? 'success' : 'default'" @click="markAs('fillable')">
        标记为填充区
      </el-button>
    </div>

    <div v-if="currentParagraph !== null" class="para-info">
      <p><strong>当前段落:</strong> {{ currentParagraph }}</p>
      <p class="text-preview">{{ paraText }}</p>
    </div>

    <!-- Fillable rules config -->
    <div v-if="selectedZone === 'fillable' && currentParagraph !== null" class="rules-config">
      <h4>校验规则</h4>
      <el-form label-width="80px" size="small">
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
            <el-option label="字母+数字+中文" value="alphanumeric" />
            <el-option label="正则表达式" value="regex" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="rules.allowed_chars === 'regex'" label="正则">
          <el-input v-model="rules.regex" placeholder="如: ^1[3-9]\d{9}$" />
        </el-form-item>
        <el-button type="primary" @click="applyRule">确认规则</el-button>
      </el-form>
    </div>

    <el-divider />
    <h4>标注列表</h4>
    <div v-if="annotations.length === 0" class="empty">暂无标注</div>
    <div v-for="a in annotations" :key="a.paragraph_index" class="ann-item" @click="$emit('selectPara', a.paragraph_index)">
      <el-tag :type="a.zone_type === 'fixed' ? 'danger' : 'success'" size="small">
        {{ a.zone_type === 'fixed' ? '固定' : '填充' }}
      </el-tag>
      <span>段落 {{ a.paragraph_index }}</span>
      <span v-if="a.rules?.field_name">- {{ a.rules.field_name }}</span>
    </div>

    <el-divider />
    <el-button type="primary" @click="save" :loading="saving">保存标注</el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { AnnotationItem, ValidationRule } from '../types'

const props = defineProps<{
  currentParagraph: number | null
  paraText: string
  annotations: AnnotationItem[]
  saving: boolean
}>()

const emit = defineEmits<{
  markAs: [zone: 'fixed' | 'fillable']
  applyRule: [rule: ValidationRule, paraIndex: number]
  save: []
  selectPara: [index: number]
}>()

const selectedZone = ref<'fixed' | 'fillable' | null>(null)

const rules = ref<ValidationRule>({
  required: true, min_chars: 1, max_chars: 200,
  allowed_chars: 'any', regex: '', field_name: ''
})

function markAs(zone: 'fixed' | 'fillable') {
  selectedZone.value = zone
  emit('markAs', zone)
}

function applyRule() {
  if (props.currentParagraph === null) return
  emit('applyRule', { ...rules.value }, props.currentParagraph)
}

function save() {
  emit('save')
}
</script>

<style scoped>
.toolbar { padding: 16px; background: #fff; border: 1px solid #e4e7ed; border-radius: 4px; height: 100%; overflow-y: auto; }
.toolbar h3 { margin: 0 0 8px 0; font-size: 16px; }
.hint { color: #909399; font-size: 12px; margin: 0 0 12px 0; }
.zone-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.para-info { background: #f5f7fa; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px; }
.para-info p { margin: 4px 0; }
.text-preview { color: #606266; font-size: 13px; word-break: break-all; }
.rules-config { margin-bottom: 12px; }
.rules-config h4 { margin: 0 0 8px 0; font-size: 14px; }
.empty { color: #c0c4cc; font-size: 13px; text-align: center; padding: 12px 0; }
.ann-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; cursor: pointer; border-radius: 4px; margin-bottom: 4px; }
.ann-item:hover { background: #f5f7fa; }
.ann-item span { font-size: 13px; color: #303133; }
</style>
