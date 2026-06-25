import json
from fastapi import APIRouter, HTTPException
from database import get_connection
from models import ReviewRequest
from services.parser import DocxParser
from services.diff_engine import DiffEngine
from services.validator import RuleValidator
from utils import resolve_path

router = APIRouter(prefix="/api/review", tags=["review"])


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


@router.post("/compare")
def review_compare(body: ReviewRequest):
    conn = get_connection()
    try:
        template = conn.execute("SELECT id, file_path FROM templates WHERE id = ?", (body.template_id,)).fetchone()
        document = conn.execute("SELECT id, file_path FROM documents WHERE id = ?", (body.document_id,)).fetchone()
        if not template or not document:
            raise HTTPException(404, "模板或文件不存在")
        template_path = resolve_path(template["file_path"])
        doc_path = resolve_path(document["file_path"])

        annotations = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type FROM annotations WHERE template_id = ?",
            (body.template_id,)
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

        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) VALUES (?, ?, 'compare', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
        return result
    finally:
        conn.close()


@router.post("/validate")
def review_validate(body: ReviewRequest):
    conn = get_connection()
    try:
        template = conn.execute("SELECT id, file_path FROM templates WHERE id = ?", (body.template_id,)).fetchone()
        document = conn.execute("SELECT id, file_path FROM documents WHERE id = ?", (body.document_id,)).fetchone()
        if not template or not document:
            raise HTTPException(404, "模板或文件不存在")
        template_path = resolve_path(template["file_path"])
        doc_path = resolve_path(document["file_path"])

        annotations = conn.execute(
            "SELECT paragraph_index, start_char, end_char, zone_type, rules FROM annotations WHERE template_id = ?",
            (body.template_id,)
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

        result["document_paragraphs"] = [{"index": p["index"], "text": p["text"]} for p in doc_paras_list]
        result["template_paragraphs"] = [{"index": p["index"], "text": p["text"]} for p in template_paras_list]

        result["paragraph_mapping"] = alignment["mapping"]
        result["inserted_paragraphs"] = alignment["inserted"]

        conn.execute(
            "INSERT INTO review_tasks (template_id, document_id, task_type, result) VALUES (?, ?, 'validate', ?)",
            (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
        )
        conn.commit()
        return result
    finally:
        conn.close()
