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
    def extract_fixed_text(file_path: str, fixed_indices: set[int]) -> str:
        """Extract text only from paragraphs marked as fixed zone."""
        doc = Document(file_path)
        texts = []
        for i, para in enumerate(doc.paragraphs):
            if i in fixed_indices and para.text.strip():
                texts.append(para.text.strip())
        return "\n".join(texts)

    @staticmethod
    def extract_fillable_values(file_path: str, fillable_indices: set[int]) -> dict[int, str]:
        """Extract text from fillable paragraphs, keyed by paragraph index."""
        doc = Document(file_path)
        values = {}
        for i, para in enumerate(doc.paragraphs):
            if i in fillable_indices:
                values[i] = para.text.strip()
        return values
