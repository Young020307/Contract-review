from pydantic import BaseModel
from typing import Optional, Literal

# --- Annotation Rules ---
class ValidationRule(BaseModel):
    required: bool = True
    min_chars: int = 1
    max_chars: int = 200
    allowed_chars: str = "any"  # "chinese" | "number" | "alphanumeric" | "any" | "regex"
    regex: str = ""
    field_name: str = ""
    allowed_values: list[str] = []
    match_field: str = ""
    radio_group: str = ""

# --- Request Models ---
class AnnotationItem(BaseModel):
    paragraph_index: int
    start_char: int = 0
    end_char: int = 0
    zone_type: Literal["fixed", "fillable"]
    rules: Optional[ValidationRule] = None

class AnnotationBatch(BaseModel):
    annotations: list[AnnotationItem]

class ReviewRequest(BaseModel):
    template_id: int
    document_id: int

# --- Response Models ---
class ParagraphInfo(BaseModel):
    index: int
    text: str
    underline_ranges: list[list[int]] = []
    is_table_cell: bool = False

class TemplateResponse(BaseModel):
    id: int
    name: str
    paragraph_count: int
    created_at: str

class TemplateDetailResponse(BaseModel):
    id: int
    name: str
    paragraphs: list[ParagraphInfo]
    created_at: str

class DocumentResponse(BaseModel):
    id: int
    name: str
    template_id: Optional[int]
    paragraphs: list[ParagraphInfo]
    uploaded_at: str

class DiffSegment(BaseModel):
    type: Literal["equal", "insert", "delete", "replace"]
    template_range: tuple[int, int]
    doc_range: tuple[int, int]
    value: str

class Violation(BaseModel):
    paragraph: int
    type: str  # "insert" | "delete" | "replace"
    template_text: str
    actual_text: str

class CompareResult(BaseModel):
    template_text: str
    document_text: str
    diffs: list[DiffSegment]
    violations: list[Violation]

class FieldResult(BaseModel):
    paragraph: int
    start_char: int = 0
    end_char: int = 0
    field_name: str
    actual_value: str
    rule: str
    pass_: bool
    reason: str = ""

class ValidateResult(BaseModel):
    results: list[FieldResult]
