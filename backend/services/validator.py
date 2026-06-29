import re
import json


def chinese_to_arabic(text: str) -> int:
    """Convert Chinese uppercase/standard number to Arabic integer.

    Handles patterns like 贰万元整 → 20000, 壹佰贰拾叁 → 123,
    一千二百三十四 → 1234, 零 → 0.

    Recognizes 亿 (10⁸), 万 (10⁴), 仟/千 (10³), 佰/百 (10²), 拾/十 (10)
    as positional multipliers.

    Raises ValueError if the text contains no recognizable Chinese number.
    """
    text = text.strip().rstrip("元整角分 ")

    if not text or text in ("零", "零元"):
        return 0

    DIGITS = {
        "零": 0, "〇": 0,
        "壹": 1, "一": 1,
        "贰": 2, "二": 2, "两": 2,
        "叁": 3, "三": 3,
        "肆": 4, "四": 4,
        "伍": 5, "五": 5,
        "陆": 6, "六": 6,
        "柒": 7, "七": 7,
        "捌": 8, "八": 8,
        "玖": 9, "九": 9,
    }
    UNITS = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}
    ALL_VALID = set(DIGITS.keys()) | set(UNITS.keys()) | {"亿", "万", "零"}

    # Reject input with no recognizable Chinese number characters
    if not any(ch in ALL_VALID for ch in text):
        raise ValueError(f"无法识别为中文数字: {text}")

    def _parse_sub_wan(seg: str) -> int:
        """Parse a segment that does NOT contain 万 or 亿."""
        if not seg:
            return 0
        result = 0
        current = 0
        for ch in seg:
            if ch in DIGITS:
                current = DIGITS[ch]
            elif ch in UNITS:
                multiplier = UNITS[ch]
                if current == 0:
                    # E.g. "十" alone → 10, "百" alone → 100
                    # But "一百" means 1 is before 百
                    # This handles edge cases like "十万元" → 10万
                    current = 1
                result += current * multiplier
                current = 0
            elif ch == "零":
                current = 0
            # Unknown chars are ignored (punctuation, etc.)
        result += current
        return result

    # Split by 亿 (10⁸)
    yi_val = 0
    rest = text
    if "亿" in rest:
        parts = rest.split("亿", 1)
        yi_val = _parse_sub_wan(parts[0]) * 100_000_000
        rest = parts[1]

    # Split by 万 (10⁴)
    wan_val = 0
    if "万" in rest:
        parts = rest.split("万", 1)
        wan_val = _parse_sub_wan(parts[0]) * 10_000
        rest = parts[1]

    rest_val = _parse_sub_wan(rest)
    return yi_val + wan_val + rest_val


class RuleValidator:
    CHAR_PATTERNS = {
        "chinese": re.compile(r'^[一-鿿]+$'),
        "number": re.compile(r'^\d+$'),
        "alphanumeric": re.compile(r'^[a-zA-Z0-9一-鿿]+$'),
    }

    @staticmethod
    def validate(values: dict, annotations: list[dict]) -> dict:
        """Validate extracted fillable values against annotation rules."""
        results = []
        for ann in annotations:
            if ann.get("zone_type") != "fillable":
                continue
            pi = ann["paragraph_index"]
            start = ann.get("start_char", 0)
            end = ann.get("end_char", 0)
            rules = json.loads(ann["rules"]) if isinstance(ann["rules"], str) else ann["rules"]
            if not rules:
                rules = {}

            key = f"{pi}_{start}"
            entry = values.get(key, {})
            actual_value = entry.get("value", "") if isinstance(entry, dict) else (entry or "")
            doc_start = entry.get("doc_start", start) if isinstance(entry, dict) else start
            doc_end = entry.get("doc_end", end) if isinstance(entry, dict) else end
            field_result = {
                "paragraph": pi,
                "start_char": doc_start,
                "end_char": doc_end,
                "ann_start_char": start,  # original annotation position for reliable lookup
                "field_name": rules.get("field_name", f"段落{pi}"),
                "actual_value": actual_value,
                "rule": RuleValidator._describe_rule(rules),
                "pass": True,
                "reason": ""
            }

            is_checkbox = bool(rules.get("radio_group"))

            if rules.get("required", False) and not actual_value.strip("_ "):
                field_result["pass"] = False
                field_result["reason"] = "必填字段为空"
                results.append(field_result)
                continue

            if not actual_value and not is_checkbox:
                results.append(field_result)
                continue

            if is_checkbox:
                results.append(field_result)
                continue

            min_chars = rules.get("min_chars", 0)
            if len(actual_value) < min_chars:
                field_result["pass"] = False
                field_result["reason"] = f"字数不足：最少{min_chars}字符，实际{len(actual_value)}字符"

            max_chars = rules.get("max_chars", 9999)
            if len(actual_value) > max_chars:
                field_result["pass"] = False
                field_result["reason"] = f"字数超限：最多{max_chars}字符，实际{len(actual_value)}字符"

            allowed = rules.get("allowed_chars", "any")
            if allowed in RuleValidator.CHAR_PATTERNS:
                pattern = RuleValidator.CHAR_PATTERNS[allowed]
                check_value = actual_value.replace(",", "") if allowed == "number" else actual_value
                if not pattern.match(check_value):
                    field_result["pass"] = False
                    field_result["reason"] = f"字符类型不符：要求{allowed}"

            if allowed == "regex" and rules.get("regex") and actual_value:
                if not re.match(rules["regex"], actual_value):
                    field_result["pass"] = False
                    field_result["reason"] = f"格式不符：需匹配 {rules['regex']}"

            allowed_values = rules.get("allowed_values", [])
            if allowed_values and actual_value not in allowed_values:
                field_result["pass"] = False
                field_result["reason"] = f"值不在允许范围内：{'/'.join(allowed_values)}"

            results.append(field_result)

        # Cross-field consistency check (second pass — needs all values extracted)
        for i, field_result in enumerate(results):
            ann = [a for a in annotations if a.get("zone_type") == "fillable"
                   and a["paragraph_index"] == field_result["paragraph"]
                   and a.get("start_char", 0) == field_result["start_char"]]
            if not ann:
                continue
            rules = json.loads(ann[0]["rules"]) if isinstance(ann[0]["rules"], str) else ann[0]["rules"]
            if not rules:
                rules = {}
            match_fields = rules.get("match_fields", [])
            # Backward compat: also accept old single match_field
            if not match_fields:
                old_single = rules.get("match_field", "")
                if old_single:
                    match_fields = [old_single]
            if not match_fields or not field_result["actual_value"]:
                continue
            for match_field in match_fields:
                # Find target annotation by field_name
                target_value = None
                for a in annotations:
                    if a.get("zone_type") != "fillable":
                        continue
                    ar = json.loads(a["rules"]) if isinstance(a["rules"], str) else a["rules"]
                    if ar and ar.get("field_name") == match_field:
                        key = f"{a['paragraph_index']}_{a.get('start_char', 0)}"
                        target_entry = values.get(key, {})
                        target_value = target_entry.get("value", "") if isinstance(target_entry, dict) else (target_entry or "")
                        break
                if target_value is not None and field_result["actual_value"] != target_value:
                    field_result["pass"] = False
                    field_result["reason"] = f"与「{match_field}」不一致"

        # Amount matching check (Arabic numeral ↔ Chinese uppercase)
        # Both the source and target fields must fail when they don't match.
        processed_pairs: set[tuple[int, int]] = set()  # avoid double-processing
        for i, field_result in enumerate(results):
            ann = _find_annotation(annotations, field_result)
            if not ann:
                continue
            rules = _parse_rules(ann.get("rules"))
            amount_match_field = rules.get("amount_match_field", "")
            if not amount_match_field or not field_result["actual_value"]:
                continue

            # Find the target result and its annotation
            target_result = None
            target_ann = None
            for j, r in enumerate(results):
                ta = _find_annotation(annotations, r)
                if not ta:
                    continue
                tar = _parse_rules(ta.get("rules"))
                if tar.get("field_name") == amount_match_field:
                    target_result = r
                    target_ann = ta
                    break
            if target_result is None:
                continue

            target_val = target_result.get("actual_value", "")
            if not target_val.strip("_ "):
                continue

            # Skip if we already processed this pair from the other side
            pair_key = (
                min(field_result["paragraph"], target_result["paragraph"]),
                field_result["start_char"],
                target_result["start_char"],
            )
            if pair_key in processed_pairs:
                continue
            processed_pairs.add(pair_key)

            amount_unit = int(rules.get("amount_unit", 1) or 1)

            # Build the unit label for error messages
            unit_label = {1: "元", 1000: "千元", 10000: "万元"}.get(
                amount_unit, f"×{amount_unit}"
            )

            # Parse Arabic side (strip commas from formatted numbers like 500,000)
            try:
                raw_value = field_result["actual_value"].strip().strip("_ ").replace(",", "")
                arabic_num = int(raw_value)
            except ValueError:
                field_result["pass"] = False
                field_result["reason"] = f"金额「{field_result['actual_value']}」不是有效数字"
                target_result["pass"] = False
                target_result["reason"] = f"关联的数字「{field_result['actual_value']}」无法解析为数字"
                continue

            # Parse Chinese uppercase side
            try:
                chinese_val = chinese_to_arabic(target_val)
            except Exception:
                field_result["pass"] = False
                field_result["reason"] = f"大写「{target_val}」无法解析"
                target_result["pass"] = False
                target_result["reason"] = f"大写金额「{target_val}」无法解析为数字"
                continue

            expected = arabic_num * amount_unit
            if expected != chinese_val:
                ar_name = rules.get("field_name", "金额")
                ta_name = _parse_rules(target_ann.get("rules", {})).get("field_name", "大写金额")
                field_result["pass"] = False
                field_result["reason"] = (
                    f"与「{ta_name}」不匹配：{arabic_num}{unit_label}={expected}，"
                    f"但大写为{chinese_val}（{target_val}）"
                )
                target_result["pass"] = False
                target_result["reason"] = (
                    f"与「{ar_name}」不匹配：大写{chinese_val}（{target_val}），"
                    f"但数字为{arabic_num}{unit_label}={expected}"
                )

        # Radio group mutual-exclusion check
        radio_groups: dict[str, list[dict]] = {}
        for r in results:
            ann = _find_annotation(annotations, r)
            if not ann:
                continue
            rules = _parse_rules(ann.get("rules"))
            rg = rules.get("radio_group", "")
            if not rg:
                continue
            radio_groups.setdefault(rg, []).append(r)

        for rg, group_results in radio_groups.items():
            checked_count = sum(
                1 for r in group_results
                if values.get(f"{r['paragraph']}_{r['start_char']}", {}).get("checked")
            )
            if checked_count != 1:
                for r in group_results:
                    r["pass"] = False
                    if checked_count == 0:
                        r["reason"] = f"「{rg}」未选择任何选项"
                    else:
                        r["reason"] = f"「{rg}」只能选择一个选项（当前已选{checked_count}个）"

        results.sort(key=lambda r: r["pass"])
        return {"results": results}

    @staticmethod
    def _describe_rule(rules: dict) -> str:
        if rules.get("radio_group"):
            desc = f"单选组:{rules['radio_group']}"
            deps = rules.get("dependent_paras", [])
            if deps:
                desc += f" 管辖段落:{','.join(str(p) for p in deps)}"
            return desc


        parts = []
        if rules.get("required"):
            parts.append("必填")
        min_c = rules.get("min_chars", 0)
        max_c = rules.get("max_chars", 9999)
        if min_c and max_c < 9999:
            parts.append(f"{min_c}-{max_c}字符")
        elif min_c:
            parts.append(f"最少{min_c}字符")
        elif max_c < 9999:
            parts.append(f"最多{max_c}字符")
        allowed = rules.get("allowed_chars", "any")
        if allowed != "any":
            parts.append(allowed)
        allowed_values = rules.get("allowed_values", [])
        if allowed_values:
            parts.append("可选:" + "/".join(allowed_values))
        match_fields = rules.get("match_fields", [])
        if not match_fields:
            old_single = rules.get("match_field", "")
            if old_single:
                match_fields = [old_single]
        if match_fields:
            parts.append("须同「" + "」「".join(match_fields) + "」")
        amf = rules.get("amount_match_field", "")
        if amf:
            unit_label = {1: "元", 1000: "千元", 10000: "万元"}.get(
                rules.get("amount_unit", 1), f"×{rules.get('amount_unit', 1)}"
            )
            parts.append(f"金额({unit_label})↔「{amf}」")
        return "+".join(parts) if parts else "无规则"


def _find_annotation(annotations: list[dict], field_result: dict) -> dict | None:
    # Use ann_start_char (original template position) when available;
    # fall back to start_char (doc position) for backward compatibility.
    ann_pos = field_result.get("ann_start_char", field_result.get("start_char", 0))
    for a in annotations:
        if (a.get("zone_type") == "fillable"
                and a["paragraph_index"] == field_result["paragraph"]
                and a.get("start_char", 0) == ann_pos):
            return a
    return None


def _parse_rules(rules) -> dict:
    if isinstance(rules, str):
        try:
            return json.loads(rules)
        except (json.JSONDecodeError, TypeError):
            return {}
    return rules or {}
