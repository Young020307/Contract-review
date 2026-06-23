# 格式合同智能审查系统 Demo — 设计文档

## 1. 范围

搭建一个 Web Demo，核心能力：

- 上传模板 docx → 可视化标注固定区/填充区 → 保存标注（一次性配置）
- 上传业务 docx → 选择审查流程
- **防篡改比对**：固定区文本一致性检查，字符级双栏 diff
- **数据校验**：填充区内容有效性检查（字数、字符类型、必填），双栏对比展示

当前模板：`咨询服务标准合同-调整板V4.docx`，后续扩展到 7 个。

## 2. 架构

```
前端 (Vue3 + Vite + TypeScript)
  ├─ 模板管理页
  ├─ 标注工作台 (Mammoth + Fabric.js)
  └─ 审查工作台 (Monaco Editor 双栏对比)
         │ REST API
后端 (FastAPI + Python)
  ├─ 文档解析 (python-docx)
  ├─ 差异比对 (difflib / diff-match-patch)
  ├─ 数据校验 (Pydantic 自定义校验器)
  └─ 标注管理
         │
SQLite (templates / annotations / documents / review_tasks)
```

层级单向依赖，前端只调 API，后端封装业务逻辑。

## 3. 核心流程

```
上传模板docx → 后端解析段落 → 前端渲染预览 → Fabric.js 可视化标注
                                                       ↓
                             标注数据(固定区/填充区+校验规则) 存入 SQLite
                                                       ↓
                    上传业务文件docx → 选择审查流程
                           ↙                    ↘
              防篡改比对                      数据校验
         (固定区文本一致性diff)         (填充区字数/字符/格式校验)
                    ↓                           ↓
         Monaco Editor 双栏              双栏对比 + 违规列表
         字符级差异高亮                   违规字段红色高亮
```

模板标注为一次性操作，标注保存后，同一模板可对多份业务文件重复使用。

## 4. 页面设计

### 4.1 模板管理页

- 上传模板 docx，列表展示已标注/未标注的模板
- 点击模板进入标注页面

### 4.2 标注工作台

- 左侧：Mammoth 渲染的 docx 文档预览
- 右侧：标注工具栏
  - 点选段落 → 标记为「固定区」或「填充区」
  - 填充区额外配置校验规则：必填/可选、字数上下限、允许字符类型、正则表达式、字段名称
- 标注保存到后端

### 4.3 审查工作台

- 上传业务 docx
- 选择审查流程（防篡改比对 / 数据校验）
- 两种结果都用双栏对比展示：
  - 防篡改：左模板原文(固定区)，右业务文件全文，字符级增/删/改高亮，差异导航跳转
  - 数据校验：左模板(填充区预期规则)，右业务文件(实际内容)，违规字段红色高亮 + 规则说明

## 5. API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/templates/upload` | 上传模板 docx |
| GET | `/api/templates` | 模板列表 |
| GET | `/api/templates/{id}` | 模板详情（含段落列表） |
| POST | `/api/templates/{id}/annotations` | 保存标注数据 |
| GET | `/api/templates/{id}/annotations` | 获取标注数据 |
| POST | `/api/documents/upload` | 上传业务 docx |
| GET | `/api/documents/{id}` | 业务文件段落列表 |
| POST | `/api/review/compare` | 防篡改比对 |
| POST | `/api/review/validate` | 数据校验 |
| GET | `/api/review/{task_id}` | 查询审查结果 |

### 5.1 防篡改比对返回结构

```json
{
  "template_text": "模板固定区拼接文本",
  "document_text": "业务文件对应文本",
  "diffs": [
    {"type": "equal|insert|delete|replace", "template_range": [0,10], "doc_range": [0,12], "value": "..."}
  ],
  "violations": [
    {"paragraph": 3, "type": "tamper", "template_text": "...", "actual_text": "..."}
  ]
}
```

### 5.2 数据校验返回结构

```json
{
  "results": [
    {
      "paragraph": 5,
      "field_name": "公司名称",
      "actual_value": "某某有限公司",
      "rule": "必填+中文+2-50字",
      "pass": true
    }
  ]
}
```

## 6. 数据设计

### 6.1 templates

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 模板ID |
| name | TEXT | 模板名称 |
| file_path | TEXT | 文件存储路径 |
| paragraph_count | INTEGER | 段落总数 |
| created_at | TEXT | 上传时间 |

### 6.2 annotations

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 标注ID |
| template_id | INTEGER FK | 关联模板 |
| paragraph_index | INTEGER | 段落序号（从0开始） |
| zone_type | TEXT | "fixed" 或 "fillable" |
| rules | TEXT(JSON) | 校验规则（仅填充区有值） |

rules JSON 结构：
```json
{
  "required": true,
  "max_chars": 50,
  "min_chars": 2,
  "allowed_chars": "chinese",
  "regex": "",
  "field_name": "公司名称"
}
```

### 6.3 documents

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 文件ID |
| template_id | INTEGER FK | 关联模板 |
| name | TEXT | 文件名 |
| file_path | TEXT | 存储路径 |
| uploaded_at | TEXT | 上传时间 |

### 6.4 review_tasks

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 任务ID |
| template_id | INTEGER FK | 模板 |
| document_id | INTEGER FK | 业务文件 |
| task_type | TEXT | "compare" / "validate" / "both" |
| result | TEXT(JSON) | 审查结果 |
| created_at | TEXT | 执行时间 |

## 7. 技术栈

| 层 | 技术 |
|----|------|
| 前端框架 | Vue3 + Vite + TypeScript |
| 文档预览 | Mammoth (docx → HTML) |
| 可视化标注 | Fabric.js |
| 差异对比 | Monaco Editor |
| UI 组件 | Element Plus |
| 后端框架 | FastAPI |
| 文档解析 | python-docx |
| 差异计算 | difflib / diff-match-patch |
| 数据校验 | Pydantic |
| 数据库 | SQLite |
