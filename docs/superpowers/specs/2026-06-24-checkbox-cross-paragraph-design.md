# Checkbox 跨段落从属校验

**日期**: 2026-06-24
**分支**: feat/regex-extraction-and-multi-upload

## 问题

`☑ 按次计费`（para 24）勾选后，其从属的填充区在 para 25-26（纯下划线段落），与 checkbox 不在同一段落。现有同段落兄弟校验无法覆盖此场景。

## 设计

### 数据模型

`ValidationRule` 新增字段：

```python
dependent_paras: list[int] = []
```

用户在标注时为 checkbox 手动指定其管辖的段落号列表。同段落兄弟依赖保持自动生效，不依赖此字段。

### 校验逻辑

**同段落兄弟**（现有逻辑不变）：checkbox 所在段落内的填充区，勾选则必填。

**跨段从属**（`dependent_paras` 非空时触发）：

遍历 `dependent_paras` 中每个段落，找到该段落内所有非 checkbox 填充区的校验结果：

| checkbox 状态 | 同段落兄弟 | dependent_paras（跨段） |
|---|---|---|
| ☑ 已勾选 | ❌ 必填，空则报错 | ✅ 可选，填不填都 PASS |
| □ 未勾选 | ❌ 有内容报错 | ❌ 有内容报错 |

跨段设计为可选：按次计费的服务项目描述行（para 25-26）填几个算几个，不强制全填。

### 前端标注

AnnotationToolbar 规则表单中"单选组名"下方新增：

- **管辖段落** 多选下拉框，列出模板所有段落号
- 默认空，用户手动勾选

### 实现范围

| 文件 | 改动 |
|---|---|
| `backend/models.py` | `dependent_paras: list[int] = []` |
| `backend/main.py` | `review_validate` 中新增跨段校验 pass |
| `backend/services/validator.py` | `_describe_rule` 显示管辖段落 |
| `backend/generate_rules.py` | classify 返回 `dependent_paras` 默认值 |
| `frontend/src/types/index.ts` | 同步 `dependent_paras: number[]` |
| `frontend/src/components/AnnotationToolbar.vue` | 管辖段落下拉选择器 |

### 不变

- `radio_group` 互斥逻辑不动
- 同段落兄弟自动依赖不动
- `detect_checkbox_status` 不动
