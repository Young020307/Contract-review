import time
from typing import Any

from pydantic import BaseModel, Field
from typing import Optional, Literal

# --- Annotation Rules ---
class ValidationRule(BaseModel):
    required: bool = Field(True, description="是否必填")
    min_chars: int = Field(1, description="最少字符数")
    max_chars: int = Field(200, description="最多字符数")
    allowed_chars: str = Field("any", description="字符类型: chinese|number|alphanumeric|any|regex")
    regex: str = Field("", description="当 allowed_chars=regex 时的正则表达式")
    field_name: str = Field("", description="字段名称，用于跨字段校验匹配")
    allowed_values: list[str] = Field([], description="可选值列表")
    match_fields: list[str] = Field([], description="需保持一致的字段名列表")
    radio_group: str = Field("", description="单选组名称，用于 Checkbox 互斥")
    dependent_paras: list[int] = Field([], description="受本 Checkbox 管辖的段落索引列表")
    amount_match_field: str = Field("", description="对应中文大写金额的 field_name")
    amount_unit: int = Field(1, description="金额单位倍数: 1=元, 1000=千元, 10000=万元")

# --- Request Models ---
class AnnotationItem(BaseModel):
    paragraph_index: int = Field(..., description="段落索引")
    start_char: int = Field(0, description="标注起始字符位置")
    end_char: int = Field(0, description="标注结束字符位置")
    zone_type: Literal["fixed", "fillable", "variable"] = Field(..., description="区域类型: fixed=固定文本, fillable=可填充, variable=可变文本")
    rules: Optional[ValidationRule] = Field(None, description="填充校验规则")

class AnnotationBatch(BaseModel):
    annotations: list[AnnotationItem] = Field(..., description="标注列表")

class ReviewRequest(BaseModel):
    template_id: int = Field(..., description="模板ID", examples=[1])
    document_id: int = Field(..., description="待审文档ID", examples=[1])

# --- Response Models ---
class ParagraphInfo(BaseModel):
    index: int = Field(..., description="段落序号")
    text: str = Field(..., description="段落文本内容")
    underline_ranges: list[list[int]] = Field([], description="下划线字符范围")
    is_table_cell: bool = Field(False, description="是否表格内段落")

class TemplateResponse(BaseModel):
    id: int = Field(..., description="模板ID")
    name: str = Field(..., description="模板文件名")
    paragraph_count: int = Field(..., description="段落总数")
    created_at: str = Field(..., description="创建时间")

class TemplateDetailResponse(BaseModel):
    id: int = Field(..., description="模板ID")
    name: str = Field(..., description="模板文件名")
    paragraphs: list[ParagraphInfo] = Field(..., description="段落列表")
    created_at: str = Field(..., description="创建时间")

class DocumentResponse(BaseModel):
    id: int = Field(..., description="文档ID")
    name: str = Field(..., description="文档文件名")
    template_id: Optional[int] = Field(None, description="关联的模板ID")
    paragraphs: list[ParagraphInfo] = Field(..., description="段落列表")
    uploaded_at: str = Field(..., description="上传时间")


class ApiResponse(BaseModel):
    code: int = Field(..., description="HTTP 状态码")
    message: str = Field(..., description="响应消息")
    data: Any = Field(None, description="响应数据，错误时为 null")
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000),
                           description="Unix 时间戳（毫秒）")
