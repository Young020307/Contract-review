# Paragraph Alignment: Template-Document Mapping for Insert/Delete Resilience

## Problem

When a document uploaded for review has paragraphs inserted or deleted relative to the template, results after the change point are entirely wrong: fillable values can't be matched, validation results fail, and highlighting misaligns.

**Root cause:** the system assumes 1:1 positional correspondence by array index between template paragraphs and document paragraphs. When the paragraph counts differ, every downstream consumer breaks:
- `extract_fillable_values()` maps template annotations to wrong document paragraphs
- `review_validate()` attaches wrong paragraph text to field results
- `renderedParagraphs` splits highlights at wrong positions in wrong paragraphs

## Approach: Skeleton-Text Sequence Matching (方案 C)

Use `difflib.SequenceMatcher` at the paragraph level, but compare **fixed_text** (paragraph text with fillable zones removed) rather than raw text. This prevents normal fillable-value differences (e.g. `_____` vs `深圳市某某科技有限公司`) from being mistaken for paragraph mismatches.

## Design

### 1. New Function: `align_paragraphs()` in `parser.py`

```
align_paragraphs(tpl_paras, doc_paras, annotations) → Alignment
```

**Internal logic (double-pointer walk):**

1. Build `tpl_fixed_texts[]` — for each template paragraph, extract skeleton by removing fillable zones. Paragraphs without annotations use raw text as fallback.
2. For each position `(i, j)` in template/docs:
   - Compute 3 similarity scores via `SequenceMatcher.ratio()`:
     - `cur  = sim(tpl_fixed[i], doc_raw[j])`
     - `skip = sim(tpl_fixed[i], doc_raw[j+1])`
     - `drop = sim(tpl_fixed[i+1], doc_raw[j])`
   - Decision:
     - `cur >= 0.5` → match, i++, j++
     - `skip > cur` → doc[j] is inserted, j++
     - `drop > cur` → tpl[i] is deleted, i++
     - else → degraded match, i++, j++

**Output:**
```json
{
  "mapping": { "0": 0, "1": 1, "2": null, "3": 2 },
  "inserted": [2]
}
```
- `mapping`: template_para_index → document_para_index (null = deleted)
- `inserted`: document paragraph indices with no template counterpart

3. Table-cell paragraphs (`is_table_cell`) participate in alignment identically to body paragraphs.

### 2. Downstream Consumers

#### 2.1 `extract_fillable_values()` — Value Extraction

Replace `doc_texts[pi]` with `doc_texts[alignment.mapping[pi]]`. Deleted paragraphs (mapping → null) are skipped.

#### 2.2 `review_compare()` — Diff Comparison

`_build_global_ranges()` and `_neutralize_fillable_diffs()` remain unchanged — they operate in template-side global coordinates, which are still correct.

#### 2.3 `review_validate()` — Validation

After extracting values, use `paragraph_mapping` to remap `r["paragraph"]` to the document paragraph index for display. Also remap `paragraph_text` attachment to use the correct document paragraph.

#### 2.4 Frontend `renderedParagraphs` — Highlighting

Receive `paragraph_mapping` in both compare and validate API responses. Build `fieldMapByDoc` keyed by document paragraph index (not template index):
```typescript
const docFieldMap: Record<number, FieldResult[]> = {}
for (const r of results) {
  const docPi = paragraphMapping[r.paragraph]
  if (docPi == null) continue
  if (!docFieldMap[docPi]) docFieldMap[docPi] = []
  docFieldMap[docPi].push(r)
}
```

### 3. API Response Additions

Both `POST /api/review/compare` and `POST /api/review/validate` responses gain:
```json
{
  "paragraph_mapping": { "0": 0, "1": 1, "2": null, "3": 2 },
  "inserted_paragraphs": [2]
}
```

### 4. Existing `extract_fixed_text()` Reuse

`DocxParser.extract_fixed_text()` already removes fillable zones from paragraph text. Use its per-paragraph logic internally in `align_paragraphs()` to build the skeleton texts.

## Edge Cases

| Case | Handling |
|------|----------|
| Document has extra paragraphs (insertion) | `inserted` list, no value extraction, shown as plain text |
| Template paragraph deleted from document | `mapping[pi] = null`, fillable fields skipped, marked "段落不存在" |
| Same paragraph count but content heavily rewritten | Similarity < 0.5 → treated as delete + insert |
| Consecutive multi-paragraph insert/delete | Double-pointer loop handles chains naturally |
| Paragraphs without annotations | Fixed text falls back to raw paragraph text |
| Table-cell paragraphs | Identical alignment logic; `is_table_cell` flag preserved |
| Matching at start/end boundaries | Loop terminates when both indices reach end; remaining items classified as insert or delete |
| No insertions or deletions (document matches template) | Alignment produces identity mapping (1:1), all downstream code path unchanged |

## Test Plan

New tests in `test_regex_extraction.py`:

1. **test_insert_paragraph** — Insert one paragraph mid-document, verify subsequent fillable values still extract correctly
2. **test_delete_paragraph** — Delete one paragraph, verify its fields are skipped, subsequent fields extract correctly
3. **test_alignment_mapping_keys** — Verify `paragraph_mapping` entries match expected template→document correspondence
4. **test_no_change** — Verify identity mapping when template and document have identical paragraph structure
5. **test_table_insert** — Insert a paragraph inside a table, verify alignment handles `is_table_cell` correctly

## Out of Scope

- Annotation storage model (unchanged — annotations always keyed by template paragraph index)
- Character-level diff engine
- Frontend UI layout and styling
- Auto rule generation (`generate_rules.py`)
