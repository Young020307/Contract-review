import difflib

class DiffEngine:
    @staticmethod
    def compare(template_text: str, doc_text: str) -> dict:
        """Compare two texts, return char-level diff segments and violation list."""
        sm = difflib.SequenceMatcher(None, template_text, doc_text)
        diffs = []
        violations = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            diff = {
                "type": tag,  # "equal", "insert", "delete", "replace"
                "template_range": [i1, i2],
                "doc_range": [j1, j2],
                "value": ""
            }
            if tag == "equal":
                diff["value"] = template_text[i1:i2]
            elif tag == "delete":
                diff["value"] = template_text[i1:i2]
            elif tag == "insert":
                diff["value"] = doc_text[j1:j2]
            elif tag == "replace":
                diff["value"] = doc_text[j1:j2]
            diffs.append(diff)

            if tag in ("delete", "insert", "replace"):
                violations.append({
                    "paragraph": 0,
                    "type": tag,
                    "template_text": template_text[i1:i2] if tag != "insert" else "",
                    "actual_text": doc_text[j1:j2] if tag != "delete" else "",
                    "template_range": [i1, i2],
                    "doc_range": [j1, j2]
                })

        return {"diffs": diffs, "violations": violations}
