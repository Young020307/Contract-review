# Paragraph Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert paragraph-level alignment between template and document so that paragraph insertions/deletions don't break value extraction, validation, or highlighting.

**Architecture:** New `align_paragraphs()` function in parser.py uses `difflib.SequenceMatcher` with skeleton texts (fillable zones removed) to produce a template→document paragraph mapping. Three downstream consumers (`extract_fillable_values`, `detect_checkbox_status`, frontend renderedParagraphs) consume this mapping instead of direct index access.

**Tech Stack:** Python (difflib), FastAPI, Vue 3 + TypeScript

## Global Constraints

- Annotation storage model unchanged — annotations always keyed by template paragraph index
- Character-level diff engine unchanged
- 0.5 similarity threshold for paragraph matching decisions

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/services/parser.py` | Modify | Add `_get_fixed_text_per_para()`, `align_paragraphs()`; update `extract_fillable_values()`, `detect_checkbox_status()` |
| `backend/main.py` | Modify | Pass alignment to extraction functions; include `paragraph_mapping` in review responses |
| `backend/test_regex_extraction.py` | Modify | Add alignment unit tests + insert/delete extraction tests |
| `frontend/src/types/index.ts` | Modify | Add `paragraph_mapping`, `inserted_paragraphs` to response types |
| `frontend/src/views/ReviewWorkbench.vue` | Modify | Build `fieldMap` keyed by document paragraph index |
| `frontend/src/components/ValidationView.vue` | Modify | Build `paraFieldsMap` keyed by document paragraph index |

---

### Task 1: Add `align_paragraphs()` to parser.py with unit tests

**Files:**
- Modify: `backend/services/parser.py`
- Modify: `backend/test_regex_extraction.py`

**Interfaces:**
- Produces: `DocxParser._get_fixed_text_per_para(text, fillable_ranges) -> str`
- Produces: `DocxParser.align_paragraphs(tpl_paras, doc_paras, annotations) -> dict`

- [ ] **Step 1: Add `_get_fixed_text_per_para()` static method to parser.py**

Insert after the `extract_fixed_text()` method (after line 112), before `extract_fillable_values()`:

```python
    @staticmethod
    def _get_fixed_text_per_para(text: str, fillable_ranges: list[tuple[int, int]]) -> str:
        """Remove fillable zones from a single paragraph's text, returning the skeleton."""
        if not fillable_ranges:
            return text
        sorted_ranges = sorted(fillable_ranges, key=lambda r: r[0])
        fixed_parts = []
        pos = 0
        for start, end in sorted_ranges:
            if pos < start:
                fixed_parts.append(text[pos:start])
            pos = max(pos, end)
        if pos < len(text):
            fixed_parts.append(text[pos:])
        return "".join(fixed_parts)
```

- [ ] **Step 2: Add `align_paragraphs()` static method to parser.py**

Insert after `_get_fixed_text_per_para()`:

```python
    @staticmethod
    def align_paragraphs(tpl_paras: list[dict], doc_paras: list[dict],
                         annotations: list[dict]) -> dict:
        """Align template paragraphs to document paragraphs via skeleton-text matching.

        Returns {"mapping": {tpl_idx: doc_idx|None}, "inserted": [doc_idx, ...]}
        """
        from difflib import SequenceMatcher

        ann_by_para: dict[int, list[dict]] = {}
        for a in annotations:
            if a.get("zone_type") != "fillable":
                continue
            ann_by_para.setdefault(a["paragraph_index"], []).append(a)

        tpl_skeletons = []
        for p in tpl_paras:
            ranges = [(a["start_char"], a["end_char"])
                      for a in ann_by_para.get(p["index"], [])]
            tpl_skeletons.append(
                DocxParser._get_fixed_text_per_para(p["text"], ranges))

        doc_texts = [p["text"] for p in doc_paras]

        i, j = 0, 0
        mapping: dict[int, int | None] = {}
        inserted: list[int] = []

        while i < len(tpl_skeletons) and j < len(doc_texts):
            cur = SequenceMatcher(None, tpl_skeletons[i], doc_texts[j]).ratio()

            skip = 0.0
            if j + 1 < len(doc_texts):
                skip = SequenceMatcher(None, tpl_skeletons[i], doc_texts[j + 1]).ratio()

            drop = 0.0
            if i + 1 < len(tpl_skeletons):
                drop = SequenceMatcher(None, tpl_skeletons[i + 1], doc_texts[j]).ratio()

            if cur >= 0.5:
                mapping[i] = j
                i += 1
                j += 1
            elif skip > cur:
                inserted.append(j)
                j += 1
            elif drop > cur:
                mapping[i] = None
                i += 1
            else:
                mapping[i] = j
                i += 1
                j += 1

        while i < len(tpl_skeletons):
            mapping[i] = None
            i += 1
        while j < len(doc_texts):
            inserted.append(j)
            j += 1

        return {"mapping": mapping, "inserted": inserted}
```

- [ ] **Step 3: Add alignment unit tests to test_regex_extraction.py**

Add the following test functions before the `if __name__ == "__main__":` block:

```python
def test_align_identity():
    """Same paragraphs → identity mapping."""
    print("Test 9: identity alignment")
    with tempfile.TemporaryDirectory() as tmp:
        tpl = os.path.join(tmp, "tpl.docx")
        doc = os.path.join(tmp, "doc.docx")
        make_docx(["甲方：_____", "乙方：_____", "金额：_____元"], tpl)
        make_docx(["甲方：阿里", "乙方：腾讯", "金额：5000元"], doc)

        tpl_paras = DocxParser.parse(tpl)
        doc_paras = DocxParser.parse(doc)
        annotations = [
            {"paragraph_index": 0, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 1, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 2, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
        ]
        result = DocxParser.align_paragraphs(tpl_paras, doc_paras, annotations)

        assert result["mapping"] == {0: 0, 1: 1, 2: 2}, f"FAIL: {result['mapping']}"
        assert result["inserted"] == [], f"FAIL: {result['inserted']}"
        print("  PASS")


def test_align_insert_middle():
    """Document has an extra paragraph in the middle."""
    print("Test 10: insert paragraph in middle")
    with tempfile.TemporaryDirectory() as tmp:
        tpl = os.path.join(tmp, "tpl.docx")
        doc = os.path.join(tmp, "doc.docx")
        make_docx(["甲方：_____", "乙方：_____", "金额：_____元"], tpl)
        make_docx(["甲方：阿里", "新增条款", "乙方：腾讯", "金额：5000元"], doc)

        tpl_paras = DocxParser.parse(tpl)
        doc_paras = DocxParser.parse(doc)
        annotations = [
            {"paragraph_index": 0, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 1, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 2, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
        ]
        result = DocxParser.align_paragraphs(tpl_paras, doc_paras, annotations)

        assert result["mapping"] == {0: 0, 1: 2, 2: 3}, f"FAIL: {result['mapping']}"
        assert result["inserted"] == [1], f"FAIL: {result['inserted']}"
        print("  PASS")


def test_align_delete_middle():
    """Document is missing a paragraph from the middle."""
    print("Test 11: delete paragraph in middle")
    with tempfile.TemporaryDirectory() as tmp:
        tpl = os.path.join(tmp, "tpl.docx")
        doc = os.path.join(tmp, "doc.docx")
        make_docx(["甲方：_____", "乙方：_____", "金额：_____元"], tpl)
        make_docx(["甲方：阿里", "金额：5000元"], doc)

        tpl_paras = DocxParser.parse(tpl)
        doc_paras = DocxParser.parse(doc)
        annotations = [
            {"paragraph_index": 0, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 1, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 2, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
        ]
        result = DocxParser.align_paragraphs(tpl_paras, doc_paras, annotations)

        assert result["mapping"] == {0: 0, 1: None, 2: 1}, f"FAIL: {result['mapping']}"
        assert result["inserted"] == [], f"FAIL: {result['inserted']}"
        print("  PASS")


def test_align_no_annotations():
    """No annotations → full-text matching fallback."""
    print("Test 12: alignment without annotations")
    with tempfile.TemporaryDirectory() as tmp:
        tpl = os.path.join(tmp, "tpl.docx")
        doc = os.path.join(tmp, "doc.docx")
        make_docx(["第一条 定义", "第二条 义务", "第三条 违约"], tpl)
        make_docx(["第一条 定义", "新条款", "第二条 义务", "第三条 违约"], doc)

        tpl_paras = DocxParser.parse(tpl)
        doc_paras = DocxParser.parse(doc)
        result = DocxParser.align_paragraphs(tpl_paras, doc_paras, [])

        assert result["mapping"][0] == 0, f"FAIL: para 0 should match"
        assert result["mapping"][1] == 2, f"FAIL: para 1→2, got {result['mapping']}"
        assert result["mapping"][2] == 3, f"FAIL: para 2→3, got {result['mapping']}"
        assert 1 in result["inserted"], f"FAIL: doc[1] should be inserted"
        print("  PASS")
```

- [ ] **Step 4: Run the new alignment tests**

```bash
cd backend && uv run python test_regex_extraction.py
```

Expected: Tests 9-12 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/parser.py backend/test_regex_extraction.py
git commit -m "feat: add paragraph alignment engine with unit tests"
```

---

### Task 2: Wire alignment into `extract_fillable_values()` and `detect_checkbox_status()`

**Files:**
- Modify: `backend/services/parser.py`
- Modify: `backend/test_regex_extraction.py`

**Interfaces:**
- Consumes: `DocxParser.align_paragraphs()` from Task 1
- Modifies: `extract_fillable_values()` — use alignment mapping instead of direct `pi` index
- Modifies: `detect_checkbox_status()` — same

- [ ] **Step 1: Update `extract_fillable_values()` to use alignment**

In `backend/services/parser.py`, change the method signature and add alignment computation at the top of the function body. Replace lines 125-128:

Old (lines 125-128):
```python
        template_doc = Document(template_file_path)
        doc_doc = Document(doc_file_path)
        tpl_texts = _get_all_texts(template_doc)
        doc_texts = _get_all_texts(doc_doc)
```

New:
```python
        template_doc = Document(template_file_path)
        doc_doc = Document(doc_file_path)
        tpl_texts = _get_all_texts(template_doc)
        doc_texts = _get_all_texts(doc_doc)

        # Compute paragraph alignment
        tpl_paras = DocxParser.parse(template_file_path)
        doc_paras = DocxParser.parse(doc_file_path)
        alignment = DocxParser.align_paragraphs(tpl_paras, doc_paras, annotations)
        para_map = alignment["mapping"]
```

Then replace the paragraph index usage. Change lines 138-143:

Old:
```python
        for pi, anns in ann_by_para.items():
            if pi >= len(tpl_texts) or pi >= len(doc_texts):
                continue

            tpl_text = tpl_texts[pi]
            doc_text = doc_texts[pi]
```

New:
```python
        for pi, anns in ann_by_para.items():
            if pi >= len(tpl_texts):
                continue
            doc_pi = para_map.get(pi)
            if doc_pi is None or doc_pi >= len(doc_texts):
                continue

            tpl_text = tpl_texts[pi]
            doc_text = doc_texts[doc_pi]
```

- [ ] **Step 2: Update `detect_checkbox_status()` to use alignment**

In the same file, replace the checkbox function's internal text loading. After line 209 (`doc_texts = _get_all_texts(doc_doc)`), add:

```python
        # Compute paragraph alignment
        tpl_paras = DocxParser.parse(template_file_path)
        doc_paras = DocxParser.parse(doc_file_path)
        alignment = DocxParser.align_paragraphs(tpl_paras, doc_paras, annotations)
        para_map = alignment["mapping"]
```

Then in the loop (around line 229), change:

Old:
```python
        for ann in checkbox_anns:
            pi = ann["paragraph_index"]
            if pi >= len(tpl_texts) or pi >= len(doc_texts):
                continue
```

New:
```python
        for ann in checkbox_anns:
            pi = ann["paragraph_index"]
            if pi >= len(tpl_texts):
                continue
            doc_pi = para_map.get(pi)
            if doc_pi is None or doc_pi >= len(doc_texts):
                continue
```

And change `doc_text = doc_texts[pi]` to `doc_text = doc_texts[doc_pi]`.

- [ ] **Step 3: Add extraction integration tests**

In `test_regex_extraction.py`, add:

```python
def test_extract_with_inserted_paragraph():
    """Document has an extra paragraph → fillable values after it still extract."""
    print("Test 13: extract values with inserted paragraph")
    with tempfile.TemporaryDirectory() as tmp:
        tpl = os.path.join(tmp, "tpl.docx")
        doc = os.path.join(tmp, "doc.docx")
        make_docx(["甲方：_____", "乙方：_____", "金额：_____元"], tpl)
        make_docx(["甲方：阿里", "新增条款内容", "乙方：腾讯", "金额：5000元"], doc)

        annotations = [
            {"paragraph_index": 0, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 1, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 2, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
        ]
        values = DocxParser.extract_fillable_values(tpl, doc, annotations)

        assert values["0_3"]["value"] == "阿里", f"FAIL: para 0: '{values['0_3']}'"
        assert values["1_3"]["value"] == "腾讯", f"FAIL: para 1: '{values.get('1_3', 'MISSING')}'"
        assert values["2_3"]["value"] == "5000", f"FAIL: para 2: '{values.get('2_3', 'MISSING')}'"
        print("  PASS")


def test_extract_with_deleted_paragraph():
    """Document missing a paragraph → its fields skipped, subsequent ones intact."""
    print("Test 14: extract values with deleted paragraph")
    with tempfile.TemporaryDirectory() as tmp:
        tpl = os.path.join(tmp, "tpl.docx")
        doc = os.path.join(tmp, "doc.docx")
        make_docx(["甲方：_____", "乙方：_____", "金额：_____元"], tpl)
        make_docx(["甲方：阿里", "金额：5000元"], doc)

        annotations = [
            {"paragraph_index": 0, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 1, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
            {"paragraph_index": 2, "start_char": 3, "end_char": 8, "zone_type": "fillable"},
        ]
        values = DocxParser.extract_fillable_values(tpl, doc, annotations)

        assert values["0_3"]["value"] == "阿里", f"FAIL: para 0: '{values['0_3']}'"
        assert "1_3" not in values, f"FAIL: deleted para should be absent"
        assert values["2_3"]["value"] == "5000", f"FAIL: para 2: '{values.get('2_3', 'MISSING')}'"
        print("  PASS")
```

- [ ] **Step 4: Run all tests**

```bash
cd backend && uv run python test_regex_extraction.py
```

Expected: All 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/parser.py backend/test_regex_extraction.py
git commit -m "feat: wire paragraph alignment into fillable value extraction"
```

---

### Task 3: Wire alignment into review endpoints (paragraph_mapping in responses)

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `DocxParser.align_paragraphs()` from Task 1
- Modifies: `review_compare()` — add `paragraph_mapping`, `inserted_paragraphs` to response
- Modifies: `review_validate()` — add same fields; use document paragraph index for `paragraph_text`

- [ ] **Step 1: Update `review_compare()` to include alignment**

In `review_compare()`, after line 281 (`fillable_ranges = _build_global_ranges(...)`), add:

```python
        # Compute paragraph alignment for frontend display
        template_paras = DocxParser.parse(template_path)
        doc_paras = DocxParser.parse(doc_path)
        alignment = DocxParser.align_paragraphs(template_paras, doc_paras, ann_list)
```

Then before the `return result` at line 299, add:

```python
        result["paragraph_mapping"] = alignment["mapping"]
        result["inserted_paragraphs"] = alignment["inserted"]
```

- [ ] **Step 2: Update `review_validate()` to include alignment and fix paragraph_text**

After line 397 (`template_paras_list = DocxParser.parse(template_path)`), and before the loop that attaches paragraph_text, add alignment computation:

Replace lines 396-402:

Old:
```python
        doc_paras_list = DocxParser.parse(doc_path)
        template_paras_list = DocxParser.parse(template_path)
        doc_paras = {p["index"]: p["text"] for p in doc_paras_list}
        template_paras = {p["index"]: p["text"] for p in template_paras_list}
        for r in result["results"]:
            r["paragraph_text"] = doc_paras.get(r["paragraph"], "")
            r["template_paragraph_text"] = template_paras.get(r["paragraph"], "")
```

New:
```python
        doc_paras_list = DocxParser.parse(doc_path)
        template_paras_list = DocxParser.parse(template_path)
        alignment = DocxParser.align_paragraphs(template_paras_list, doc_paras_list, ann_list)
        para_map = alignment["mapping"]
        doc_paras = {p["index"]: p["text"] for p in doc_paras_list}
        template_paras = {p["index"]: p["text"] for p in template_paras_list}
        for r in result["results"]:
            doc_pi = para_map.get(r["paragraph"])
            if doc_pi is not None:
                r["paragraph_text"] = doc_paras.get(doc_pi, "")
            else:
                r["paragraph_text"] = ""
            r["template_paragraph_text"] = template_paras.get(r["paragraph"], "")
```

Then before `conn.execute(...)` near line 527, add:

```python
        result["paragraph_mapping"] = alignment["mapping"]
        result["inserted_paragraphs"] = alignment["inserted"]
```

- [ ] **Step 3: Run existing tests to verify no regressions**

```bash
cd backend && uv run python test_regex_extraction.py
```

Expected: All 14 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: include paragraph_mapping in review endpoint responses"
```

---

### Task 4: Frontend — consume paragraph_mapping for correct highlighting

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/views/ReviewWorkbench.vue`
- Modify: `frontend/src/components/ValidationView.vue`

**Interfaces:**
- Consumes: `paragraph_mapping`, `inserted_paragraphs` from API responses
- Modifies: `buildFieldMap()` → key by document paragraph index using mapping
- Modifies: `ValidationView.paraFieldsMap` → same

- [ ] **Step 1: Update TypeScript types**

In `frontend/src/types/index.ts`, add to `CompareResult` and `ValidateResult` interfaces. Find the relevant interfaces and add:

```typescript
paragraph_mapping?: Record<number, number | null>
inserted_paragraphs?: number[]
```

Add these to both `CompareResult` and `ValidateResult` interfaces.

- [ ] **Step 2: Update ReviewWorkbench `buildFieldMap()`**

In `frontend/src/views/ReviewWorkbench.vue`, change the `buildFieldMap` function (around line 305):

Old:
```typescript
function buildFieldMap(): Record<number, FieldResult[]> {
  const map: Record<number, FieldResult[]> = {}
  if (!validateResult.value) return map
  for (const r of validateResult.value.results) {
    if (!map[r.paragraph]) map[r.paragraph] = []
    map[r.paragraph].push(r)
  }
  return map
}
```

New:
```typescript
function buildFieldMap(): Record<number, FieldResult[]> {
  const map: Record<number, FieldResult[]> = {}
  if (!validateResult.value) return map
  const mapping = validateResult.value.paragraph_mapping ?? {}
  for (const r of validateResult.value.results) {
    const docPi = mapping[r.paragraph] ?? r.paragraph
    if (!map[docPi]) map[docPi] = []
    map[docPi].push(r)
  }
  return map
}
```

- [ ] **Step 3: Update ValidationView `paraFieldsMap`**

In `frontend/src/components/ValidationView.vue`, change the `paraFieldsMap` computed (around line 81):

Old:
```typescript
const paraFieldsMap = computed(() => {
  const map: Record<number, FieldResult[]> = {}
  for (const r of props.result.results) {
    if (!map[r.paragraph]) map[r.paragraph] = []
    map[r.paragraph].push(r)
  }
  return map
})
```

New:
```typescript
const paraFieldsMap = computed(() => {
  const map: Record<number, FieldResult[]> = {}
  const mapping = props.result.paragraph_mapping ?? {}
  for (const r of props.result.results) {
    const docPi = mapping[r.paragraph] ?? r.paragraph
    if (!map[docPi]) map[docPi] = []
    map[docPi].push(r)
  }
  return map
})
```

- [ ] **Step 4: Verify frontend compiles**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/views/ReviewWorkbench.vue frontend/src/components/ValidationView.vue
git commit -m "feat: use paragraph_mapping for correct field-to-document-paragraph alignment"
```
