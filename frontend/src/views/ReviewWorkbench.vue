<template>
  <div class="review-page">
    <!-- Step 1: Upload and select -->
    <el-card v-if="!showResult">
      <template #header><span>审查工作台</span></template>
      <el-form label-width="100px">
        <el-form-item label="选择模板">
          <el-select v-model="selectedTemplateId" placeholder="请选择模板">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="上传业务文件">
          <el-upload :show-file-list="false" :before-upload="handleDocUpload" accept=".docx">
            <el-button type="primary" :disabled="!selectedTemplateId">上传 docx</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="uploadedDoc" label="已上传文件">
          <el-tag>{{ uploadedDoc.name }}</el-tag>
        </el-form-item>
        <el-form-item label="审查流程">
          <el-radio-group v-model="reviewMode" :disabled="!uploadedDoc">
            <el-radio value="compare">防篡改比对</el-radio>
            <el-radio value="validate">数据校验</el-radio>
            <el-radio value="both">全部执行</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="startReview" :disabled="!uploadedDoc" :loading="reviewing">
            开始审查
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Step 2: Results -->
    <div v-if="showResult">
      <el-tabs v-model="activeTab">
        <el-tab-pane v-if="compareResult" label="防篡改比对" name="compare">
          <CompareDiffView :result="compareResult" />
        </el-tab-pane>
        <el-tab-pane v-if="validateResult" label="数据校验" name="validate">
          <ValidationView :result="validateResult" />
        </el-tab-pane>
      </el-tabs>
      <el-button type="default" @click="resetReview" style="margin-top: 16px">返回</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listTemplates, uploadDocument, reviewCompare, reviewValidate } from '../api'
import type { TemplateInfo, DocumentInfo, CompareResult, ValidateResult } from '../types'
import CompareDiffView from '../components/CompareDiffView.vue'
import ValidationView from '../components/ValidationView.vue'

const templates = ref<TemplateInfo[]>([])
const selectedTemplateId = ref<number | null>(null)
const uploadedDoc = ref<DocumentInfo | null>(null)
const reviewMode = ref<'compare' | 'validate' | 'both'>('compare')
const reviewing = ref(false)
const showResult = ref(false)
const activeTab = ref('compare')

const compareResult = ref<CompareResult | null>(null)
const validateResult = ref<ValidateResult | null>(null)

onMounted(async () => {
  templates.value = await listTemplates()
})

async function handleDocUpload(file: File) {
  if (!selectedTemplateId.value) return false
  uploadedDoc.value = await uploadDocument(file, selectedTemplateId.value)
  ElMessage.success('文件上传成功')
  return false
}

async function startReview() {
  if (!selectedTemplateId.value || !uploadedDoc.value) return
  reviewing.value = true
  const tid = selectedTemplateId.value
  const did = uploadedDoc.value.id

  if (reviewMode.value === 'compare' || reviewMode.value === 'both') {
    compareResult.value = await reviewCompare(tid, did)
  }
  if (reviewMode.value === 'validate' || reviewMode.value === 'both') {
    validateResult.value = await reviewValidate(tid, did)
  }

  activeTab.value = reviewMode.value === 'validate' ? 'validate' : 'compare'
  showResult.value = true
  reviewing.value = false
}

function resetReview() {
  showResult.value = false
  uploadedDoc.value = null
  compareResult.value = null
  validateResult.value = null
}
</script>
