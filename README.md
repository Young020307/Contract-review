# 合同智能审查系统

基于文档批注与规则引擎的合同审查工具，支持模板标注、篡改比对、数据校验三类审查模式。

## 核心功能

- **模板标注** — 上传标准合同模板，标记固定区（不可篡改）与填充区（待填写字段），为填充区配置校验规则（必填、字符类型、长度限制、正则、枚举值、跨字段一致性）
- **篡改比对** — 对已填写的业务文档与模板进行字符级 diff，检测固定条款的增删改，填充区变更自动排除
- **数据校验** — 基于正则上下文锚点提取填充区实际值，逐字段校验合规性，支持变量长度内容
- **多文档审查** — 支持拖拽上传多个业务文档，审查结果按文档标签页切换查看

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | Python / FastAPI |
| 文档解析 | python-docx |
| 差异比对 | difflib.SequenceMatcher（字符级） |
| 数据存储 | SQLite |
| 前端框架 | Vue 3 + TypeScript + Vite |
| UI 组件库 | Element Plus |
| 文档渲染 | mammoth.js（DOCX → HTML） |
| 设计主题 | 朱墨批阅（vermilion ink） |

## 快速开始

### 环境要求

- Python 3.10+（推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖）
- Node.js 18+

### 安装与运行

```bash
# 克隆仓库
git clone <repo-url> && cd <repo>

# 终端 1 — 启动后端（端口 8000）
cd backend && uv run uvicorn main:app --port 8000

# 终端 2 — 启动前端（端口 5173）
cd frontend && npm install && npm run dev
```

浏览器访问 `http://localhost:5173`。

## 使用流程

### 1. 上传模板

在「模板管理」页面上传标准合同 .docx 文件（如咨询服务标准合同模板）。

### 2. 标注区域与规则

进入「标注」工作台，为模板文本标记两类区域：

- **固定区** — 合同条款正文，不得修改
- **填充区** — 需要对方填写的字段，可配置校验规则：
  - 必填、字符数上下限
  - 字符类型：中文 / 数字 / 中英文数字 / 自定义正则
  - 允许值列表（枚举）
  - 跨字段一致性（如"甲方名称"与"乙方名称"不得相同）

系统会自动检测下划线文本为候选填充区。

### 3. 执行业务文档审查

在「审查工作台」选择模板后，拖拽上传一个或多个 .docx 业务文档，选择审查模式：

| 模式 | 功能 |
|---|---|
| 篡改比对 | 检测固定条款是否被增删改 |
| 数据校验 | 提取填充区数值并逐字段校验合规性 |
| 全部执行 | 同时执行比对与校验 |

审查结果以三栏布局展示：模板原文 | 实际文档（内联高亮）| 违规列表。填充区合规高亮为绿色，违规高亮为琥珀色，篡改差异高亮为红色。点击结果卡片可定位到文档对应位置。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/templates/upload` | 上传合同模板 |
| `GET` | `/api/templates` | 列出所有模板 |
| `GET` | `/api/templates/:id` | 获取模板段落详情 |
| `POST` | `/api/templates/:id/annotations` | 保存标注数据 |
| `GET` | `/api/templates/:id/annotations` | 获取标注数据 |
| `POST` | `/api/documents/upload` | 上传业务文档 |
| `GET` | `/api/documents/:id` | 获取文档段落详情 |
| `POST` | `/api/review/compare` | 执行篡改比对 |
| `POST` | `/api/review/validate` | 执行数据校验 |

## 项目结构

```
├── backend/
│   ├── main.py              # FastAPI 应用入口，API 路由
│   ├── models.py             # Pydantic 请求/响应模型
│   ├── database.py           # SQLite 数据库初始化与迁移
│   ├── services/
│   │   ├── parser.py         # DOCX 解析、固定文本提取、填充值提取
│   │   ├── diff_engine.py    # 字符级差异比对引擎
│   │   └── validator.py      # 填充值规则校验引擎
│   └── test_regex_extraction.py  # 填充值提取单元测试
├── frontend/
│   ├── src/
│   │   ├── main.ts           # Vue 应用入口
│   │   ├── App.vue           # 根组件（导航栏 + 路由出口）
│   │   ├── api/index.ts      # Axios API 客户端
│   │   ├── types/index.ts    # TypeScript 类型定义
│   │   ├── router/index.ts   # Vue Router 路由配置
│   │   ├── assets/tokens.css # 设计令牌（朱墨批阅主题）
│   │   ├── views/
│   │   │   ├── TemplateList.vue        # 模板管理页
│   │   │   ├── AnnotationWorkbench.vue # 标注工作台
│   │   │   └── ReviewWorkbench.vue     # 审查工作台
│   │   └── components/
│   │       ├── DocxPreview.vue         # DOCX 渲染预览面板
│   │       ├── AnnotationToolbar.vue   # 标注工具栏
│   │       ├── CompareDiffView.vue     # 差异比对视图
│   │       └── ValidationView.vue      # 数据校验视图
│   ├── package.json
│   └── vite.config.ts
└── docs/
    └── 使用说明.md
```
