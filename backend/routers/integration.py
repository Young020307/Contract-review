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
