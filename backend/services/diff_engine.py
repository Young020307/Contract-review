import difflib


def _is_in_para_fillable(i1: int, i2: int, para_fillable: list[tuple[int, int]]) -> bool:
    """Check if a per-paragraph range falls within fillable zones."""
    for fs, fe in para_fillable:
        if i1 == i2:
            if (fs <= i1 < fe) or (fs == fe and fs == i1):
                return True
        else:
            if fs <= i1 and i2 <= fe:
                return True
            if fs <= i1 < fe and i2 - fe <= 2:
                return True
    return False


class DiffEngine:
    @staticmethod
    def compare_aligned(tpl_paras: list[dict], doc_paras: list[dict],
                        para_map: dict[int, int | None], inserted: list[int],
                        fillable_by_para: dict[int, list[tuple[int, int]]]) -> dict:
        """Per-paragraph diff using paragraph alignment.

        Diffs each matched paragraph pair independently so that paragraph
        boundaries never split a diff segment. Fillable zones are filtered
        within each paragraph using local coordinates.

        Returns the same format as compare() with global coordinates.
        """
        # Pre-compute global character offsets for each paragraph
        tpl_start: dict[int, int] = {}
        tpl_offset = 0
        for p in tpl_paras:
            tpl_start[p["index"]] = tpl_offset
            tpl_offset += len(p["text"]) + 1  # +1 for \n

        doc_start: dict[int, int] = {}
        doc_offset = 0
        for p in doc_paras:
            doc_start[p["index"]] = doc_offset
            doc_offset += len(p["text"]) + 1

        diffs: list[dict] = []
        violations: list[dict] = []

        # Walk template paragraphs in order
        for p in tpl_paras:
            pi = p["index"]
            tpl_text = p["text"]
            tpl_go = tpl_start[pi]
            doc_i = para_map.get(pi)

            if doc_i is not None:
                doc_text = doc_paras[doc_i]["text"]
                doc_go = doc_start[doc_i]
                para_fillable = fillable_by_para.get(pi, [])

                sm = difflib.SequenceMatcher(None, tpl_text, doc_text)
                for tag, i1, i2, j1, j2 in sm.get_opcodes():
                    if tag == "equal":
                        diffs.append({
                            "type": "equal",
                            "template_range": [tpl_go + i1, tpl_go + i2],
                            "doc_range": [doc_go + j1, doc_go + j2],
                            "value": tpl_text[i1:i2]
                        })
                        continue

                    if _is_in_para_fillable(i1, i2, para_fillable):
                        # Neutralize: treat fillable-zone diffs as equal
                        diffs.append({
                            "type": "equal",
                            "template_range": [tpl_go + i1, tpl_go + i2],
                            "doc_range": [doc_go + j1, doc_go + j2],
                            "value": doc_text[j1:j2] if tag != "delete" else tpl_text[i1:i2]
                        })
                        continue

                    t_template = tpl_text[i1:i2] if tag != "insert" else ""
                    t_actual = doc_text[j1:j2] if tag != "delete" else ""

                    diffs.append({
                        "type": tag,
                        "template_range": [tpl_go + i1, tpl_go + i2],
                        "doc_range": [doc_go + j1, doc_go + j2],
                        "value": t_actual if tag in ("insert", "replace") else t_template
                    })

                    violations.append({
                        "paragraph": pi,
                        "type": tag,
                        "template_text": t_template,
                        "actual_text": t_actual,
                        "template_range": [tpl_go + i1, tpl_go + i2],
                        "doc_range": [doc_go + j1, doc_go + j2]
                    })
            else:
                # Paragraph deleted entirely
                doc_pos = _find_doc_position_after(pi, para_map, doc_start, doc_paras)
                diffs.append({
                    "type": "delete",
                    "template_range": [tpl_go, tpl_go + len(tpl_text)],
                    "doc_range": [doc_pos, doc_pos],
                    "value": tpl_text
                })
                violations.append({
                    "paragraph": pi,
                    "type": "delete",
                    "template_text": tpl_text,
                    "actual_text": "",
                    "template_range": [tpl_go, tpl_go + len(tpl_text)],
                    "doc_range": [doc_pos, doc_pos]
                })

        # Inserted paragraphs
        for doc_i in sorted(inserted):
            doc_text = doc_paras[doc_i]["text"]
            doc_go = doc_start[doc_i]
            tpl_pos = _find_tpl_position_before(doc_i, para_map, tpl_start, tpl_paras)
            diffs.append({
                "type": "insert",
                "template_range": [tpl_pos, tpl_pos],
                "doc_range": [doc_go, doc_go + len(doc_text)],
                "value": doc_text
            })
            violations.append({
                "paragraph": 0,
                "type": "insert",
                "template_text": "",
                "actual_text": doc_text,
                "template_range": [tpl_pos, tpl_pos],
                "doc_range": [doc_go, doc_go + len(doc_text)]
            })

        return {"diffs": diffs, "violations": violations}


def _find_doc_position_after(tpl_idx: int, para_map: dict, doc_start: dict,
                              doc_paras: list[dict]) -> int:
    """Find doc global position after a deleted template paragraph."""
    # Find the next matched template paragraph and use its doc paragraph start
    for pi in sorted(k for k in para_map if k > tpl_idx):
        doc_i = para_map[pi]
        if doc_i is not None:
            return doc_start[doc_i]
    # Deleted after all matched paragraphs: use end of document text
    if doc_paras:
        last = doc_paras[-1]
        return doc_start[last["index"]] + len(last["text"]) + 1
    return 0


def _find_tpl_position_before(doc_idx: int, para_map: dict, tpl_start: dict,
                               tpl_paras: list[dict]) -> int:
    """Find template global position before an inserted document paragraph."""
    # Find the previous matched template paragraph (largest doc_i < doc_idx)
    best_tpl = -1
    best_doc = -1
    for tpl_i, doc_i in para_map.items():
        if doc_i is not None and doc_i < doc_idx and doc_i > best_doc:
            best_doc = doc_i
            best_tpl = tpl_i
    if best_tpl >= 0:
        text = next((p["text"] for p in tpl_paras if p["index"] == best_tpl), "")
        return tpl_start[best_tpl] + len(text) + 1
    return 0
