import re
from docx import Document


class DocxParser:
    @staticmethod
    def parse(file_path: str) -> list[dict]:
        doc = Document(file_path)
        paragraphs = []
        for i, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if text:  # skip empty paragraphs
                underline_ranges = []
                pos = 0
                for run in para.runs:
                    run_len = len(run.text)
                    if run_len == 0:
                        continue
                    if run.font.underline:
                        underline_ranges.append([pos, pos + run_len])
                    pos += run_len
                paragraphs.append({
                    "index": i,
                    "text": text,
                    "underline_ranges": underline_ranges
                })
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
    def extract_fillable_values(template_file_path: str, doc_file_path: str, annotations: list[dict]) -> dict:
        """Extract fillable values using regex context anchors.

        Builds a regex per paragraph from template fixed-text segments surrounding
        the fillable zones, then extracts variable-length content from the filled
        document. Falls back to character-slice on regex mismatch.

        Returns dict keyed by '{pi}_{start_char}' with shape:
            {"value": str, "doc_start": int, "doc_end": int}
        """
        template_doc = Document(template_file_path)
        doc_doc = Document(doc_file_path)
        values = {}

        ann_by_para: dict[int, list[dict]] = {}
        for ann in annotations:
            if ann.get("zone_type") != "fillable":
                continue
            pi = ann["paragraph_index"]
            ann_by_para.setdefault(pi, []).append(ann)

        for pi, anns in ann_by_para.items():
            if pi >= len(template_doc.paragraphs) or pi >= len(doc_doc.paragraphs):
                continue

            tpl_text = template_doc.paragraphs[pi].text.strip()
            doc_text = doc_doc.paragraphs[pi].text.strip()
            if not tpl_text:
                continue

            anns_sorted = sorted(anns, key=lambda a: a.get("start_char", 0))
            tpl_len = len(tpl_text)

            # Build fixed-text segments between fillable zones
            fixed_parts = []
            pos = 0
            for ann in anns_sorted:
                start = max(0, min(ann.get("start_char", 0), tpl_len))
                end = max(start, min(ann.get("end_char", tpl_len), tpl_len))
                if pos < start:
                    fixed_parts.append(tpl_text[pos:start])
                else:
                    fixed_parts.append("")
                pos = max(pos, end)
            if pos < tpl_len:
                fixed_parts.append(tpl_text[pos:])
            else:
                fixed_parts.append("")

            # Build regex: ^fixed0(.*?)fixed1(.*?)...fixedN$
            escaped = [re.escape(p) for p in fixed_parts]
            pattern = "^" + "(.*?)".join(escaped) + "$"

            match = re.search(pattern, doc_text)
            if match:
                groups = match.groups()
                for i, ann in enumerate(anns_sorted):
                    key = f"{pi}_{ann.get('start_char', 0)}"
                    raw = groups[i] if i < len(groups) else ""
                    doc_start = match.start(i + 1) if i < len(groups) else 0
                    doc_end = match.end(i + 1) if i < len(groups) else 0
                    values[key] = {
                        "value": raw.strip().strip("_"),
                        "doc_start": doc_start,
                        "doc_end": doc_end
                    }
            else:
                # Fallback: character-slice extraction
                for ann in anns_sorted:
                    tpl_start = max(0, min(ann.get("start_char", 0), len(doc_text)))
                    tpl_end = max(tpl_start, min(ann.get("end_char", len(doc_text)), len(doc_text)))
                    key = f"{pi}_{tpl_start}"
                    val = doc_text[tpl_start:tpl_end].strip().strip("_")
                    values[key] = {
                        "value": val,
                        "doc_start": tpl_start,
                        "doc_end": tpl_start + len(val)
                    }

        return values
