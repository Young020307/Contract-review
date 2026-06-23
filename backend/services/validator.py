import re
import json


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
            actual_value = values.get(key, "")
            field_result = {
                "paragraph": pi,
                "start_char": start,
                "end_char": end,
                "field_name": rules.get("field_name", f"段落{pi}"),
                "actual_value": actual_value,
                "rule": RuleValidator._describe_rule(rules),
                "pass": True,
                "reason": ""
            }

            if rules.get("required", False) and not actual_value:
                field_result["pass"] = False
                field_result["reason"] = "必填字段为空"
                results.append(field_result)
                continue

            if not actual_value:
                results.append(field_result)
                continue

            min_chars = rules.get("min_chars", 0)
            if len(actual_value) < min_chars:
                field_result["pass"] = False
                field_result["reason"] = f"字数不足：最少{min_chars}字，实际{len(actual_value)}字"

            max_chars = rules.get("max_chars", 9999)
            if len(actual_value) > max_chars:
                field_result["pass"] = False
                field_result["reason"] = f"字数超限：最多{max_chars}字，实际{len(actual_value)}字"

            allowed = rules.get("allowed_chars", "any")
            if allowed in RuleValidator.CHAR_PATTERNS:
                pattern = RuleValidator.CHAR_PATTERNS[allowed]
                if not pattern.match(actual_value):
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
            match_field = rules.get("match_field", "")
            if not match_field or not field_result["actual_value"]:
                continue
            # Find target annotation by field_name
            target_value = None
            for a in annotations:
                if a.get("zone_type") != "fillable":
                    continue
                ar = json.loads(a["rules"]) if isinstance(a["rules"], str) else a["rules"]
                if ar and ar.get("field_name") == match_field:
                    key = f"{a['paragraph_index']}_{a.get('start_char', 0)}"
                    target_value = values.get(key, "")
                    break
            if target_value is not None and field_result["actual_value"] != target_value:
                field_result["pass"] = False
                field_result["reason"] = f"与「{match_field}」不一致"

        return {"results": results}

    @staticmethod
    def _describe_rule(rules: dict) -> str:
        parts = []
        if rules.get("required"):
            parts.append("必填")
        min_c = rules.get("min_chars", 0)
        max_c = rules.get("max_chars", 9999)
        if min_c and max_c < 9999:
            parts.append(f"{min_c}-{max_c}字")
        elif min_c:
            parts.append(f"最少{min_c}字")
        elif max_c < 9999:
            parts.append(f"最多{max_c}字")
        allowed = rules.get("allowed_chars", "any")
        if allowed != "any":
            parts.append(allowed)
        allowed_values = rules.get("allowed_values", [])
        if allowed_values:
            parts.append("可选:" + "/".join(allowed_values))
        match_field = rules.get("match_field", "")
        if match_field:
            parts.append(f"须同「{match_field}」")
        return "+".join(parts) if parts else "无规则"
