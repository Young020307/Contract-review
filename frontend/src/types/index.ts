export interface ParagraphInfo {
  index: number
  text: string
  underline_ranges?: [number, number][]
  is_table_cell?: boolean
}

export interface TemplateInfo {
  id: number
  name: string
  paragraph_count: number
  created_at: string
}

export interface TemplateDetail {
  id: number
  name: string
  paragraphs: ParagraphInfo[]
  created_at: string
}

export interface ValidationRule {
  required: boolean
  min_chars: number
  max_chars: number
  allowed_chars: 'chinese' | 'number' | 'alphanumeric' | 'any' | 'regex'
  regex: string
  field_name: string
  allowed_values: string[]
  match_field: string
}

export interface AnnotationItem {
  paragraph_index: number
  start_char: number
  end_char: number
  zone_type: 'fixed' | 'fillable'
  rules?: ValidationRule
}

export interface AnnotationEntry {
  paragraph_index: number
  start_char: number
  end_char: number
  zone_type: string
  rules: string
}

export interface DocumentInfo {
  id: number
  template_id: number | null
  name: string
  paragraphs: ParagraphInfo[]
  uploaded_at: string
}

export interface DiffSegment {
  type: 'equal' | 'insert' | 'delete' | 'replace'
  template_range: [number, number]
  doc_range: [number, number]
  value: string
}

export interface CompareViolation {
  paragraph: number
  type: string
  template_text: string
  actual_text: string
  template_range: [number, number]
  doc_range: [number, number]
}

export interface CompareResult {
  template_text: string
  document_text: string
  diffs: DiffSegment[]
  violations: CompareViolation[]
}

export interface FieldResult {
  paragraph: number
  start_char: number
  end_char: number
  field_name: string
  actual_value: string
  rule: string
  pass: boolean
  reason: string
  paragraph_text: string
  template_paragraph_text: string
}

export interface ValidateResult {
  results: FieldResult[]
  document_paragraphs: ParagraphInfo[]
  template_paragraphs: ParagraphInfo[]
}
