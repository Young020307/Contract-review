<template>
  <div class="diff-container">
    <div class="diff-header">
      <h3>防篡改比对结果</h3>
      <span class="violation-count" v-if="violations.length > 0">
        发现 {{ violations.length }} 处差异
      </span>
      <el-tag v-else type="success">未发现篡改</el-tag>
    </div>
    <div ref="editorContainer" class="diff-editor"></div>
    <div v-if="violations.length > 0" class="violation-list">
      <h4>差异详情</h4>
      <div v-for="(v, i) in violations" :key="i" class="violation-item" @click="goToViolation(i)">
        <el-tag type="danger">篡改</el-tag>
        <span class="v-template">模板: {{ truncate(v.template_text) }}</span>
        <span class="v-actual">实际: {{ truncate(v.actual_text) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as monaco from 'monaco-editor'
import type { CompareResult } from '../types'

const props = defineProps<{ result: CompareResult }>()
const editorContainer = ref<HTMLDivElement | null>(null)
let diffEditor: monaco.editor.IStandaloneDiffEditor | null = null

const violations = ref(props.result?.violations ?? [])

onMounted(() => {
  if (!editorContainer.value) return
  diffEditor = monaco.editor.createDiffEditor(editorContainer.value, {
    readOnly: true,
    automaticLayout: true,
    renderSideBySide: true,
    scrollBeyondLastLine: false,
    minimap: { enabled: false }
  })
  updateModel()
})

watch(() => props.result, () => {
  violations.value = props.result?.violations ?? []
  updateModel()
})

function updateModel() {
  if (!diffEditor) return
  const original = monaco.editor.createModel(props.result.template_text, 'text/plain')
  const modified = monaco.editor.createModel(props.result.document_text, 'text/plain')
  diffEditor.setModel({ original, modified })
}

function truncate(text: string): string {
  return text.length > 30 ? text.slice(0, 30) + '...' : text
}

function goToViolation(index: number) {
  if (!diffEditor) return
  const diff = props.result.diffs[index]
  if (diff) {
    diffEditor.setSelection({
      startLineNumber: 1,
      startColumn: diff.doc_range[0] + 1,
      endLineNumber: 1,
      endColumn: diff.doc_range[1] + 1
    })
  }
}
</script>

<style scoped>
.diff-container { height: 100%; display: flex; flex-direction: column; }
.diff-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.diff-editor { flex: 1; min-height: 400px; border: 1px solid #e4e7ed; }
.violation-count { color: #f56c6c; font-weight: bold; }
.violation-list { margin-top: 16px; }
.violation-item { padding: 8px; border: 1px solid #fde2e2; border-radius: 4px; margin-bottom: 4px; cursor: pointer; display: flex; gap: 12px; align-items: center; }
.violation-item:hover { background: #fef0f0; }
</style>
