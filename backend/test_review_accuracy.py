"""
验证审查系统的准确性：
1. 模板和文档的实际差异（逐段对比）
2. 审查系统的篡改比对结果是否与真实差异一致
3. 可填充区高亮是否正确（是否高亮了固定区域）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

from services.parser import DocxParser
from services.diff_engine import DiffEngine
from services.validator import RuleValidator

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 配置 ──
TPL_NAME = "5b03a5999bc2404ba1df910034a4f29d_咨询服务标准合同-调整板V4.docx"
TPL_PATH = os.path.join(BACKEND_DIR, "uploads", TPL_NAME)
DOC_PATH = os.path.join(BACKEND_DIR, "..", "docs", "咨询服务标准合同-测试.docx")

# ── 加载数据 ──
import database
database.init_db()
conn = database.get_connection()

# 获取模板信息
tpl_row = conn.execute("SELECT id FROM templates WHERE file_path LIKE ?", (f"%{TPL_NAME}%",)).fetchone()
tpl_id = tpl_row["id"] if tpl_row else None
print(f"模板 ID: {tpl_id}")

# 获取标注
annotations = conn.execute(
    "SELECT paragraph_index, start_char, end_char, zone_type, rules FROM annotations WHERE template_id = ?",
    (tpl_id,)
).fetchall()
ann_list = [dict(a) for a in annotations]
print(f"标注数量: {len(ann_list)}")
fillable_anns = [a for a in ann_list if a.get("zone_type") == "fillable"]
print(f"可填充区数量: {len(fillable_anns)}")

# 解析
tpl_paras = DocxParser.parse(TPL_PATH)
doc_paras = DocxParser.parse(DOC_PATH)
tpl_text = DocxParser.extract_full_text(TPL_PATH)
doc_text = DocxParser.extract_full_text(DOC_PATH)

print(f"\n{'='*60}")
print(f"模板: {len(tpl_paras)} 段, {len(tpl_text)} 字符")
print(f"文档: {len(doc_paras)} 段, {len(doc_text)} 字符")
print(f"段数差异: {len(doc_paras) - len(tpl_paras)}")

# ── 1. 段落对齐 ──
alignment = DocxParser.align_paragraphs(tpl_paras, doc_paras, ann_list)
para_map = alignment["mapping"]
inserted = alignment["inserted"]

print(f"\n{'='*60}")
print("段落对齐结果:")
print(f"  映射: {len(para_map)} 项")

deleted_tpl = [k for k, v in para_map.items() if v is None]
print(f"  模板被删段落 ({len(deleted_tpl)}): {deleted_tpl}")
for di in deleted_tpl:
    tpl_text_short = tpl_paras[di]["text"][:100] if di < len(tpl_paras) else "(超出)"
    print(f"    [{di}] {tpl_text_short}")

print(f"  文档新增段落 ({len(inserted)}): {inserted}")
for ii in inserted:
    doc_text_short = doc_paras[ii]["text"][:100] if ii < len(doc_paras) else "(超出)"
    print(f"    [{ii}] {doc_text_short}")

# 对齐结果摘要
print(f"\n对齐详情 (模板→文档):")
for tpl_i in sorted(para_map.keys()):
    doc_i = para_map[tpl_i]
    tpl_preview = tpl_paras[tpl_i]["text"][:60] if tpl_i < len(tpl_paras) else "?"
    if doc_i is not None:
        doc_preview = doc_paras[doc_i]["text"][:60] if doc_i < len(doc_paras) else "?"
        print(f"  T[{tpl_i}] → D[{doc_i}]  tpl='{tpl_preview}'  doc='{doc_preview}'")
    else:
        print(f"  T[{tpl_i}] → None (已删除) tpl='{tpl_preview}'")

# ── 2. 逐段真实差异 ──
print(f"\n{'='*60}")
print("逐段真实差异 (模板 vs 文档):")

differences_found = 0
for tpl_i in sorted(para_map.keys()):
    doc_i = para_map[tpl_i]
    if doc_i is None:
        differences_found += 1
        print(f"\n  [段 T{tpl_i}] 整段被删除:")
        print(f"    模板: {tpl_paras[tpl_i]['text'][:120]}")
    else:
        tpl_text_p = tpl_paras[tpl_i]["text"]
        doc_text_p = doc_paras[doc_i]["text"]
        if tpl_text_p != doc_text_p:
            differences_found += 1
            print(f"\n  [段 T{tpl_i}→D{doc_i}] 内容差异:")
            t_preview = tpl_text_p[:100] + ("..." if len(tpl_text_p) > 100 else "")
            d_preview = doc_text_p[:100] + ("..." if len(doc_text_p) > 100 else "")
            print(f"    模板: {t_preview}")
            print(f"    文档: {d_preview}")

for ii in inserted:
    differences_found += 1
    print(f"\n  [段 D{ii}] 文档新增:")
    print(f"    文档: {doc_paras[ii]['text'][:120]}")

print(f"\n真实差异总数: {differences_found} 处")

# ── 3. 可填充区值提取 ──
print(f"\n{'='*60}")
print("可填充区值提取验证:")

values = DocxParser.extract_fillable_values(TPL_PATH, DOC_PATH, ann_list)

# 按段落组织可填充区
ann_by_para = {}
for a in ann_list:
    if a.get("zone_type") != "fillable":
        continue
    pi = a["paragraph_index"]
    ann_by_para.setdefault(pi, []).append(a)

# 检查每个可填充区
extraction_issues = []
for pi, anns in sorted(ann_by_para.items()):
    doc_pi = para_map.get(pi)
    if doc_pi is None:
        tpl_preview = tpl_paras[pi]["text"][:80] if pi < len(tpl_paras) else "?"
        extraction_issues.append(f"段 T{pi} 被删除，标注仍存在: '{tpl_preview}'")
        continue

    tpl_p_text = tpl_paras[pi]["text"] if pi < len(tpl_paras) else ""
    doc_p_text = doc_paras[doc_pi]["text"] if doc_pi < len(doc_paras) else ""

    for ann in anns:
        key = f"{pi}_{ann.get('start_char', 0)}"
        entry = values.get(key, {})
        val = entry.get("value", "") if isinstance(entry, dict) else (entry or "")

        # 检查标注在模板中的位置内容
        s, e = ann.get("start_char", 0), ann.get("end_char", 0)
        tpl_placeholder = tpl_p_text[s:e] if s < len(tpl_p_text) else ""
        doc_extracted = doc_p_text[entry.get("doc_start", s):entry.get("doc_end", e)] if isinstance(entry, dict) and entry.get("doc_start") is not None else val

        if val == "" and tpl_placeholder.strip("_ "):
            # 可填充区没提取到值，但模板有这个区
            pass  # 可能是故意留空的字段

        if val:
            # 验证提取的值是否在文档正确的段落里
            if val not in doc_p_text and val.strip("_").strip() not in doc_p_text:
                extraction_issues.append(
                    f"段 T{pi}→D{doc_pi} key={key}: 提取值'{val}'不在文档段落中! "
                    f"模板占位:'{tpl_placeholder[:30]}' 文档段:'{doc_p_text[:60]}'"
                )

print(f"可填充区: {len(fillable_anns)} 个, 提取到值: {len(values)} 个")
if extraction_issues:
    print(f"\n⚠️ 发现 {len(extraction_issues)} 个问题:")
    for issue in extraction_issues:
        print(f"  - {issue}")
else:
    print("✓ 无可填充区提取问题")

# ── 4. 篡改比对结果 ──
print(f"\n{'='*60}")
print("篡改比对 (DiffEngine.compare + 填充区中立化):")

from main import _build_global_ranges, _neutralize_fillable_diffs, _is_fully_in_fillable

fillable_ranges = _build_global_ranges(TPL_PATH, ann_list)
diff_result = DiffEngine.compare(tpl_text, doc_text)
diffs = _neutralize_fillable_diffs(diff_result["diffs"], fillable_ranges)
violations = [v for v in diff_result["violations"]
              if not _is_fully_in_fillable(v, fillable_ranges)]

print(f"Diff 段数: {len(diffs)}")
print(f"  其中 equal: {sum(1 for d in diffs if d['type']=='equal')}")
print(f"  其中 insert: {sum(1 for d in diffs if d['type']=='insert')}")
print(f"  其中 delete: {sum(1 for d in diffs if d['type']=='delete')}")
print(f"  其中 replace: {sum(1 for d in diffs if d['type']=='replace')}")
print(f"违规数 (排除填充区): {len(violations)}")

print("\n违规详情:")
for vi, v in enumerate(violations):
    tr = v["template_range"]
    dr = v["doc_range"]
    t_text = v["template_text"][:60]
    a_text = v["actual_text"][:60] if v["type"] != "delete" else "(空)"
    print(f"  [{vi}] {v['type']}: tpl_range={tr} doc_range={dr}")
    print(f"       模板: '{t_text}'")
    print(f"       实际: '{a_text}'")
    # 定位到段落
    for p in tpl_paras:
        # 用模板全局偏移定位
        pass

# 用全局偏移定位违规在哪个段落
print("\n违规段落定位:")
goff = 0
para_goffs = []
for p in tpl_paras:
    para_goffs.append((p["index"], goff, goff + len(p["text"])))
    goff += len(p["text"]) + 1

for vi, v in enumerate(violations):
    tr = v["template_range"]
    # 找到模板对应段落
    tpl_pi = None
    for pi, start, end in para_goffs:
        if tr[0] >= start and tr[0] <= end:
            tpl_pi = pi
            break
    print(f"  [{vi}] type={v['type']} → 模板段 T{tpl_pi}, template_range={tr}")

# ── 5. 可填充区高亮验证 ──
print(f"\n{'='*60}")
print("可填充区高亮位置验证:")

# For each fillable zone, check that the immediately surrounding fixed text
# (between fillable zones, not the entire paragraph prefix) exists in the
# document paragraph. This avoids false positives when earlier fillable zones
# changed the template placeholder underscores to filled values.
highlight_issues = []
for pi, anns in sorted(ann_by_para.items()):
    doc_pi = para_map.get(pi)
    if doc_pi is None:
        continue

    tpl_p_text = tpl_paras[pi]["text"] if pi < len(tpl_paras) else ""
    doc_p_text = doc_paras[doc_pi]["text"] if doc_pi < len(doc_paras) else ""

    prev_end = 0
    for ann in sorted(anns, key=lambda a: a.get("start_char", 0)):
        s, e = ann.get("start_char", 0), ann.get("end_char", 0)

        # Only check fixed text between the previous fillable zone and this one
        between = tpl_p_text[prev_end:s] if s > prev_end else ""

        if between and between not in doc_p_text:
            highlight_issues.append(
                f"段 T{pi}→D{doc_pi}: 标注间固定文本'{between[:30]}'在文档段中找不到"
            )
        prev_end = e

    # Check trailing fixed text after last fillable zone
    last_end = max((a.get("end_char", 0) for a in anns), default=0)
    if last_end < len(tpl_p_text):
        trailing = tpl_p_text[last_end:]
        if trailing not in doc_p_text:
            highlight_issues.append(
                f"段 T{pi}→D{doc_pi}: 末尾固定文本'{trailing[:30]}'在文档段中找不到"
            )

if highlight_issues:
    print(f"\n⚠️ 发现 {len(highlight_issues)} 个高亮位置问题:")
    for issue in highlight_issues[:20]:
        print(f"  - {issue}")
    if len(highlight_issues) > 20:
        print(f"  ... 还有 {len(highlight_issues) - 20} 个")
else:
    print("✓ 所有可填充区前后固定文本在文档中存在")

def _find_tpl_para_for_range(tr, tpl_paras):
    """Find template paragraph index for a global template range (overlap check)."""
    goff = 0
    for p in tpl_paras:
        pend = goff + len(p["text"])
        if tr[0] <= pend and tr[1] >= goff:  # range overlaps this paragraph
            return p["index"]
        goff = pend + 1
    return None


def _tpl_para_offsets(tpl_paras):
    """Return list of (index, goff, pend) for each template paragraph."""
    result = []
    goff = 0
    for p in tpl_paras:
        pend = goff + len(p["text"])
        result.append((p["index"], goff, pend))
        goff = pend + 1
    return result


# ── 6. 前端占位符数量验证 ──
print(f"\n{'='*60}")
print("前端视角验证:")

# 前端 displayItems 逻辑：deleted_tpl 中每个 → 一个 "该条款已删除" 占位符
placeholder_count = len(deleted_tpl)
# 插入段不产生占位符（它们正常显示在文档视图中）
print(f"  左侧占位符数量: {placeholder_count}")
print(f"  右侧违规数: {len(violations)}")
print(f"  实际真实删除: {sum(1 for v in violations if v['type'] == 'delete')}")

# 验证占位符位置是否对应真正的删除（非 fillable 差异）
real_deletions = [v for v in violations if v['type'] == 'delete']
tpl_deleted_set = set(deleted_tpl)

# 检查每个 delete 违规对应的模板段落是否在 deleted 列表中
print(f"\n删除验证:")
for v in real_deletions:
    tr = v["template_range"]
    tpl_pi = None
    goff = 0
    for p in tpl_paras:
        pend = goff + len(p["text"])
        if tr[0] >= goff and tr[0] <= pend:
            tpl_pi = p["index"]
            break
        goff = pend + 1
    in_deleted = tpl_pi in tpl_deleted_set if tpl_pi is not None else False
    if in_deleted:
        print(f"  违规段 T{tpl_pi}: ✓ 整段删除（有占位符）")
    else:
        print(f"  违规段 T{tpl_pi}: ✓ 段内差异（段落已匹配，无占位符）")

# 检查是否有多余的占位符（标记为删除但实际不是删除）
_para_offsets = _tpl_para_offsets(tpl_paras)
for di in deleted_tpl:
    di_goff = next((goff for i, goff, pend in _para_offsets if i == di), None)
    di_pend = next((pend for i, goff, pend in _para_offsets if i == di), None)
    has_violation = any(
        v["template_range"][0] <= di_pend and v["template_range"][1] >= di_goff
        for v in real_deletions
    ) if di_goff is not None else False
    tpl_text_short = tpl_paras[di]["text"][:60] if di < len(tpl_paras) else "?"
    if not has_violation:
        print(f"  T{di}: ⚠ 占位符标记但无对应违规 — '{tpl_text_short}'")
    else:
        print(f"  T{di}: ✓ 占位符与违规一致 — '{tpl_text_short}'")

# ── 7. 删除段标注泄露验证 ──
# Catch the frontend bug: mapping[pi]=null → null ?? pi = pi
# Deleted paragraph annotations leak onto unrelated document paragraphs
print(f"\n删除段标注泄露检查 (mapping[pi]=null → null??pi=pi 导致泄露到 D{pi}):")
leaked = 0
for pi in deleted_tpl:
    pi_anns = [a for a in fillable_anns if a["paragraph_index"] == pi]
    if not pi_anns:
        continue
    leaked_to = pi  # the bug would map to this doc paragraph
    if leaked_to < len(doc_paras):
        field_name = ""
        for a in pi_anns:
            rules_str = a.get("rules", "{}")
            try:
                rules = json.loads(rules_str) if isinstance(rules_str, str) else rules_str
                field_name = rules.get("field_name", "") or field_name
            except Exception:
                pass
        doc_text = doc_paras[leaked_to]["text"][:60]
        tpl_text_short = tpl_paras[pi]["text"][:40] if pi < len(tpl_paras) else "?"
        leaked += len(pi_anns)
        print(f"  ⚠ T{pi}「{field_name}」→ 会误显示在 D{leaked_to}「{doc_text}」")

if leaked:
    print(f"\n  ❌ {leaked} 个标注会泄露到错误的文档段落！前端 buildFieldMap 有 null?? 回退 bug")
else:
    print(f"  ✓ 无标注泄露")

print(f"\n验证摘要:")
print(f"  段落对齐: {'✓' if len(tpl_paras) - len(deleted_tpl) + len(inserted) == len(doc_paras) else '⚠ 可能不完整'}")
print(f"  真实差异: {sum(1 for _ in real_deletions)} 处删除 + {sum(1 for v in violations if v['type']=='insert')} 处新增")
print(f"  审查违规: {len(violations)} 处")
print(f"  可填充区提取: {len(values)}/{len(fillable_anns)}")
print(f"  提取问题: {len(extraction_issues)} 个")
print(f"  高亮问题: {len(highlight_issues)} 个")
print(f"  标注泄露: {leaked} 个")
print(f"  占位符: {placeholder_count} 个 (违规 {len(violations)} 处)")

conn.close()
