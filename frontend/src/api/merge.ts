import http from './http'
import type { MergeListResponse, MergePreview, MergeRecord, MetricMergeRequest } from '../types/merge'

export function previewMerge(payload: MetricMergeRequest) {
  return http.post<MergePreview>('/metrics/merges/preview', payload)
}

export function createMerge(payload: MetricMergeRequest) {
  return http.post<MergeRecord>('/metrics/merges', payload)
}

export function fetchMerges(status?: string) {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : ''
  return http.get<MergeListResponse>(`/metrics/merges${suffix}`)
}

export function fetchMerge(mergeId: number) {
  return http.get<MergeRecord>(`/metrics/merges/${mergeId}`)
}

export function rollbackMerge(mergeId: number) {
  return http.post<MergeRecord>(`/metrics/merges/${mergeId}/rollback`)
}
