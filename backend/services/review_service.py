import difflib
import json
from database import get_connection
from services.parser import DocxParser
from services.diff_engine import DiffEngine
from services.validator import RuleValidator
from utils import resolve_path


class TemplateMismatchError(Exception):
    """Raised when the uploaded document does not match the selected template."""
    pass


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


def _check_first_paragraph(tpl_paras: list[dict], doc_paras: list[dict]) -> None:
    """Raise TemplateMismatchError if the first paragraphs (titles) differ too much."""
    tpl_first = tpl_paras[0]["text"].strip() if tpl_paras else ""
    doc_first = doc_paras[0]["text"].strip() if doc_paras else ""
    if not tpl_first or not doc_first:
        return
    ratio = difflib.SequenceMatcher(None, tpl_first, doc_first).ratio()
    if ratio < 1.0:
        raise TemplateMismatchError("上传的文件与所选模板不匹配，请确认文件正确")


KEYWORDS = ["保费收入"]


def _scan_keywords(result: dict, doc_paras: list[dict],
                   mapping: dict[int, int | None]) -> None:
    """Scan document text for sensitive keywords and add to violations.

    Keyword matches are prepended to the violations list so they appear
    first in the review results. A ``keyword_matches`` list is added to
    *result* for frontend highlighting.
    """
    doc_text: str = result.get("document_text", "")
    if not doc_text:
        result["keyword_matches"] = []
        return

    # Build doc-paragraph offset map
    doc_go = 0
    doc_offsets: list[tuple[int, int, int]] = []  # (index, start, end)
    for dp in doc_paras:
        p_end = doc_go + len(dp["text"]) + 1  # +1 for \n
        doc_offsets.append((dp["index"], doc_go, p_end))
        doc_go = p_end

    # Reverse mapping: doc_idx → tpl_idx
    rev_map: dict[int, int] = {}
    for tpl_i, doc_i in mapping.items():
        if doc_i is not None:
            rev_map[doc_i] = tpl_i

    keyword_matches: list[dict] = []

    for kw in KEYWORDS:
        start = 0
        while True:
            idx = doc_text.find(kw, start)
            if idx == -1:
                break

            doc_pi = -1
            for di, ds, de in doc_offsets:
                if ds <= idx < de:
                    doc_pi = di
                    break

            tpl_pi = rev_map.get(doc_pi, 0)

            match_entry = {
                "keyword": kw,
                "paragraph": tpl_pi,
                "doc_paragraph": doc_pi,
                "doc_range": [idx, idx + len(kw)],
            }
            keyword_matches.append(match_entry)

            # Prepend to violations — highest priority
            result["violations"].insert(0, {
                "paragraph": tpl_pi,
                "type": "keyword",
                "template_text": "",
                "actual_text": kw,
                "template_range": [0, 0],
                "doc_range": [idx, idx + len(kw)],
                "keyword": kw,
            })

            start = idx + 1

    result["keyword_matches"] = keyword_matches


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
        _check_first_paragraph(template_paras, doc_paras)
        alignment = DocxParser.align_paragraphs(template_paras, doc_paras, ann_list)

        fillable_by_para = _build_fillable_by_para(ann_list)

        result = DiffEngine.compare_aligned(
            template_paras, doc_paras,
            alignment["mapping"], alignment["inserted"],
            fillable_by_para,
            absorbed=alignment.get("absorbed")
        )
        result["template_text"] = DocxParser.extract_full_text(template_path)
        result["document_text"] = DocxParser.extract_full_text(doc_path)
        result["paragraph_mapping"] = alignment["mapping"]
        result["inserted_paragraphs"] = alignment["inserted"]
        result["absorbed"] = alignment.get("absorbed", {})

        # ── Keyword scan ──
        _scan_keywords(result, doc_paras, alignment["mapping"])
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

        doc_paras_list = DocxParser.parse(doc_path)
        template_paras_list = DocxParser.parse(template_path)
        _check_first_paragraph(template_paras_list, doc_paras_list)

        values = DocxParser.extract_fillable_values(template_path, doc_path, ann_list)
        checkbox_statuses = DocxParser.detect_checkbox_status(
            template_path, doc_path, ann_list
        )
        values.update(checkbox_statuses)
        result = RuleValidator.validate(values, ann_list)

        alignment = DocxParser.align_paragraphs(template_paras_list, doc_paras_list, ann_list)
        para_map = alignment["mapping"]
        absorbed_val = alignment.get("absorbed", {})
        doc_paras = {p["index"]: p["text"] for p in doc_paras_list}
        template_paras = {p["index"]: p["text"] for p in template_paras_list}
        for r in result["results"]:
            doc_pi = para_map.get(r["paragraph"])
            if doc_pi is not None:
                text = doc_paras.get(doc_pi, "")
                extra = absorbed_val.get(r["paragraph"], [])
                if extra:
                    merged = [text] + [doc_paras[j] for j in sorted(extra) if j in doc_paras]
                    text = "\n".join(merged)
                r["paragraph_text"] = text
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
        result["absorbed"] = alignment.get("absorbed", {})
        return result
    finally:
        conn.close()
