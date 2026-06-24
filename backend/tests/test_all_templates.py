"""Comprehensive validation: all templates vs test documents.

Validates that:
1. Every matched paragraph pair has matching fixed-text content (not just same index)
2. Every detected violation corresponds to a real non-fillable change
3. No real non-fillable changes are missed by the diff engine
"""
import sys, os, re

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.parser import DocxParser
from services.diff_engine import DiffEngine
from difflib import SequenceMatcher
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = sqlite3.connect(os.path.join(BACKEND_DIR, "data.db"))
db.row_factory = sqlite3.Row

DOCS_DIR = os.path.join(BACKEND_DIR, "..", "docs")

test_pairs = [
    (33, "技术服务标准合同-调整版V4.docx", "技术服务标准合同-测试.docx"),
    (37, "咨询服务标准合同-调整板V4.docx", "咨询服务标准合同-测试.docx"),
    (38, "租车服务标准合同-调整版V4.docx", "租车服务标准合同-测试.docx"),
]


def build_fixed_regex(text, fills):
    """Build regex from fixed-text segments between fillable zones."""
    if not fills:
        return None
    ranges = sorted(fills, key=lambda r: r[0])
    fixed_segs = []
    pos = 0
    for s, e in ranges:
        s = max(0, min(s, len(text)))
        e = max(s, min(e, len(text)))
        if pos < s:
            fixed_segs.append(text[pos:s])
        pos = max(pos, e)
    if pos < len(text):
        fixed_segs.append(text[pos:])
    if not fixed_segs:
        return None
    total_len = sum(len(s) for s in fixed_segs)
    if total_len < 2:
        return None
    return ".*?".join(re.escape(s) for s in fixed_segs)


def validate_alignment(mapping, tpl_by_idx, doc_by_idx, fillable_by_para):
    """Check that every matched pair has matching fixed-text content.

    Returns list of true misalignments (pairs whose fixed text doesn't match).
    """
    bad = []
    for pi, dj in mapping.items():
        if dj is None:
            continue  # genuine deletion — fine
        tpl_text = tpl_by_idx.get(pi, "")
        doc_text = doc_by_idx.get(dj, "")
        fills = fillable_by_para.get(pi, [])

        pattern = build_fixed_regex(tpl_text, fills)
        if pattern and not re.search(pattern, doc_text):
            # Fixed text of template doesn't appear in matched doc paragraph
            bad.append((pi, dj, tpl_text, doc_text, pattern))
        elif not pattern:
            # No usable fixed text — check positional consistency
            # The pair should be in correct relative order (deferred paras match positionally)
            pass
    return bad


def find_real_changes(mapping, inserted, tpl_by_idx, doc_by_idx, fillable_by_para):
    """Find all non-fillable differences between template and document."""
    changes = []

    for pi, dj in mapping.items():
        tpl_text = tpl_by_idx.get(pi, "")
        if dj is None:
            changes.append(("delete", pi, None, tpl_text, ""))
            continue

        doc_text = doc_by_idx.get(dj, "")
        fills = fillable_by_para.get(pi, [])

        # Build fillable character mask on the TEMPLATE side
        mask = [False] * len(tpl_text)
        for s, e in fills:
            for i in range(max(0, s), min(e, len(tpl_text))):
                mask[i] = True

        sm = SequenceMatcher(None, tpl_text, doc_text)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            # Diff entirely in fillable zone → ignore
            if all(i >= len(mask) or mask[i] for i in range(i1, i2)):
                continue
            changes.append((tag, pi, dj, tpl_text[i1:i2], doc_text[j1:j2]))

    for dj in inserted:
        doc_text = doc_by_idx.get(dj, "")
        changes.append(("insert", None, dj, "", doc_text))

    return changes


all_pass = True

for tid, tpl_name, doc_name in test_pairs:
    print(f'\n{"=" * 70}')
    print(f"Testing: {tpl_name}  vs  {doc_name}")
    print(f"{'=' * 70}")

    tpl_row = db.execute("SELECT * FROM templates WHERE id = ?", (tid,)).fetchone()
    tpl_path = tpl_row["file_path"]
    doc_path = os.path.join(DOCS_DIR, doc_name)

    tpl_paras = DocxParser.parse(tpl_path)
    doc_paras = DocxParser.parse(doc_path)

    ann_rows = db.execute(
        "SELECT * FROM annotations WHERE template_id = ? ORDER BY paragraph_index, start_char",
        (tid,),
    ).fetchall()
    annotations = [
        {
            "paragraph_index": a["paragraph_index"],
            "start_char": a["start_char"],
            "end_char": a["end_char"],
            "zone_type": a["zone_type"],
        }
        for a in ann_rows
    ]

    fillable_by_para = {}
    for a in annotations:
        if a["zone_type"] == "fillable":
            fillable_by_para.setdefault(a["paragraph_index"], []).append(
                (a["start_char"], a["end_char"])
            )

    tpl_by_idx = {p["index"]: p["text"] for p in tpl_paras}
    doc_by_idx = {p["index"]: p["text"] for p in doc_paras}

    # ── Alignment ──
    align_result = DocxParser.align_paragraphs(tpl_paras, doc_paras, annotations)
    mapping = align_result["mapping"]
    inserted = align_result["inserted"]

    # ── Validate alignment using content, not indices ──
    true_misalignments = validate_alignment(
        mapping, tpl_by_idx, doc_by_idx, fillable_by_para
    )

    # ── Diff ──
    diff_result = DiffEngine.compare_aligned(
        tpl_paras, doc_paras, mapping, inserted, fillable_by_para
    )
    violations = diff_result.get("violations", [])

    # ── Find real non-fillable changes ──
    real_changes = find_real_changes(
        mapping, inserted, tpl_by_idx, doc_by_idx, fillable_by_para
    )

    # ── Match violations to real changes ──
    violation_matched = [False] * len(violations)
    change_matched = [False] * len(real_changes)

    for vi, v in enumerate(violations):
        v_para = v.get("paragraph")
        v_type = v.get("type")
        v_tpl = (v.get("template_text") or "").strip()
        v_actual = (v.get("actual_text") or "").strip()

        for ci, (c_type, c_pi, c_dj, c_tpl, c_doc) in enumerate(real_changes):
            if change_matched[ci]:
                continue
            if v_type != c_type:
                continue
            if v_type == "delete":
                if v_para == c_pi and (v_tpl in c_tpl or c_tpl in v_tpl):
                    violation_matched[vi] = True
                    change_matched[ci] = True
                    break
            elif v_type == "insert":
                if v_actual in c_doc or c_doc in v_actual:
                    violation_matched[vi] = True
                    change_matched[ci] = True
                    break
            elif v_type == "replace":
                if v_para == c_pi:
                    violation_matched[vi] = True
                    change_matched[ci] = True
                    break

    unmatched_violations = [i for i, m in enumerate(violation_matched) if not m]
    unmatched_changes = [i for i, m in enumerate(change_matched) if not m]

    # ── Report ──
    n_deleted = sum(1 for v in mapping.values() if v is None)
    print(f"  Paragraphs: tpl={len(tpl_paras)}, doc={len(doc_paras)}")
    print(f"  Alignment: {len(mapping)} mapped, {n_deleted} deleted, {len(inserted)} inserted")
    print(f"  True misalignments (content mismatch): {len(true_misalignments)}")
    print(f"  Real non-fillable changes: {len(real_changes)}")
    print(f"  Detected violations: {len(violations)}")

    issues = []

    if true_misalignments:
        issues.append(f"{len(true_misalignments)} content mismatches in alignment")
        for pi, dj, tpl_text, doc_text, pattern in true_misalignments[:5]:
            print(f"    T[{pi}] -> D[{dj}]")
            print(f"      tpl:  \"{tpl_text[:100]}\"")
            print(f"      doc:  \"{doc_text[:100]}\"")
            print(f"      regex: {pattern[:100]}")

    if unmatched_violations:
        issues.append(f"{len(unmatched_violations)} false positive violations")
        for i in unmatched_violations:
            v = violations[i]
            print(f"    FALSE+: P{v.get('paragraph')}: {v.get('type')}")
            print(f"      tpl=\"{(v.get('template_text') or '')[:80]}\"")
            print(f"      actual=\"{(v.get('actual_text') or '')[:80]}\"")

    if unmatched_changes:
        issues.append(f"{len(unmatched_changes)} missed real changes")
        for i in unmatched_changes[:10]:
            c_type, c_pi, c_dj, c_tpl, c_doc = real_changes[i]
            print(f"    MISSED: {c_type} P{c_pi}")
            print(f"      tpl=\"{(c_tpl or '')[:80]}\"")
            print(f"      doc=\"{(c_doc or '')[:80]}\"")

    if issues:
        print(f"  ** FAIL: {'; '.join(issues)}")
        all_pass = False
    else:
        print(f"  ** PASS **")

print()
print("=" * 70)
if all_pass:
    print("ALL TEMPLATES PASS")
else:
    print("SOME TEMPLATES HAVE ISSUES — see details above")
