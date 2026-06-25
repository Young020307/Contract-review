import json
import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Path, Query
from fastapi.responses import FileResponse
from database import get_connection
from models import (
    AnnotationBatch, TemplateResponse, TemplateDetailResponse,
    DocumentResponse, ParagraphInfo
)
from services.parser import DocxParser
from services.review_service import run_compare, run_validate
from utils import UPLOAD_DIR, DOC_UPLOAD_DIR, resolve_path, decode_filename

router = APIRouter(
    prefix="/api/integration/v1",
    tags=["统一集成 API"],
)


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


@router.get(
    "/templates",
    response_model=list[TemplateResponse],
    summary="获取模板列表",
    description="返回所有已注册的合同模板，按 ID 排序，供大系统下拉选择。",
)
def list_templates():
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


# ══════════════════════════════════════════════════════════════════════════════
# 文档管理
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/documents/proxy-template/{template_id}",
    summary="代理下载模板文件",
    description="以原始 .docx 格式返回模板文件，供主系统直接下载。",
)
async def proxy_template_file(
    template_id: int = Path(..., description="模板 ID")
):
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


@router.post(
    "/documents/upload",
    response_model=DocumentResponse,
    summary="上传待审文档",
    description="上传待审查的 .docx 文档并关联到指定模板，解析段落结构后入库。",
)
async def upload_document(
    file: UploadFile = File(..., description="待审文档 (.docx)"),
    template_id: int = Query(..., description="关联的模板 ID"),
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


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="获取文档详情",
    description="返回指定文档的完整段落列表和关联的模板 ID。",
)
def get_document(
    document_id: int = Path(..., description="文档 ID")
):
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


# ══════════════════════════════════════════════════════════════════════════════
# 统一审查
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/review",
    summary="执行合同审查",
    description=(
        "大系统一站式审查接口。接收模板编号、文件流和审查类型，完成审查后返回 JSON 结果。\n\n"
        "**审查类型：**\n"
        "- `1` — 段落比对：逐段 Diff，返回差异和违规项\n"
        "- `2` — 规则校验：提取填充值，按标注规则逐字段校验\n"
        "- `3` — 完整审查：比对 + 校验，聚合返回\n\n"
        "**流程：** 上传文档 → 入库 → 审查 → 记录任务 → 返回结果"
    ),
)
async def review(
    template_id: int = Form(..., description="模板 ID"),
    review_type: int = Form(..., description="审查类型: 1=段落比对, 2=规则校验, 3=完整审查"),
    file: UploadFile = File(..., description="待审文档 (.docx)"),
):
    if review_type not in (1, 2, 3):
        raise HTTPException(400, "review_type 必须为 1（比对）、2（校验）或 3（完整审查）")

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

    # Save uploaded document
    filename = decode_filename(file.filename)
    safe_name = f"doc_{uuid.uuid4().hex}_{filename}"
    os.makedirs(DOC_UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOC_UPLOAD_DIR, safe_name)
    rel_path = os.path.join("temp", safe_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Create document record
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

    # Run review based on type
    result: dict = {"document_id": document_id}
    task_type_map = {1: "compare", 2: "validate", 3: "both"}

    if review_type in (1, 3):
        compare_result = run_compare(template_id, document_id)
        if compare_result is None:
            raise HTTPException(500, "比对失败")
        result["compare"] = compare_result

    if review_type in (2, 3):
        validate_result = run_validate(template_id, document_id)
        if validate_result is None:
            raise HTTPException(500, "校验失败")
        result["validate"] = validate_result

    # Save review task record
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) "
            "VALUES (?, ?, ?, ?)",
            (template_id, document_id, task_type_map[review_type],
             json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
    finally:
        conn.close()

    return result
