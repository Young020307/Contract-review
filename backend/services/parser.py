from docx import Document


class DocxParser:
    @staticmethod
    def parse(file_path: str) -> list[dict]:
        doc = Document(file_path)
        paragraphs = []
        for i, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if text:  # skip empty paragraphs
                paragraphs.append({"index": i, "text": text})
        return paragraphs

    @staticmethod
    def extract_full_text(file_path: str) -> str:
        """Extract full paragraph text (all zones), joined by newlines."""
        doc = Document(file_path)
        texts = []
        for para in doc.paragraphs:
            text = para.text
            if text.strip():
                texts.append(text.strip())
        return "\n".join(texts)

    @staticmethod
    def extract_fixed_text(file_path: str, annotations: list[dict]) -> str:
        """Extract text from fixed zones, excluding fillable ranges."""
        doc = Document(file_path)
        ann_by_para = {}
        for a in annotations:
            ann_by_para.setdefault(a["paragraph_index"], []).append(a)

        texts = []
        for pi, para in enumerate(doc.paragraphs):
            text = para.text
            if not text.strip():
                continue
            if pi in ann_by_para:
                fillable_ranges = sorted(
                    [(a["start_char"], a["end_char"]) for a in ann_by_para[pi]
                     if a.get("zone_type") == "fillable"]
                )
                if not fillable_ranges:
                    texts.append(text.strip())
                    continue
                fixed_parts = []
                pos = 0
                for start, end in fillable_ranges:
                    if pos < start:
                        fixed_parts.append(text[pos:start])
                    pos = max(pos, end)
                if pos < len(text):
                    fixed_parts.append(text[pos:])
                result = "".join(fixed_parts).strip()
                if result:
                    texts.append(result)
            else:
                texts.append(text.strip())
        return "\n".join(texts)

    @staticmethod
    def extract_fillable_values(file_path: str, annotations: list[dict]) -> dict:
        """Extract text from fillable character ranges. Key: '{pi}_{start_char}'."""
        doc = Document(file_path)
        values = {}
        for ann in annotations:
            if ann.get("zone_type") != "fillable":
                continue
            pi = ann["paragraph_index"]
            para = doc.paragraphs[pi]
            start = ann.get("start_char", 0)
            end = ann.get("end_char", len(para.text))
            values[f"{pi}_{start}"] = para.text[start:end].replace("_", "").strip()
        return values
