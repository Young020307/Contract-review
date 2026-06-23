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

app = FastAPI(title="格式合同智能审查系统 Demo")

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
            paragraphs=[ParagraphInfo(index=p["index"], text=p["text"]) for p in paragraphs],
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
                "INSERT INTO annotations (template_id, paragraph_index, zone_type, rules) VALUES (?, ?, ?, ?)",
                (template_id, ann.paragraph_index, ann.zone_type, rules_json)
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
            "SELECT paragraph_index, zone_type, rules FROM annotations WHERE template_id = ? ORDER BY paragraph_index",
            (template_id,)
        ).fetchall()
        return [
            {
                "paragraph_index": r["paragraph_index"],
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
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"]) for p in paragraphs],
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
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"]) for p in paragraphs],
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

        # Get fixed paragraph indices from annotations
        annotations = conn.execute(
            "SELECT paragraph_index FROM annotations WHERE template_id = ? AND zone_type = 'fixed'",
            (body.template_id,)
        ).fetchall()
        fixed_indices = {a["paragraph_index"] for a in annotations}

        template_text = DocxParser.extract_fixed_text(template["file_path"], fixed_indices)
        doc_text = DocxParser.extract_fixed_text(document["file_path"], fixed_indices)

        result = DiffEngine.compare(template_text, doc_text)
        result["template_text"] = template_text
        result["document_text"] = doc_text

        # Save review task
        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) VALUES (?, ?, 'compare', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
        return result
    finally:
        conn.close()


@app.post("/api/review/validate")
def review_validate(body: ReviewRequest):
    conn = get_connection()
    try:
        template = conn.execute("SELECT id, file_path FROM templates WHERE id = ?", (body.template_id,)).fetchone()
        document = conn.execute("SELECT id, file_path FROM documents WHERE id = ?", (body.document_id,)).fetchone()
        if not template or not document:
            raise HTTPException(404, "模板或文件不存在")

        annotations = conn.execute(
            "SELECT paragraph_index, zone_type, rules FROM annotations WHERE template_id = ? AND zone_type = 'fillable'",
            (body.template_id,)
        ).fetchall()
        fillable_indices = {a["paragraph_index"] for a in annotations}

        values = DocxParser.extract_fillable_values(document["file_path"], fillable_indices)

        ann_list = [{"paragraph_index": a["paragraph_index"], "rules": a["rules"]} for a in annotations]
        result = RuleValidator.validate(values, ann_list)

        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) VALUES (?, ?, 'validate', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
        return result
    finally:
        conn.close()
