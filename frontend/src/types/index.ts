export interface ParagraphInfo {
  index: number
  text: string
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
}

export interface AnnotationItem {
  paragraph_index: number
  zone_type: 'fixed' | 'fillable'
  rules?: ValidationRule
}

export interface AnnotationEntry {
  paragraph_index: number
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
}

export interface CompareResult {
  template_text: string
  document_text: string
  diffs: DiffSegment[]
  violations: CompareViolation[]
}

export interface FieldResult {
  paragraph: number
  field_name: string
  actual_value: string
  rule: string
  pass: boolean
  reason: string
}

export interface ValidateResult {
  results: FieldResult[]
}
