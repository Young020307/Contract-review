# Checkbox 跨段落从属校验 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许 checkbox 标注手动指定额外的从属段落号，勾选时这些段落的填充区可选填，未勾选时这些段落不能有内容。

**Architecture:** `ValidationRule` 新增 `dependent_paras: list[int]`，前端新增段落多选器，后端在现有兄弟校验后追加跨段校验 pass。同段兄弟逻辑不变。

**Tech Stack:** Python/FastAPI, Vue 3/TypeScript/Element Plus

## Global Constraints

- 同段落兄弟依赖保持自动生效，不计入 `dependent_paras`
- `dependent_paras` 中的段落在 ☑ 勾选时内容可选、□ 未勾选时不得有内容
- 每个 dependent paragraph 独立校验，互不连坐
- `dependent_paras` 默认空列表

---

### Task 1: 数据模型更新

**Files:**
- Modify: `backend/models.py`
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Produces: `ValidationRule.dependent_paras: list[int]` (Python), `dependent_paras: number[]` (TS)

- [ ] **Step 1: Python model**

```python
# backend/models.py — 在 ValidationRule 的 match_field 之后添加
    match_field: str = ""
    radio_group: str = ""
    dependent_paras: list[int] = []
```

- [ ] **Step 2: TypeScript type**

```typescript
// frontend/src/types/index.ts — 在 ValidationRule 的 radio_group 之后添加
  radio_group: string
  dependent_paras: number[]
```

- [ ] **Step 3: Commit**

```bash
git add backend/models.py frontend/src/types/index.ts
git commit -m "feat: add dependent_paras field to ValidationRule model"
```

---

### Task 2: 跨段校验逻辑

**Files:**
- Modify: `backend/main.py` — `review_validate` endpoint

**Interfaces:**
- Consumes: `ValidationRule.dependent_paras` from Task 1, existing `checkbox_checked` dict, `values` dict, `result["results"]`

- [ ] **Step 1: Add cross-paragraph check after existing sibling check**

在 `main.py` 的 `result["results"].sort(key=lambda r: r["pass"])` 之前，插入跨段校验。该 pass 遍历所有带 `dependent_paras` 的 checkbox 标注，检查每个从属段落内填充区的内容状态。

```python
# 放在 checkbox_checked 构建之后、result.sort 之前

# Cross-paragraph dependent check: dependent_paras fillable zones
# are optional when checked, must be empty when unchecked.
for a in ann_list:
    if a.get("zone_type") != "fillable":
        continue
    rules = _parse_annotation_rules(a.get("rules", "{}"))
    rg = rules.get("radio_group", "")
    deps = rules.get("dependent_paras", [])
    if not rg or not deps:
        continue
    pi = a["paragraph_index"]
    key = f"{pi}_{a.get('start_char', 0)}"
    is_checked = values.get(key, {}).get("checked", False)

    for dep_pi in deps:
        for r in result["results"]:
            if r["paragraph"] != dep_pi:
                continue
            # Find annotation for this result to check it's not a checkbox
            dep_ann = None
            for da in ann_list:
                if (da.get("zone_type") == "fillable"
                        and da["paragraph_index"] == dep_pi
                        and da.get("start_char", 0) == r.get("start_char", 0)):
                    dep_ann = da
                    break
            if not dep_ann:
                continue
            dep_rules = _parse_annotation_rules(dep_ann.get("rules", "{}"))
            if dep_rules.get("radio_group"):
                continue  # skip checkboxes in dependent paragraphs
            dep_key = f"{dep_pi}_{dep_ann.get('start_char', 0)}"
            v = values.get(dep_key, {})
            actual = v.get("value", "") if isinstance(v, dict) else (v or "")
            has_content = bool(str(actual).strip("_ "))

            if not is_checked:
                if has_content:
                    r["pass"] = False
                    r["reason"] = "该条款未勾选，不应填写内容"
                else:
                    r["pass"] = True
                    r["reason"] = ""
            # when is_checked: PASS either way (optional)
```

- [ ] **Step 2: Verify sort still happens**

确认 `result["results"].sort(key=lambda r: r["pass"])` 在新代码之后执行。当前该行在第 431 行，新代码插入在第 430 行之前。

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest test_regex_extraction.py -v
```

Expected: 8 passed

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: add cross-paragraph dependent_paras validation"
```

---

### Task 3: 规则描述更新

**Files:**
- Modify: `backend/services/validator.py` — `_describe_rule` method

**Interfaces:**
- Consumes: `dependent_paras` in rules dict

- [ ] **Step 1: Update _describe_rule**

```python
# In _describe_rule, after the radio_group block:
        if rules.get("radio_group"):
            desc = f"单选组:{rules['radio_group']}"
            deps = rules.get("dependent_paras", [])
            if deps:
                desc += f" 管辖段落:{','.join(str(p) for p in deps)}"
            return desc
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/validator.py
git commit -m "feat: show dependent_paras in rule description"
```

---

### Task 4: 自动规则生成更新

**Files:**
- Modify: `backend/generate_rules.py` — `classify` function, initial R dict

**Interfaces:**
- Produces: `dependent_paras` in returned rules dict

- [ ] **Step 1: Add default to R template**

```python
# In classify(), R dict:
    R = {
        ...
        "radio_group": "",
        "dependent_paras": []
    }
```

Note: `classify` 不自动推断 `dependent_paras`，保持默认空列表。跨段从属关系由用户手动指定。

- [ ] **Step 2: Commit**

```bash
git add backend/generate_rules.py
git commit -m "chore: add dependent_paras default to generate_rules"
```

---

### Task 5: 前端管辖区段选择器

**Files:**
- Modify: `frontend/src/components/AnnotationToolbar.vue` — template + script
- Modify: `frontend/src/views/AnnotationWorkbench.vue` — pass para indices prop

**Interfaces:**
- Consumes: `paraIndices: number[]` prop (passed from AnnotationWorkbench)
- Produces: `rules.dependent_paras` emitted via updateAnnotation/markSelection

- [ ] **Step 1: Add prop to AnnotationToolbar**

```typescript
// In defineProps, add:
  paraIndices: number[]
```

- [ ] **Step 2: Add to defaults**

```typescript
// Update rules ref default:
  allowed_values: [], match_field: '',
  radio_group: '', dependent_paras: []
```

Update all 6 Object.assign defaults from:
```
, radio_group: ''
```
to:
```
, radio_group: '', dependent_paras: []
```

- [ ] **Step 3: Add UI control in template**

在"单选组名" `</el-form-item>` 之后、"`<div class="btn-row">`" 之前：

```html
          <el-form-item label="管辖段落">
            <el-select v-model="rules.dependent_paras" multiple clearable
              placeholder="选择从属段落号" size="small" style="width:100%">
              <el-option v-for="idx in paraIndices" :key="idx"
                :label="'段落 ' + idx" :value="idx" />
            </el-select>
          </el-form-item>
```

- [ ] **Step 4: Pass paraIndices from AnnotationWorkbench**

```html
<!-- In AnnotationWorkbench.vue template, add prop to AnnotationToolbar -->
      <AnnotationToolbar
        ...
        :para-indices="docxIndices"
      />
```

- [ ] **Step 5: Type check**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: no new errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AnnotationToolbar.vue frontend/src/views/AnnotationWorkbench.vue
git commit -m "feat: add dependent_paras paragraph selector to annotation toolbar"
```

---

### Task 6: 集成测试

**Files:**
- None (manual verification)

- [ ] **Step 1: Run backend tests**

```bash
cd backend && uv run pytest test_regex_extraction.py -v
```

Expected: 8 passed

- [ ] **Step 2: Manual smoke test**

```bash
cd backend && uv run python -c "
from services.parser import DocxParser
from services.validator import RuleValidator
from services.validator import _parse_rules
from glob import glob
import json

template_path = glob('uploads/*技术服务标准*.docx')[0]

annotations = [
    {'paragraph_index': 24, 'start_char': 0, 'end_char': 1, 'zone_type': 'fillable',
     'rules': json.dumps({'radio_group': '计价方式', 'field_name': '按次计费', 'dependent_paras': [25, 26]})},
    {'paragraph_index': 25, 'start_char': 0, 'end_char': 38, 'zone_type': 'fillable',
     'rules': json.dumps({'required': True, 'field_name': '服务项目1'})},
    {'paragraph_index': 26, 'start_char': 0, 'end_char': 38, 'zone_type': 'fillable',
     'rules': json.dumps({'required': True, 'field_name': '服务项目2'})},
]

# Simulate 按次计费 checked, para 25 filled, para 26 empty
values = {'24_0': {'checked': True, 'value': '☑'},
          '25_0': {'value': 'SEO优化服务'},
          '26_0': {'value': '______'}}

result = RuleValidator.validate(values, annotations)
# Apply cross-paragraph check manually (same as main.py)
# ... (manual verification)

for r in result['results']:
    print(f'{r[\"field_name\"]}: pass={r[\"pass\"]} reason={r[\"reason\"]!r}')
# Expected: para 25 PASS, para 26 PASS (optional when checked)
"
```

Expected: para 25 PASS, para 26 PASS (可选)

- [ ] **Step 3: Commit final adjustments if needed**

```bash
git add -A && git commit -m "test: verify cross-paragraph dependent_paras validation"
```
