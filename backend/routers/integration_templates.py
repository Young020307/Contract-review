"""模板管理接口 — 上传、详情、删除、标注配置。"""

import os
import shutil
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException, Path
from database import get_connection
from models import (
    AnnotationBatch, TemplateResponse, TemplateDetailResponse,
    ParagraphInfo
)
from services.parser import DocxParser
from utils import UPLOAD_DIR, resolve_path, decode_filename

router = APIRouter(prefix="/api/integration/v1")


# ══════════════════════════════════════════════════════════════════════════════
# 模板管理
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/templates/upload",
    response_model=TemplateResponse,
    summary="上传合同模板",
    description="接收主系统上传的 .docx 模板文件，解析段落结构后入库，返回模板元信息。",
)
async def upload_template(
    file: UploadFile = File(..., description="模板文件 (.docx)")
):
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


@router.delete(
    "/templates/{template_id}",
    summary="删除模板",
    description="删除指定模板及其关联的标注、文档和审查记录。",
)
def delete_template(
    template_id: int = Path(..., description="模板 ID")
):
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


@router.get(
    "/templates/{template_id}",
    response_model=TemplateDetailResponse,
    summary="获取模板详情",
    description="返回指定模板的完整段落列表，包含下划线标注和表格单元格标记。",
)
def get_template(
    template_id: int = Path(..., description="模板 ID")
):
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


# ══════════════════════════════════════════════════════════════════════════════
# 标注管理
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/templates/{template_id}/annotations",
    summary="保存标注区域",
    description="为模板的指定段落保存固定区、可填充区和可变区的字符级标注。\n\n"
                "每次调用会**全量替换**该模板的已有标注。",
)
def save_annotations(
    template_id: int = Path(..., description="模板 ID"),
    body: AnnotationBatch = ...,
):
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


@router.get(
    "/templates/{template_id}/annotations",
    summary="获取标注区域",
    description="返回指定模板的所有段落标注，按段落索引和起始字符排序。",
)
def get_annotations(
    template_id: int = Path(..., description="模板 ID")
):
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
