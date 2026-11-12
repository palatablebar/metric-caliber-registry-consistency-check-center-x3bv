import type { MergePointer } from './metric'

export interface MetricMergeRequest {
  primary_metric_id: number
  source_metric_id: number
  reason?: string | null
}

export interface MergeEdgeMove {
  edge_id: number
  from_metric_id: number
  to_metric_id: number | null
  to_table: string | null
  relation: string
}

export interface MergePreview {
  primary_metric: Record<string, unknown>
  source_metric: Record<string, unknown>
  edges_before: number
  edges_after: number
  edges_migrated_count: number
  edges_migrated: MergeEdgeMove[]
  duplicate_edges_dropped_count: number
  duplicate_edges_dropped: MergeEdgeMove[]
  boards_to_merge: string[]
  primary_boards_after: string[]
  source_versions_kept: number
  already_merged: boolean
  existing_merge_id: number | null
}

export interface MergeSnapshot {
  captured_at?: string
  metrics: Record<string, unknown>[]
  edges: Record<string, unknown>[]
}

export interface MergeVerification {
  primary: Record<string, unknown>
  source: Record<string, unknown>
  graph: {
    node_count: number
    edge_count: number
    cycle_count: number
    orphan_count: number
    node_keys: string[]
    edges: { from_key: string; to_key: string; relation: string }[]
    table_edges: Record<string, unknown>[]
  }
  primary_boards: string[]
  source_boards: string[]
}

export interface MergeMigration {
  edges_before: number
  edges_after: number
  edges_migrated: MergeEdgeMove[]
  duplicate_edges_dropped: MergeEdgeMove[]
  boards_merged: string[]
}

export interface MergeRecord {
  id: number
  status: 'active' | 'rolled_back'
  status_label: string
  reason: string | null
  merge_count: number
  merged_by: string | null
  rolled_back_by: string | null
  merged_at: string | null
  rolled_back_at: string | null
  created_at: string | null
  updated_at: string | null
  idempotent_reused?: boolean
  rolled_back_now?: boolean
  primary_metric: Record<string, unknown> | null
  source_metric: Record<string, unknown> | null
  before_snapshot: MergeSnapshot
  after_snapshot: { snapshot?: MergeSnapshot; verification?: MergeVerification }
  before?: MergeVerification
  after?: MergeVerification
  migration?: MergeMigration
}

export interface MergeListResponse {
  items: MergeRecord[]
  total: number
}

export interface MergeTargetOption {
  id: number
  key: string
  name: string
  domain: string
  status: string
  is_merged: boolean
  merged_into: MergePointer | null
}
