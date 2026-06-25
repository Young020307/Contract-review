# Integration API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a unified `/api/integration/v1` external API with 12 endpoints (all existing functionality + one-stop review orchestration) by extracting a review service layer and adding a new integration router.

**Architecture:** Extract `run_compare()` and `run_validate()` from `routers/review.py` into `services/review_service.py` as pure business-logic functions. Both the existing review router and the new integration router become thin wrappers that call these service functions. Template and document integration endpoints duplicate the existing thin router logic (acceptable tradeoff per spec).

**Tech Stack:** FastAPI, Python, SQLite (via `database.get_connection()`), python-docx, difflib

## Global Constraints

- File I/O and DB record creation stay in router layer; Service layer operates on existing resources by ID
- Error handling uses standard `HTTPException` — no custom exception classes
- No auth for now
- Existing internal API must remain backward-compatible
- Response format matches existing API (no `{code, message, data}` wrapper)

---

### Task 1: Create `backend/services/review_service.py`

**Files:**
- Create: `backend/services/review_service.py`

**Interfaces:**
- Consumes: `database.get_connection`, `utils.resolve_path`, `services.parser.DocxParser`, `services.diff_engine.DiffEngine`, `services.validator.RuleValidator`
- Produces: `run_compare(template_id, document_id) -> dict | None`, `run_validate(template_id, document_id) -> dict | None`

- [ ] **Step 1: Write the file**

```python
import json
from database import get_connection
from services.parser import DocxParser
from services.diff_engine import DiffEngine
from services.validator import RuleValidator
from utils import resolve_path


def _build_fillable_by_para(ann_list: list[dict]) -> dict[int, list[tuple[int, int]]]:
    """Group fillable zone annotations by template paragraph index."""
    result: dict[int, list[tuple[int, int]]] = {}
    for a in ann_list:
        if a.get("zone_type") != "fillable":
            continue
        pi = a["paragraph_index"]
        result.setdefault(pi, []).append((a["start_char"], a["end_char"]))
    return result


def _parse_annotation_rules(rules) -> dict:
    if isinstance(rules, str):
        try:
            return json.loads(rules)
        except (json.JSONDecodeError, TypeError):
            return {}
    return rules or {}


def run_compare(template_id: int, document_id: int) -> dict | None:
    """Run paragraph-level diff comparison between template and document.

    Returns the comparison result dict, or None if either ID is invalid.
    """
    conn = get_connection()
    try:
        template = conn.execute(
            "SELECT file_path FROM templates WHERE id = ?", (template_id,)
        ).fetchone()
        document = conn.execute(
            "SELECT file_path FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if not template or not document:
            return None

        template_path = resolve_path(template["file_path"])
        doc_path = resolve_path(document["file_path"])

        annotations = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type "
            "FROM annotations WHERE template_id = ?",
            (template_id,)
        ).fetchall()
        ann_list = [dict(a) for a in annotations]

        template_paras = DocxParser.parse(template_path)
        doc_paras = DocxParser.parse(doc_path)
        alignment = DocxParser.align_paragraphs(template_paras, doc_paras, ann_list)

        fillable_by_para = _build_fillable_by_para(ann_list)

        result = DiffEngine.compare_aligned(
            template_paras, doc_paras,
            alignment["mapping"], alignment["inserted"],
            fillable_by_para
        )
        result["template_text"] = DocxParser.extract_full_text(template_path)
        result["document_text"] = DocxParser.extract_full_text(doc_path)
        result["paragraph_mapping"] = alignment["mapping"]
        result["inserted_paragraphs"] = alignment["inserted"]
        return result
    finally:
        conn.close()


def run_validate(template_id: int, document_id: int) -> dict | None:
    """Run validation of fillable fields against annotation rules.

    Includes checkbox toggle detection, cross-field consistency checks,
    dependent-paragraph logic, radio-group mutual exclusion, and
    Arabic/Chinese amount matching.

    Returns the validation result dict, or None if either ID is invalid.
    """
    conn = get_connection()
    try:
        template = conn.execute(
            "SELECT file_path FROM templates WHERE id = ?", (template_id,)
        ).fetchone()
        document = conn.execute(
            "SELECT file_path FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if not template or not document:
            return None

        template_path = resolve_path(template["file_path"])
        doc_path = resolve_path(document["file_path"])

        annotations = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type, rules "
            "FROM annotations WHERE template_id = ?",
            (template_id,)
        ).fetchall()
        ann_list = [dict(a) for a in annotations]

        values = DocxParser.extract_fillable_values(template_path, doc_path, ann_list)
        checkbox_statuses = DocxParser.detect_checkbox_status(
            template_path, doc_path, ann_list
        )
        values.update(checkbox_statuses)
        result = RuleValidator.validate(values, ann_list)

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

        # ── Checkbox dependency: fillable fields gated by checkbox toggle ──
        checkbox_checked: dict[int, bool] = {}
        for a in ann_list:
            if a.get("zone_type") != "fillable":
                continue
            rules = _parse_annotation_rules(a.get("rules", "{}"))
            if not rules.get("radio_group"):
                continue
            pi = a["paragraph_index"]
            key = f"{pi}_{a.get('start_char', 0)}"
            checkbox_checked[pi] = checkbox_checked.get(pi, False) or values.get(key, {}).get("checked", False)

        for r in result["results"]:
            pi = r["paragraph"]
            if pi not in checkbox_checked:
                continue
            matched_ann = None
            for a in ann_list:
                if (a.get("zone_type") == "fillable"
                        and a["paragraph_index"] == pi
                        and a.get("start_char", 0) == r.get("start_char", 0)):
                    matched_ann = a
                    break
            if not matched_ann:
                continue
            rules = _parse_annotation_rules(matched_ann.get("rules", "{}"))
            if rules.get("radio_group"):
                continue
            key = f"{pi}_{matched_ann.get('start_char', 0)}"
            v = values.get(key, {})
            actual = v.get("value", "") if isinstance(v, dict) else (v or "")
            has_content = bool(str(actual).strip("_ "))
            if checkbox_checked[pi] and not has_content:
                r["pass"] = False
                r["reason"] = "该条款已勾选，需填写内容"
            elif not checkbox_checked[pi]:
                if has_content:
                    r["pass"] = False
                    r["reason"] = "该条款未勾选，不应填写内容"
                else:
                    r["pass"] = True
                    r["reason"] = ""

        # ── Dependent paragraph: cross-paragraph checkbox-content gating ──
        dep_para_any_checked: dict[int, bool] = {}
        dep_group_any_content: dict[int, bool] = {}
        for a in ann_list:
            if a.get("zone_type") != "fillable":
                continue
            rules = _parse_annotation_rules(a.get("rules", "{}"))
            deps = rules.get("dependent_paras", [])
            if not rules.get("radio_group") or not deps:
                continue
            pi = a["paragraph_index"]
            key = f"{pi}_{a.get('start_char', 0)}"
            is_checked = values.get(key, {}).get("checked", False)

            for dep_pi in deps:
                dep_para_any_checked[dep_pi] = dep_para_any_checked.get(dep_pi, False) or is_checked

            if is_checked:
                group_any = False
                for dep_pi in deps:
                    for r in result["results"]:
                        if r["paragraph"] != dep_pi:
                            continue
                        v = values.get(f"{dep_pi}_{r.get('start_char', 0)}", {})
                        actual = v.get("value", "") if isinstance(v, dict) else (v or "")
                        if bool(str(actual).strip("_ ")):
                            group_any = True
                            break
                    if group_any:
                        break
                for dep_pi in deps:
                    dep_group_any_content[dep_pi] = dep_group_any_content.get(dep_pi, False) or group_any

        for r in result["results"]:
            pi = r["paragraph"]
            if pi not in dep_para_any_checked:
                continue
            dep_ann = None
            for da in ann_list:
                if (da.get("zone_type") == "fillable"
                        and da["paragraph_index"] == pi
                        and da.get("start_char", 0) == r.get("start_char", 0)):
                    dep_ann = da
                    break
            if not dep_ann:
                continue
            dep_rules = _parse_annotation_rules(dep_ann.get("rules", "{}"))
            if dep_rules.get("radio_group"):
                continue
            dep_key = f"{pi}_{dep_ann.get('start_char', 0)}"
            v = values.get(dep_key, {})
            actual = v.get("value", "") if isinstance(v, dict) else (v or "")
            has_content = bool(str(actual).strip("_ "))

            if dep_para_any_checked[pi]:
                if not dep_group_any_content.get(pi, False):
                    r["pass"] = False
                    r["reason"] = "该条款已勾选，需填写内容"
                else:
                    r["pass"] = True
                    r["reason"] = ""
            else:
                if has_content:
                    r["pass"] = False
                    r["reason"] = "该条款未勾选，不应填写内容"
                else:
                    r["pass"] = True
                    r["reason"] = ""

        result["results"].sort(key=lambda r: r["pass"])

        result["document_paragraphs"] = [
            {"index": p["index"], "text": p["text"]} for p in doc_paras_list
        ]
        result["template_paragraphs"] = [
            {"index": p["index"], "text": p["text"]} for p in template_paras_list
        ]
        result["paragraph_mapping"] = alignment["mapping"]
        result["inserted_paragraphs"] = alignment["inserted"]
        return result
    finally:
        conn.close()
```

- [ ] **Step 2: Verify the file imports correctly**

Run: `cd backend && uv run python -c "from services.review_service import run_compare, run_validate; print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/services/review_service.py
git commit -m "feat: extract review_service with run_compare and run_validate"
```

---

### Task 2: Refactor `backend/routers/review.py` to use review_service

**Files:**
- Modify: `backend/routers/review.py`

**Interfaces:**
- Consumes: `services.review_service.run_compare`, `services.review_service.run_validate`
- Produces: Same two endpoints (`POST /api/review/compare`, `POST /api/review/validate`) with unchanged response format

- [ ] **Step 1: Replace the file content**

Replace the entire content of `backend/routers/review.py` with the slimmed-down version:

```python
import json
from fastapi import APIRouter, HTTPException
from database import get_connection
from models import ReviewRequest
from services.review_service import run_compare, run_validate

router = APIRouter(prefix="/api/review", tags=["review"])


@router.post("/compare")
def review_compare(body: ReviewRequest):
    result = run_compare(body.template_id, body.document_id)
    if result is None:
        raise HTTPException(404, "模板或文件不存在")

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) "
            "VALUES (?, ?, 'compare', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
    finally:
        conn.close()
    return result


@router.post("/validate")
def review_validate(body: ReviewRequest):
    result = run_validate(body.template_id, body.document_id)
    if result is None:
        raise HTTPException(404, "模板或文件不存在")

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) "
            "VALUES (?, ?, 'validate', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
    finally:
        conn.close()
    return result
```

Also remove the now-unused imports (`from services.parser import DocxParser`, `from services.diff_engine import DiffEngine`, `from services.validator import RuleValidator`, `from utils import resolve_path`) and the module-level helper functions (`_build_fillable_by_para`, `_parse_annotation_rules`).

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `cd backend && uv run pytest tests/ -v`
Expected: All 14 tests from `test_regex_extraction.py` pass. Any tests in `test_review_accuracy.py` or `test_all_templates.py` pass.

- [ ] **Step 3: Commit**

```bash
git add backend/routers/review.py
git commit -m "refactor: slim review router to thin wrapper over review_service"
```

---

### Task 3: Create `backend/routers/integration.py`

**Files:**
- Create: `backend/routers/integration.py`

**Interfaces:**
- Consumes: `services.review_service.run_compare`, `services.review_service.run_validate`, `services.parser.DocxParser`, `database.get_connection`, `utils.*`, `models.*`
- Produces: 12 endpoints under prefix `/api/integration/v1`

- [ ] **Step 1: Write the file**

```python
import json
import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse
from database import get_connection
from models import (
    AnnotationBatch, TemplateResponse, TemplateDetailResponse,
    DocumentResponse, ParagraphInfo, ReviewRequest
)
from services.parser import DocxParser
from services.review_service import run_compare, run_validate
from utils import UPLOAD_DIR, DOC_UPLOAD_DIR, resolve_path, decode_filename

router = APIRouter(prefix="/api/integration/v1", tags=["integration"])


# ── Templates ──

@router.post("/templates/upload", response_model=TemplateResponse)
async def integration_upload_template(file: UploadFile = File(...)):
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "只支持 .docx 文件")
    filename = decode_filename(file.filename)
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    rel_path = os.path.join("uploads", safe_name)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    conn = get_connection()
    try:
        paragraphs = DocxParser.parse(file_path)
        cur = conn.execute(
            "INSERT INTO templates (name, file_path, paragraph_count) VALUES (?, ?, ?)",
            (filename, rel_path, len(paragraphs))
        )
        conn.commit()
        template_id = cur.lastrowid
    finally:
        conn.close()
    return TemplateResponse(
        id=template_id, name=filename,
        paragraph_count=len(paragraphs), created_at=""
    )


@router.get("/templates", response_model=list[TemplateResponse])
def integration_list_templates():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, paragraph_count, created_at FROM templates ORDER BY id"
    ).fetchall()
    conn.close()
    return [
        TemplateResponse(
            id=r["id"], name=r["name"],
            paragraph_count=r["paragraph_count"],
            created_at=r["created_at"] or ""
        )
        for r in rows
    ]


@router.delete("/templates/{template_id}")
def integration_delete_template(template_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, file_path FROM templates WHERE id = ?", (template_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "模板不存在")
        file_path = resolve_path(row["file_path"])
        conn.execute("DELETE FROM review_tasks WHERE template_id = ?", (template_id,))
        conn.execute("DELETE FROM documents WHERE template_id = ?", (template_id,))
        conn.execute("DELETE FROM annotations WHERE template_id = ?", (template_id,))
        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        conn.commit()
        if os.path.exists(file_path):
            os.remove(file_path)
    finally:
        conn.close()
    return {"ok": True}


@router.get("/templates/{template_id}", response_model=TemplateDetailResponse)
def integration_get_template(template_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, file_path, created_at FROM templates WHERE id = ?",
            (template_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "模板不存在")
        paragraphs = DocxParser.parse(resolve_path(row["file_path"]))
        return TemplateDetailResponse(
            id=row["id"], name=row["name"],
            paragraphs=[
                ParagraphInfo(
                    index=p["index"], text=p["text"],
                    underline_ranges=p.get("underline_ranges", []),
                    is_table_cell=p.get("is_table_cell", False)
                )
                for p in paragraphs
            ],
            created_at=row["created_at"] or ""
        )
    finally:
        conn.close()


@router.post("/templates/{template_id}/annotations")
def integration_save_annotations(template_id: int, body: AnnotationBatch):
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM annotations WHERE template_id = ?", (template_id,))
        for ann in body.annotations:
            rules_json = "{}"
            if ann.zone_type == "fillable" and ann.rules:
                rules_json = ann.rules.model_dump_json()
            conn.execute(
                "INSERT OR REPLACE INTO annotations "
                "(template_id, paragraph_index, start_char, end_char, zone_type, rules) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (template_id, ann.paragraph_index, ann.start_char, ann.end_char,
                 ann.zone_type, rules_json)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"ok": True, "count": len(body.annotations)}


@router.get("/templates/{template_id}/annotations")
def integration_get_annotations(template_id: int):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type, rules "
            "FROM annotations WHERE template_id = ? "
            "ORDER BY paragraph_index, start_char",
            (template_id,)
        ).fetchall()
        return [
            {
                "paragraph_index": r["paragraph_index"],
                "start_char": r["start_char"],
                "end_char": r["end_char"],
                "zone_type": r["zone_type"],
                "rules": r["rules"] if r["rules"] else "{}"
            }
            for r in rows
        ]
    finally:
        conn.close()


# ── Documents ──

@router.get("/documents/proxy-template/{template_id}")
async def integration_proxy_template_file(template_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT file_path FROM templates WHERE id = ?", (template_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404)
    return FileResponse(
        resolve_path(row["file_path"]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@router.post("/documents/upload", response_model=DocumentResponse)
async def integration_upload_document(
    file: UploadFile = File(...),
    template_id: int = Query(...)
):
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "只支持 .docx 文件")
    filename = decode_filename(file.filename)
    safe_name = f"doc_{uuid.uuid4().hex}_{filename}"
    os.makedirs(DOC_UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOC_UPLOAD_DIR, safe_name)
    rel_path = os.path.join("temp", safe_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    conn = get_connection()
    try:
        paragraphs = DocxParser.parse(file_path)
        cur = conn.execute(
            "INSERT INTO documents (template_id, name, file_path) VALUES (?, ?, ?)",
            (template_id, filename, rel_path)
        )
        conn.commit()
        doc_id = cur.lastrowid
    finally:
        conn.close()
    return DocumentResponse(
        id=doc_id, name=filename, template_id=template_id,
        paragraphs=[
            ParagraphInfo(
                index=p["index"], text=p["text"],
                underline_ranges=p.get("underline_ranges", []),
                is_table_cell=p.get("is_table_cell", False)
            )
            for p in paragraphs
        ],
        uploaded_at=""
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def integration_get_document(document_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, template_id, file_path, uploaded_at "
            "FROM documents WHERE id = ?",
            (document_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "文件不存在")
        paragraphs = DocxParser.parse(resolve_path(row["file_path"]))
    finally:
        conn.close()
    return DocumentResponse(
        id=row["id"], name=row["name"], template_id=row["template_id"],
        paragraphs=[
            ParagraphInfo(
                index=p["index"], text=p["text"],
                underline_ranges=p.get("underline_ranges", []),
                is_table_cell=p.get("is_table_cell", False)
            )
            for p in paragraphs
        ],
        uploaded_at=row["uploaded_at"] or ""
    )


# ── Review ──

@router.post("/review/compare")
def integration_review_compare(body: ReviewRequest):
    result = run_compare(body.template_id, body.document_id)
    if result is None:
        raise HTTPException(404, "模板或文件不存在")

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) "
            "VALUES (?, ?, 'compare', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
    finally:
        conn.close()
    return result


@router.post("/review/validate")
def integration_review_validate(body: ReviewRequest):
    result = run_validate(body.template_id, body.document_id)
    if result is None:
        raise HTTPException(404, "模板或文件不存在")

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) "
            "VALUES (?, ?, 'validate', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
    finally:
        conn.close()
    return result


@router.post("/review/full")
async def integration_review_full(
    template_id: int = Form(...),
    file: UploadFile = File(...)
):
    """One-stop review: upload document, run compare, run validate."""
    # Validate template exists
    conn = get_connection()
    try:
        template = conn.execute(
            "SELECT id FROM templates WHERE id = ?", (template_id,)
        ).fetchone()
        if not template:
            raise HTTPException(404, "模板不存在")
    finally:
        conn.close()

    # Validate file type
    if not file.filename or not file.filename.endswith(".docx"):
        raise HTTPException(400, "只支持 .docx 文件")

    # Save uploaded document file (router-layer: file I/O)
    filename = decode_filename(file.filename)
    safe_name = f"doc_{uuid.uuid4().hex}_{filename}"
    os.makedirs(DOC_UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOC_UPLOAD_DIR, safe_name)
    rel_path = os.path.join("temp", safe_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Create document record (router-layer: DB record creation)
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO documents (template_id, name, file_path) VALUES (?, ?, ?)",
            (template_id, filename, rel_path)
        )
        conn.commit()
        document_id = cur.lastrowid
    finally:
        conn.close()

    # Run review (service-layer: pure business logic)
    compare_result = run_compare(template_id, document_id)
    if compare_result is None:
        raise HTTPException(500, "比对失败")

    validate_result = run_validate(template_id, document_id)
    if validate_result is None:
        raise HTTPException(500, "校验失败")

    # Save review_task records (router-layer: audit trail)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) "
            "VALUES (?, ?, 'compare', ?)",
            (template_id, document_id, json.dumps(compare_result, ensure_ascii=False))
        )
        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) "
            "VALUES (?, ?, 'validate', ?)",
            (template_id, document_id, json.dumps(validate_result, ensure_ascii=False))
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "document_id": document_id,
        "compare": compare_result,
        "validate": validate_result
    }
```

- [ ] **Step 2: Verify the file imports correctly**

Run: `cd backend && uv run python -c "from routers.integration import router; print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/routers/integration.py
git commit -m "feat: add integration router with 12 endpoints"
```

---

### Task 4: Register integration router in `backend/main.py`

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `routers.integration.router`
- Produces: New route prefix `/api/integration/v1` available on the app

- [ ] **Step 1: Add the import and registration**

Add after the existing router imports:

```python
from routers.integration import router as integration_router
```

Add after the existing `app.include_router` calls:

```python
app.include_router(integration_router)
```

- [ ] **Step 2: Start the server and smoke-test a GET endpoint**

Run server: `cd backend && uv run python main.py` (background, or just check it starts)

Run: `curl -s http://localhost:8000/api/integration/v1/templates`
Expected: JSON array (may be empty)

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: register integration router in main app"
```

---

### Task 5: Write integration test

**Files:**
- Create: `backend/tests/test_integration_api.py`

**Interfaces:**
- Consumes: Integration router endpoints via FastAPI TestClient
- Produces: Test coverage for integration API

- [ ] **Step 1: Write the test file**

```python
"""Smoke tests for the integration API endpoints."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from main import app
import database

database.init_db()
client = TestClient(app)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DOCX = os.path.join(BACKEND_DIR, "uploads",
    "5b03a5999bc2404ba1df910034a4f29d_咨询服务标准合同-调整板V4.docx")


def _get_first_template_id():
    resp = client.get("/api/integration/v1/templates")
    items = resp.json()
    return items[0]["id"] if items else None


def test_list_templates():
    resp = client.get("/api/integration/v1/templates")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_template_not_found():
    resp = client.get("/api/integration/v1/templates/99999")
    assert resp.status_code == 404


def test_upload_template():
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/templates/upload",
            files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] > 0
    assert data["paragraph_count"] > 0


def test_get_template():
    tid = _get_first_template_id()
    if not tid:
        return
    resp = client.get(f"/api/integration/v1/templates/{tid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == tid


def test_list_annotations():
    tid = _get_first_template_id()
    if not tid:
        return
    resp = client.get(f"/api/integration/v1/templates/{tid}/annotations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_upload_document():
    tid = _get_first_template_id()
    if not tid:
        return
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            f"/api/integration/v1/documents/upload?template_id={tid}",
            files={"file": ("test_doc.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] > 0


def test_compare():
    tid = _get_first_template_id()
    if not tid:
        return
    # Get a document for this template
    from database import get_connection
    conn = get_connection()
    doc = conn.execute(
        "SELECT id FROM documents WHERE template_id = ? ORDER BY id DESC LIMIT 1",
        (tid,)
    ).fetchone()
    conn.close()
    if not doc:
        return
    resp = client.post(
        "/api/integration/v1/review/compare",
        json={"template_id": tid, "document_id": doc["id"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "diffs" in data
    assert "violations" in data


def test_validate():
    tid = _get_first_template_id()
    if not tid:
        return
    from database import get_connection
    conn = get_connection()
    doc = conn.execute(
        "SELECT id FROM documents WHERE template_id = ? ORDER BY id DESC LIMIT 1",
        (tid,)
    ).fetchone()
    conn.close()
    if not doc:
        return
    resp = client.post(
        "/api/integration/v1/review/validate",
        json={"template_id": tid, "document_id": doc["id"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data


def test_full_review():
    """End-to-end: upload docx + compare + validate in one call."""
    tid = _get_first_template_id()
    if not tid:
        return
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/review/full",
            data={"template_id": str(tid)},
            files={"file": ("full_test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "document_id" in data
    assert data["document_id"] > 0
    assert "compare" in data
    assert "validate" in data
    assert "diffs" in data["compare"]
    assert "results" in data["validate"]


def test_full_review_bad_template():
    """Non-existent template should return 404."""
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/review/full",
            data={"template_id": "99999"},
            files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 404


def test_full_review_bad_file():
    """Non-docx file should return 400."""
    tid = _get_first_template_id()
    if not tid:
        return
    resp = client.post(
        "/api/integration/v1/review/full",
        data={"template_id": str(tid)},
        files={"file": ("test.txt", b"hello world", "text/plain")}
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run the integration tests**

Run: `cd backend && uv run pytest tests/test_integration_api.py -v`
Expected: All tests pass (some may skip if no template exists in DB, which is fine for a fresh clone)

- [ ] **Step 3: Run full test suite to confirm no regression**

Run: `cd backend && uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_integration_api.py
git commit -m "test: add integration API smoke tests"
```

---

### Task 6: Final verification and cleanup

- [ ] **Step 1: Start the dev server and verify all routes are registered**

Run: `cd backend && timeout 3 uv run python -c "from main import app; [print(r.path) for r in app.routes]" || true`

Expected output includes:
```
/api/health
/api/templates/upload
/api/templates
/api/templates/{template_id}
/api/templates/{template_id}/annotations
/api/documents/upload
/api/documents/{document_id}
/api/documents/proxy-template/{template_id}
/api/review/compare
/api/review/validate
/api/integration/v1/templates/upload
/api/integration/v1/templates
/api/integration/v1/templates/{template_id}
/api/integration/v1/templates/{template_id}/annotations
/api/integration/v1/documents/upload
/api/integration/v1/documents/{document_id}
/api/integration/v1/documents/proxy-template/{template_id}
/api/integration/v1/review/compare
/api/integration/v1/review/validate
/api/integration/v1/review/full
```

- [ ] **Step 2: Run the full test suite one final time**

Run: `cd backend && uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Final commit if any cleanup was needed, otherwise done**

```bash
git status
```
