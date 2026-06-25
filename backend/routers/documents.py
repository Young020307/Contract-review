import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from database import get_connection
from models import DocumentResponse, ParagraphInfo
from services.parser import DocxParser
from utils import DOC_UPLOAD_DIR, resolve_path, decode_filename

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/proxy-template/{template_id}")
async def proxy_template_file(template_id: int):
    conn = get_connection()
    row = conn.execute("SELECT file_path FROM templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404)
    return FileResponse(resolve_path(row["file_path"]), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...), template_id: int = Query(...)):
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
        id=doc_id,
        name=filename,
        template_id=template_id,
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"], underline_ranges=p.get("underline_ranges", []), is_table_cell=p.get("is_table_cell", False)) for p in paragraphs],
        uploaded_at=""
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, template_id, file_path, uploaded_at FROM documents WHERE id = ?",
            (document_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "文件不存在")
        paragraphs = DocxParser.parse(resolve_path(row["file_path"]))
    finally:
        conn.close()
    return DocumentResponse(
        id=row["id"],
        name=row["name"],
        template_id=row["template_id"],
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"], underline_ranges=p.get("underline_ranges", []), is_table_cell=p.get("is_table_cell", False)) for p in paragraphs],
        uploaded_at=row["uploaded_at"] or ""
    )
