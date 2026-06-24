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

现有同段落兄弟校验保持不动。新增跨段校验仅在 `dependent_paras` 非空时触发：

遍历 `dependent_paras` 中每个段落，找到该段落内所有非 checkbox 填充区的校验结果：

| checkbox 状态 | 填充区有内容 | 填充区为空 |
|---|---|---|
| ☑ 已勾选 | ✅ PASS | ❌ "该条款已勾选，需填写内容" |
| □ 未勾选 | ❌ "该条款未勾选，不应填写内容" | ✅ PASS（覆盖"必填为空"） |

每个 dependent paragraph **独立校验**，互不连坐。

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
