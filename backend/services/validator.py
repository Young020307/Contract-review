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
        """Validate extracted fillable values against annotation rules.
        values: {paragraph_index: "actual text"}
        annotations: [{paragraph_index, zone_type, rules}, ...]
        """
        results = []
        for ann in annotations:
            pi = ann["paragraph_index"]
            rules = json.loads(ann["rules"]) if isinstance(ann["rules"], str) else ann["rules"]
            if not rules:
                continue

            actual_value = values.get(pi, "")
            field_result = {
                "paragraph": pi,
                "field_name": rules.get("field_name", f"段落{pi}"),
                "actual_value": actual_value,
                "rule": RuleValidator._describe_rule(rules),
                "pass": True,
                "reason": ""
            }

            # Required check
            if rules.get("required", False) and not actual_value:
                field_result["pass"] = False
                field_result["reason"] = "必填字段为空"
                results.append(field_result)
                continue

            if not actual_value:
                results.append(field_result)
                continue

            # Min chars
            min_chars = rules.get("min_chars", 0)
            if len(actual_value) < min_chars:
                field_result["pass"] = False
                field_result["reason"] = f"字数不足：最少{min_chars}字，实际{len(actual_value)}字"

            # Max chars
            max_chars = rules.get("max_chars", 9999)
            if len(actual_value) > max_chars:
                field_result["pass"] = False
                field_result["reason"] = f"字数超限：最多{max_chars}字，实际{len(actual_value)}字"

            # Allowed chars
            allowed = rules.get("allowed_chars", "any")
            if allowed in RuleValidator.CHAR_PATTERNS:
                pattern = RuleValidator.CHAR_PATTERNS[allowed]
                if not pattern.match(actual_value):
                    field_result["pass"] = False
                    field_result["reason"] = f"字符类型不符：要求{allowed}"

            # Custom regex
            if allowed == "regex" and rules.get("regex"):
                if not re.match(rules["regex"], actual_value):
                    field_result["pass"] = False
                    field_result["reason"] = f"格式不符：需匹配 {rules['regex']}"

            results.append(field_result)

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
        return "+".join(parts) if parts else "无规则"
