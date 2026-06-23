<template>
  <div class="template-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>模板管理</span>
          <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".docx">
            <el-button type="primary">上传模板</el-button>
          </el-upload>
        </div>
      </template>
      <el-table :data="templates" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="模板名称" />
        <el-table-column prop="paragraph_count" label="段落数" width="100" />
        <el-table-column prop="created_at" label="上传时间" width="180" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.annotated ? 'success' : 'warning'">
              {{ row.annotated ? '已标注' : '未标注' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="$router.push(`/annotate/${row.id}`)">
              标注
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listTemplates, uploadTemplate, getAnnotations } from '../api'
import type { TemplateInfo } from '../types'

interface TemplateRow extends TemplateInfo { annotated: boolean }
const templates = ref<TemplateRow[]>([])

onMounted(async () => {
  await loadTemplates()
})

async function loadTemplates() {
  const list = await listTemplates()
  const enriched: TemplateRow[] = []
  for (const t of list) {
    try {
      const anns = await getAnnotations(t.id)
      enriched.push({ ...t, annotated: anns.length > 0 })
    } catch {
      enriched.push({ ...t, annotated: false })
    }
  }
  templates.value = enriched
}

async function handleUpload(file: File) {
  await uploadTemplate(file)
  ElMessage.success('模板上传成功')
  await loadTemplates()
  return false
}
</script>

<style scoped>
.card-header { display: flex; align-items: center; justify-content: space-between; }
</style>
