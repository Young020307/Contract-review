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


def _diff_para_segments(tpl_text: str, doc_text: str,
                        fillable_zones: list[tuple[int, int]],
                        pi: int, tpl_go: int, doc_go: int):
    """Per-paragraph diff using fixed-text anchors.

    Splits the template at fillable-zone boundaries into fixed / fillable
    segments, then locates each fixed segment in the document via positional
    search.  Fillable content is always neutral; only missing / extra fixed
    text produces violations.

    Returns (diffs, violations) — both lists of dicts in the same shape as
    the SequenceMatcher path.
    """
    diffs: list[dict] = []
    violations: list[dict] = []

    if not fillable_zones:
        # No fillable zones — whole paragraph is fixed, use simple comparison
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
        return diffs, violations

    # Build ordered segments: (is_fillable, tpl_start, tpl_end)
    segments: list[tuple[bool, int, int]] = []
    pos = 0
    for fs, fe in sorted(fillable_zones):
        fs = max(0, min(fs, len(tpl_text)))
        fe = max(fs, min(fe, len(tpl_text)))
        if pos < fs:
            segments.append((False, pos, fs))   # fixed
        if fs < fe or fs == fe:
            segments.append((True, fs, fe))     # fillable
        pos = fe
    if pos < len(tpl_text):
        segments.append((False, pos, len(tpl_text)))  # trailing fixed

    # Walk segments: locate each fixed segment in doc by positional search
    doc_pos = 0
    for is_fillable, s, e in segments:
        tpl_seg = tpl_text[s:e]
        if is_fillable:
            # Find the *next* fixed segment (if any) to bound this fillable
            # Search forward for the first fixed segment after this one
            next_fixed_text = ""
            for is_f2, s2, e2 in segments:
                if not is_f2 and s2 >= e:
                    next_fixed_text = tpl_text[s2:e2]
                    break
            if next_fixed_text:
                anchor = doc_text.find(next_fixed_text, doc_pos)
                if anchor >= 0:
                    doc_fill_end = anchor
                else:
                    doc_fill_end = doc_pos
            else:
                doc_fill_end = len(doc_text)

            doc_fill_start = doc_pos
            fill_val = doc_text[doc_fill_start:doc_fill_end] if doc_fill_end > doc_fill_start else ""
            diffs.append({
                "type": "equal",
                "template_range": [tpl_go + s, tpl_go + e],
                "doc_range": [doc_go + doc_fill_start, doc_go + doc_fill_end],
                "value": fill_val
            })
            doc_pos = doc_fill_end
        else:
            # Fixed segment — find it in doc starting from doc_pos
            idx = doc_text.find(tpl_seg, doc_pos)
            if idx == -1:
                # Fixed segment deleted
                diffs.append({
                    "type": "delete",
                    "template_range": [tpl_go + s, tpl_go + e],
                    "doc_range": [doc_go + doc_pos, doc_go + doc_pos],
                    "value": tpl_seg
                })
                violations.append({
                    "paragraph": pi,
                    "type": "delete",
                    "template_text": tpl_seg,
                    "actual_text": "",
                    "template_range": [tpl_go + s, tpl_go + e],
                    "doc_range": [doc_go + doc_pos, doc_go + doc_pos]
                })
                # Don't advance doc_pos — segment not found
            else:
                if idx > doc_pos:
                    # Extra content in doc before this fixed segment
                    extra = doc_text[doc_pos:idx]
                    diffs.append({
                        "type": "insert",
                        "template_range": [tpl_go + s, tpl_go + s],
                        "doc_range": [doc_go + doc_pos, doc_go + idx],
                        "value": extra
                    })
                    violations.append({
                        "paragraph": pi,
                        "type": "insert",
                        "template_text": "",
                        "actual_text": extra,
                        "template_range": [tpl_go + s, tpl_go + s],
                        "doc_range": [doc_go + doc_pos, doc_go + idx]
                    })
                diffs.append({
                    "type": "equal",
                    "template_range": [tpl_go + s, tpl_go + e],
                    "doc_range": [doc_go + idx, doc_go + idx + len(tpl_seg)],
                    "value": tpl_seg
                })
                doc_pos = idx + len(tpl_seg)

    # Trailing extra content in doc not covered by template
    if doc_pos < len(doc_text):
        extra = doc_text[doc_pos:]
        # Template position: last segment end, or 0 if no segments
        last_tpl_pos = segments[-1][2] if segments else 0
        diffs.append({
            "type": "insert",
            "template_range": [tpl_go + last_tpl_pos, tpl_go + last_tpl_pos],
            "doc_range": [doc_go + doc_pos, doc_go + len(doc_text)],
            "value": extra
        })
        violations.append({
            "paragraph": pi,
            "type": "insert",
            "template_text": "",
            "actual_text": extra,
            "template_range": [tpl_go + last_tpl_pos, tpl_go + last_tpl_pos],
            "doc_range": [doc_go + doc_pos, doc_go + len(doc_text)]
        })

    return diffs, violations


class DiffEngine:
    @staticmethod
    def compare_aligned(tpl_paras: list[dict], doc_paras: list[dict],
                        para_map: dict[int, int | None], inserted: list[int],
                        fillable_by_para: dict[int, list[tuple[int, int]]],
                        absorbed: dict[int, list[int]] | None = None,
                        optional_missing: set[int] | None = None) -> dict:
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

                para_diffs, para_violations = _diff_para_segments(
                    tpl_text, doc_text, para_fillable, pi, tpl_go, doc_go
                )
                diffs.extend(para_diffs)
                violations.extend(para_violations)
            else:
                if optional_missing and pi in optional_missing:
                    # Entirely-fillable non-required paragraph with no counterpart
                    # in the document — treat as omitted, not deleted
                    continue
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

        # Absorbed paragraphs: fillable content spread across extra doc paragraphs.
        # Treat as equal (no violation) — they belong to the fillable zone of their
        # parent template paragraph.
        absorbed_set: set[int] = set()
        if absorbed:
            for doc_indices in absorbed.values():
                absorbed_set.update(doc_indices)
            for doc_i in sorted(absorbed_set):
                doc_text = doc_paras[doc_i]["text"]
                doc_go = doc_start[doc_i]
                tpl_pos = _find_tpl_position_before(doc_i, para_map, tpl_start, tpl_paras)
                diffs.append({
                    "type": "equal",
                    "template_range": [tpl_pos, tpl_pos],
                    "doc_range": [doc_go, doc_go + len(doc_text)],
                    "value": doc_text
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

        return {
            "diffs": _merge_adjacent_diffs(diffs),
            "violations": _merge_adjacent_violations(violations)
        }


def _merge_adjacent_diffs(diffs: list[dict]) -> list[dict]:
    """Merge adjacent delete+insert diff entries (possibly separated by equal)
    into a single replace when their template positions are close."""
    if not diffs:
        return []
    sorted_d = sorted(diffs, key=lambda d: d["template_range"][0])
    merged: list[dict] = []
    i = 0
    while i < len(sorted_d):
        a = sorted_d[i]
        if a["type"] not in ("delete", "insert"):
            merged.append(a)
            i += 1
            continue
        # Scan forward (skip equal) to find a matching insert/delete
        found = False
        for j in range(i + 1, len(sorted_d)):
            b = sorted_d[j]
            if b["type"] == "equal":
                continue
            types = {a["type"], b["type"]}
            if types != {"delete", "insert"}:
                break
            gap = abs(a["template_range"][1] - b["template_range"][0])
            if gap > 2:
                break
            # Merge: drain intermediate entries, emit replace
            d = a if a["type"] == "delete" else b
            ins = b if b["type"] == "insert" else a
            merged.append({
                "type": "replace",
                "template_range": d["template_range"],
                "doc_range": ins["doc_range"],
                "value": ins["value"],
            })
            # Copy over any equal entries between a and b
            for k in range(i + 1, j):
                merged.append(sorted_d[k])
            i = j + 1
            found = True
            break
        if not found:
            merged.append(a)
            i += 1
    return merged


def _merge_adjacent_violations(violations: list[dict]) -> list[dict]:
    """Merge adjacent delete+insert pairs into a single replace violation.

    SequenceMatcher sometimes represents a substitution as separate delete and
    insert operations when the edit distance is small (e.g. "45" → "50").
    This pass merges them back into a single "replace" for cleaner UI display.
    """
    if not violations:
        return []
    # Sort by paragraph, then by template_range start
    sorted_v = sorted(violations, key=lambda v: (v["paragraph"], v["template_range"][0]))
    merged: list[dict] = []
    i = 0
    while i < len(sorted_v):
        a = sorted_v[i]
        if i + 1 >= len(sorted_v) or a["paragraph"] != sorted_v[i + 1]["paragraph"]:
            merged.append(a)
            i += 1
            continue
        b = sorted_v[i + 1]
        # Look for adjacent delete+insert or insert+delete in same paragraph
        types = {a["type"], b["type"]}
        if types != {"delete", "insert"}:
            merged.append(a)
            i += 1
            continue
        gap = abs(a["template_range"][1] - b["template_range"][0])
        if gap > 2:
            merged.append(a)
            i += 1
            continue
        # Merge: pick delete as template_text, insert as actual_text
        d = a if a["type"] == "delete" else b
        ins = b if b["type"] == "insert" else a
        merged.append({
            "paragraph": d["paragraph"],
            "type": "replace",
            "template_text": d["template_text"],
            "actual_text": ins["actual_text"],
            "template_range": d["template_range"],
            "doc_range": ins["doc_range"],
        })
        i += 2
    return merged


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
