<template>
  <div class="tpl-page">
    <div class="page-head">
      <div class="head-left">
        <h2 class="page-title">模板管理</h2>
        <span class="page-subtitle">上传并标注合同模板，用于后续智能审查</span>
      </div>
      <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".docx">
        <el-button type="primary" size="large" class="upload-btn">
          <el-icon><UploadFilled /></el-icon>
          上传模板
        </el-button>
      </el-upload>
    </div>

    <div class="table-card">
      <el-table :data="templates" stripe highlight-current-row>
        <el-table-column type="index" label="序号" width="64" />
        <el-table-column prop="name" label="模板名称" align="center" />
        <el-table-column prop="paragraph_count" label="段落数" width="88" align="center" />
        <el-table-column prop="created_at" label="上传时间" width="176" align="center" />
        <el-table-column label="状态" width="96" align="center">
          <template #default="{ row }">
            <el-tag :type="row.annotated ? 'success' : 'warning'" size="small">
              {{ row.annotated ? '已标注' : '未标注' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="196" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/annotate/${row.id}`)">
              <el-icon><Edit /></el-icon>
              标注
            </el-button>
            <el-popconfirm
              title="确定删除该模板？相关标注和文档也将被删除"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="handleDelete(row.id)"
            >
              <template #reference>
                <el-button type="danger" size="small" plain>
                  <el-icon><Delete /></el-icon>
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Edit, Delete } from '@element-plus/icons-vue'
import { listTemplates, uploadTemplate, getAnnotations, deleteTemplate } from '../api'
import type { TemplateInfo } from '../types'

interface TemplateRow extends TemplateInfo { annotated: boolean }
const templates = ref<TemplateRow[]>([])

onMounted(async () => { await loadTemplates() })

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

async function handleDelete(id: number) {
  await deleteTemplate(id)
  ElMessage.success('模板已删除')
  await loadTemplates()
}

async function handleUpload(file: File) {
  await uploadTemplate(file)
  ElMessage.success('模板上传成功')
  await loadTemplates()
  return false
}
</script>

<style scoped>
.tpl-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: var(--space-6) var(--space-8);
  max-width: 1100px;
  margin: 0 auto;
  overflow: hidden;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: var(--space-5);
}
.head-left {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.page-title {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 700;
  color: var(--ink);
  letter-spacing: .02em;
}
.page-subtitle {
  font-size: var(--text-base);
  color: var(--ink-muted);
}

.table-card {
  flex: 1;
  min-height: 0;
  background: var(--paper-white);
  border: 1px solid var(--rule);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-md);
  transition: box-shadow var(--transition-base);
  display: flex;
  flex-direction: column;
}
.table-card:hover {
  box-shadow: var(--shadow-lg);
}

.table-card :deep(.el-table) { border: none; font-size: 15px; height: 100%; }
.table-card :deep(.el-table__inner-wrapper) { height: 100%; }
.table-card :deep(.el-table td) { padding: 16px 0; }
.table-card :deep(.el-table th) { padding: 16px 0; font-size: 15px; }
.table-card :deep(.el-table::before) { display: none; }
.table-card :deep(.el-table__inner-wrapper::before) { display: none; }
.table-card :deep(.el-tag) { font-size: 13px; }
.table-card :deep(.el-button--small) { border-radius: var(--radius-sm); font-size: 14px; }
.upload-btn { --el-button-bg-color: var(--primary); --el-button-border-color: var(--primary); font-size: 16px; }
.upload-btn:hover { --el-button-bg-color: #1d4ed8; --el-button-border-color: #1d4ed8; }
</style>
