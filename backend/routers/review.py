import json
from fastapi import APIRouter, HTTPException
from database import get_connection
from models import ReviewRequest
from services.review_service import run_compare, run_validate, TemplateMismatchError

router = APIRouter(prefix="/api/review", tags=["review"])


@router.post("/compare")
def review_compare(body: ReviewRequest):
    try:
        result = run_compare(body.template_id, body.document_id)
    except TemplateMismatchError as e:
        raise HTTPException(400, str(e))
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
    try:
        result = run_validate(body.template_id, body.document_id)
    except TemplateMismatchError as e:
        raise HTTPException(400, str(e))
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
