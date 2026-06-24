import json
import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from database import init_db, get_connection
from models import (
    AnnotationBatch, AnnotationItem, ValidationRule,
    TemplateResponse, TemplateDetailResponse, ParagraphInfo,
    DocumentResponse, ReviewRequest
)
from services.parser import DocxParser
from services.diff_engine import DiffEngine
from services.validator import RuleValidator


def _decode_filename(name: str) -> str:
    """Fix filenames sent with incorrect encoding by the HTTP client.

    Some clients (curl, certain browsers) send non-ASCII filenames as raw
    bytes without proper RFC 5987 encoding. FastAPI/Starlette interprets
    these bytes as latin-1 characters, producing garbled text.
    """
    try:
        raw = name.encode("latin-1")
    except UnicodeEncodeError:
        return name
    # Try GBK first (common on Windows/Chinese systems), then UTF-8
    for enc in ("gbk", "utf-8"):
        try:
            decoded = raw.decode(enc)
            if decoded != name:
                return decoded
        except UnicodeDecodeError:
            continue
    return name
from services.validator import RuleValidator

app = FastAPI(title="合同智能审查系统 Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/api/health")
def health():
    return {"status": "ok"}

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/api/templates/upload", response_model=TemplateResponse)
async def upload_template(file: UploadFile = File(...)):
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "只支持 .docx 文件")
    filename = _decode_filename(file.filename)
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    conn = get_connection()
    try:
        paragraphs = DocxParser.parse(file_path)
        cur = conn.execute(
            "INSERT INTO templates (name, file_path, paragraph_count) VALUES (?, ?, ?)",
            (filename, file_path, len(paragraphs))
        )
        conn.commit()
        template_id = cur.lastrowid
    finally:
        conn.close()
    return TemplateResponse(
        id=template_id,
        name=filename,
        paragraph_count=len(paragraphs),
        created_at=""
    )


@app.get("/api/templates", response_model=list[TemplateResponse])
def list_templates():
    conn = get_connection()
    rows = conn.execute("SELECT id, name, paragraph_count, created_at FROM templates ORDER BY id").fetchall()
    conn.close()
    return [TemplateResponse(id=r["id"], name=r["name"], paragraph_count=r["paragraph_count"], created_at=r["created_at"] or "") for r in rows]


@app.delete("/api/templates/{template_id}")
def delete_template(template_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, file_path FROM templates WHERE id = ?", (template_id,)).fetchone()
        if not row:
            raise HTTPException(404, "模板不存在")
        # Delete related records first (FKs without CASCADE)
        conn.execute("DELETE FROM review_tasks WHERE template_id = ?", (template_id,))
        conn.execute("DELETE FROM documents WHERE template_id = ?", (template_id,))
        # Annotations have ON DELETE CASCADE, but delete explicitly for clarity
        conn.execute("DELETE FROM annotations WHERE template_id = ?", (template_id,))
        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        conn.commit()
        # Remove uploaded file
        if os.path.exists(row["file_path"]):
            os.remove(row["file_path"])
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/templates/{template_id}", response_model=TemplateDetailResponse)
def get_template(template_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, name, file_path, created_at FROM templates WHERE id = ?", (template_id,)).fetchone()
        if not row:
            raise HTTPException(404, "模板不存在")
        paragraphs = DocxParser.parse(row["file_path"])
        return TemplateDetailResponse(
            id=row["id"],
            name=row["name"],
            paragraphs=[ParagraphInfo(index=p["index"], text=p["text"], underline_ranges=p.get("underline_ranges", []), is_table_cell=p.get("is_table_cell", False)) for p in paragraphs],
            created_at=row["created_at"] or ""
        )
    finally:
        conn.close()


@app.post("/api/templates/{template_id}/annotations")
def save_annotations(template_id: int, body: AnnotationBatch):
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM annotations WHERE template_id = ?", (template_id,))
        for ann in body.annotations:
            rules_json = "{}"
            if ann.zone_type == "fillable" and ann.rules:
                rules_json = ann.rules.model_dump_json()
            conn.execute(
                "INSERT INTO annotations (template_id, paragraph_index, start_char, end_char, zone_type, rules) VALUES (?, ?, ?, ?, ?, ?)",
                (template_id, ann.paragraph_index, ann.start_char, ann.end_char, ann.zone_type, rules_json)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"ok": True, "count": len(body.annotations)}


@app.get("/api/templates/{template_id}/annotations")
def get_annotations(template_id: int):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type, rules FROM annotations WHERE template_id = ? ORDER BY paragraph_index, start_char",
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


@app.get("/api/documents/proxy-template/{template_id}")
async def proxy_template_file(template_id: int):
    conn = get_connection()
    row = conn.execute("SELECT file_path FROM templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404)
    return FileResponse(row["file_path"], media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.post("/api/documents/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...), template_id: int = Query(...)):
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "只支持 .docx 文件")
    filename = _decode_filename(file.filename)
    safe_name = f"doc_{uuid.uuid4().hex}_{filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    conn = get_connection()
    try:
        paragraphs = DocxParser.parse(file_path)
        cur = conn.execute(
            "INSERT INTO documents (template_id, name, file_path) VALUES (?, ?, ?)",
            (template_id, filename, file_path)
        )
        conn.commit()
        doc_id = cur.lastrowid
    finally:
        conn.close()
    return DocumentResponse(
        id=doc_id,
        name=filename,
        template_id=template_id,
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"], underline_ranges=p.get("underline_ranges", []), is_table_cell=p.get("is_table_cell", False)) for p in paragraphs],
        uploaded_at=""
    )


@app.get("/api/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, template_id, file_path, uploaded_at FROM documents WHERE id = ?",
            (document_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "文件不存在")
        paragraphs = DocxParser.parse(row["file_path"])
    finally:
        conn.close()
    return DocumentResponse(
        id=row["id"],
        name=row["name"],
        template_id=row["template_id"],
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"], underline_ranges=p.get("underline_ranges", []), is_table_cell=p.get("is_table_cell", False)) for p in paragraphs],
        uploaded_at=row["uploaded_at"] or ""
    )


@app.post("/api/review/compare")
def review_compare(body: ReviewRequest):
    conn = get_connection()
    try:
        template = conn.execute("SELECT id, file_path FROM templates WHERE id = ?", (body.template_id,)).fetchone()
        document = conn.execute("SELECT id, file_path FROM documents WHERE id = ?", (body.document_id,)).fetchone()
        if not template or not document:
            raise HTTPException(404, "模板或文件不存在")

        annotations = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type FROM annotations WHERE template_id = ?",
            (body.template_id,)
        ).fetchall()
        ann_list = [dict(a) for a in annotations]

        template_text = DocxParser.extract_full_text(template["file_path"])
        doc_text = DocxParser.extract_full_text(document["file_path"])

        # Build global fillable zone ranges (in concatenated full text)
        fillable_ranges = _build_global_ranges(template["file_path"], ann_list)

        result = DiffEngine.compare(template_text, doc_text)
        result["template_text"] = template_text
        result["document_text"] = doc_text

        # Neutralize fillable zone diffs to "equal" (they are expected changes)
        result["diffs"] = _neutralize_fillable_diffs(result["diffs"], fillable_ranges)

        # Filter violations: exclude diffs that fall entirely within fillable zones
        result["violations"] = [
            v for v in result["violations"]
            if not _is_fully_in_fillable(v, fillable_ranges)
        ]

        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) VALUES (?, ?, 'compare', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
        return result
    finally:
        conn.close()


def _build_global_ranges(file_path: str, ann_list: list[dict]) -> list[tuple[int, int]]:
    """Compute global character ranges for fillable zones in concatenated full text."""
    paras = DocxParser.parse(file_path)
    offset = 0
    ranges = []
    for p in paras:
        text = p["text"]
        for a in ann_list:
            if a["paragraph_index"] == p["index"] and a.get("zone_type") == "fillable":
                start = offset + a["start_char"]
                end = offset + a["end_char"]
                ranges.append((start, end))
        offset += len(text) + 1  # +1 for the \n separator
    return ranges


def _is_in_fillable(i1: int, i2: int, fillable_ranges: list[tuple[int, int]]) -> bool:
    """Check if a template range falls within fillable zones (with small boundary fuzz)."""
    for fs, fe in fillable_ranges:
        if i1 == i2:
            # Insert: inside non-zero-width zone, or exactly at zero-width marker
            if (fs <= i1 < fe) or (fs == fe and fs == i1):
                return True
        else:
            # Delete/replace: fully within zone, or starts within zone and overhangs ≤ 2 chars
            # (handles trailing punctuation like "。" that belongs to the fillable content)
            if fs <= i1 and i2 <= fe:
                return True
            if fs <= i1 < fe and i2 - fe <= 2:
                return True
    return False


def _is_fully_in_fillable(violation: dict, fillable_ranges: list[tuple[int, int]]) -> bool:
    tr = violation.get("template_range", [0, 0])
    return _is_in_fillable(tr[0], tr[1], fillable_ranges)


def _neutralize_fillable_diffs(diffs: list[dict], fillable_ranges: list[tuple[int, int]]) -> list[dict]:
    """Change fillable zone diffs to 'equal' so the inline document view doesn't highlight expected changes."""
    for d in diffs:
        if d["type"] == "equal":
            continue
        tr = d.get("template_range", [0, 0])
        if _is_in_fillable(tr[0], tr[1], fillable_ranges):
            d["type"] = "equal"
    return diffs


def _find_checkbox_annotation(ann_list: list[dict], field_result: dict) -> dict | None:
    for a in ann_list:
        if (a.get("zone_type") == "fillable"
                and a["paragraph_index"] == field_result.get("paragraph")
                and a.get("start_char", 0) == field_result.get("start_char", 0)):
            return a
    return None


def _parse_annotation_rules(rules) -> dict:
    if isinstance(rules, str):
        try:
            return json.loads(rules)
        except (json.JSONDecodeError, TypeError):
            return {}
    return rules or {}


@app.post("/api/review/validate")
def review_validate(body: ReviewRequest):
    conn = get_connection()
    try:
        template = conn.execute("SELECT id, file_path FROM templates WHERE id = ?", (body.template_id,)).fetchone()
        document = conn.execute("SELECT id, file_path FROM documents WHERE id = ?", (body.document_id,)).fetchone()
        if not template or not document:
            raise HTTPException(404, "模板或文件不存在")

        annotations = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type, rules FROM annotations WHERE template_id = ?",
            (body.template_id,)
        ).fetchall()
        ann_list = [dict(a) for a in annotations]

        values = DocxParser.extract_fillable_values(template["file_path"], document["file_path"], ann_list)
        checkbox_statuses = DocxParser.detect_checkbox_status(
            template["file_path"], document["file_path"], ann_list
        )
        values.update(checkbox_statuses)
        result = RuleValidator.validate(values, ann_list)

        # Attach full paragraph text to each result for context display
        doc_paras_list = DocxParser.parse(document["file_path"])
        template_paras_list = DocxParser.parse(template["file_path"])
        doc_paras = {p["index"]: p["text"] for p in doc_paras_list}
        template_paras = {p["index"]: p["text"] for p in template_paras_list}
        for r in result["results"]:
            r["paragraph_text"] = doc_paras.get(r["paragraph"], "")
            r["template_paragraph_text"] = template_paras.get(r["paragraph"], "")

        # Checkbox-dependent sibling check: within a paragraph that has a
        # checkbox, sibling fillable zones must be filled iff the box is ☑.
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
            # Find annotation for this result (match by paragraph and annotation pos)
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

        result["results"].sort(key=lambda r: r["pass"])

        # Include ALL document and template paragraphs for full-text display
        result["document_paragraphs"] = [{"index": p["index"], "text": p["text"]} for p in doc_paras_list]
        result["template_paragraphs"] = [{"index": p["index"], "text": p["text"]} for p in template_paras_list]

        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) VALUES (?, ?, 'validate', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
        return result
    finally:
        conn.close()
