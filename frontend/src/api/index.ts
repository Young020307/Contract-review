import axios from 'axios'
import type {
  TemplateInfo, TemplateDetail, AnnotationItem, AnnotationEntry,
  DocumentInfo, CompareResult, ValidateResult
} from '../types'

const api = axios.create({ baseURL: '/api' })

export async function uploadTemplate(file: File): Promise<TemplateInfo> {
  const fd = new FormData(); fd.append('file', file)
  const { data } = await api.post('/templates/upload', fd)
  return data
}

export async function listTemplates(): Promise<TemplateInfo[]> {
  const { data } = await api.get('/templates')
  return data
}

export async function getTemplate(id: number): Promise<TemplateDetail> {
  const { data } = await api.get(`/templates/${id}`)
  return data
}

export async function saveAnnotations(templateId: number, annotations: AnnotationItem[]): Promise<void> {
  await api.post(`/templates/${templateId}/annotations`, { annotations })
}

export async function getAnnotations(templateId: number): Promise<AnnotationEntry[]> {
  const { data } = await api.get(`/templates/${templateId}/annotations`)
  return data
}

export async function uploadDocument(file: File, templateId: number): Promise<DocumentInfo> {
  const fd = new FormData(); fd.append('file', file)
  const { data } = await api.post(`/documents/upload?template_id=${templateId}`, fd)
  return data
}

export async function getDocument(id: number): Promise<DocumentInfo> {
  const { data } = await api.get(`/documents/${id}`)
  return data
}

export async function reviewCompare(templateId: number, documentId: number): Promise<CompareResult> {
  const { data } = await api.post('/review/compare', { template_id: templateId, document_id: documentId })
  return data
}

export async function reviewValidate(templateId: number, documentId: number): Promise<ValidateResult> {
  const { data } = await api.post('/review/validate', { template_id: templateId, document_id: documentId })
  return data
}
