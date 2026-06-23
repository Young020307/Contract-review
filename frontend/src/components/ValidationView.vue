<template>
  <div class="validation-container">
    <div class="val-header">
      <h3>数据校验结果</h3>
      <span>
        通过 {{ passCount }} / 共 {{ result.results.length }} 项
      </span>
    </div>
    <div class="dual-pane">
      <div class="pane left-pane">
        <h4>模板规则</h4>
        <div v-for="r in result.results" :key="r.paragraph" class="rule-row">
          <div class="field-label">{{ r.field_name }} <el-tag size="small">段落{{ r.paragraph }}</el-tag></div>
          <div class="field-rule">{{ r.rule }}</div>
        </div>
      </div>
      <div class="pane right-pane">
        <h4>实际填写</h4>
        <div v-for="r in result.results" :key="r.paragraph" class="value-row" :class="{ fail: !r.pass }">
          <div class="field-value">{{ r.actual_value || '(空)' }}</div>
          <div v-if="!r.pass" class="fail-reason">
            <el-icon><WarningFilled /></el-icon>
            {{ r.reason }}
          </div>
          <div v-else class="pass-indicator">
            <el-icon color="#67c23a"><CircleCheckFilled /></el-icon>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ValidateResult } from '../types'

const props = defineProps<{ result: ValidateResult }>()

const passCount = computed(() => props.result.results.filter(r => r.pass).length)
</script>

<style scoped>
.validation-container { height: 100%; }
.val-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.dual-pane { display: flex; gap: 16px; }
.pane { flex: 1; border: 1px solid #e4e7ed; border-radius: 4px; padding: 16px; background: #fff; }
.pane h4 { margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #e4e7ed; }
.rule-row { padding: 8px 0; border-bottom: 1px dashed #e4e7ed; }
.value-row { padding: 8px 0; border-bottom: 1px dashed #e4e7ed; display: flex; align-items: center; justify-content: space-between; }
.value-row.fail { background: #fef0f0; }
.fail-reason { color: #f56c6c; font-size: 13px; }
.pass-indicator { color: #67c23a; }
</style>
