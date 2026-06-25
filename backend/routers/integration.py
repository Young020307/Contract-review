import json
import os
import shutil
import uuid

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from database import get_connection
from models import TemplateResponse
from services.review_service import run_compare, run_validate, TemplateMismatchError
from utils import DOC_UPLOAD_DIR, decode_filename

router = APIRouter(
    prefix="/api/integration/v1",
    tags=["统一集成 API"],
)


# ══════════════════════════════════════════════════════════════════════════════
# 对外暴露
# ══════════════════════════════════════════════════════════════════════════════

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


@router.post(
    "/review",
    summary="执行合同审查",
    description=(
        "一站式审查接口。接收模板编号、文件流和审查类型，完成审查后返回 JSON 结果。\n\n"
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

    try:
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
    except TemplateMismatchError as e:
        raise HTTPException(400, str(e))

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
