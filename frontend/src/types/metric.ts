export type MetricStatus = 'draft' | 'active' | 'deprecated' | 'merged'
export type DomainKey = 'growth' | 'trade' | 'content' | 'experience'

export interface MergePointer {
  id: number
  key: string
  name: string
  status: string
}

export interface MergeRecordBrief {
  id: number
  status: string
  reason: string | null
  merged_by: string | null
  merged_at: string | null
}

export interface MergedAlias {
  id: number
  key: string
  name: string
  status: string
  merge_reason: string | null
}

export interface MergeRecordRow {
  id: number
  status: string
  status_label: string
  source_metric_id: number
  reason: string | null
  merged_by: string | null
  merged_at: string | null
  rolled_back_at: string | null
}

export interface Tuple {
  agg: string | null
  measure: string | null
  filters: string[]
  window: string | null
  grain: string | null
}

export interface MetricVersion {
  id: number
  metric_id: number
  version_no: number
  team_id: number
  team_code: string | null
  team_name: string | null
  dsl_text: string
  agg: string | null
  measure: string | null
  source_table: string | null
  filters: string[]
  window: string | null
  grain: string | null
  parse_status: string
  parse_error: string | null
  is_current: boolean
  effective_from: string | null
  created_by: string | null
  created_at: string | null
  tuple: Tuple
}

export interface DependencyRef {
  edge_id: number
  id: number
  key: string
  name: string
  domain: string
  relation: string
  note?: string
}

export interface TableRef {
  edge_id: number
  table: string
  relation: string
  note?: string
}

export interface Metric {
  id: number
  key: string
  name: string
  domain: DomainKey
  domain_label: string
  status: MetricStatus
  status_label: string
  owner_team: { id: number; code: string | null; name: string | null }
  description: string | null
  consumers: string[]
  version_count: number
  team_count: number
  current_version: MetricVersion | null
  updated_at: string | null
  is_merged: boolean
  merge_reason: string | null
  merged_into: MergePointer | null
}

export interface MetricDetail extends Metric {
  versions: MetricVersion[]
  merge_record: MergeRecordBrief | null
  merged_aliases: MergedAlias[]
  merge_records: MergeRecordRow[]
  dependencies: {
    upstream: DependencyRef[]
    downstream: DependencyRef[]
    tables: TableRef[]
  }
}

export interface MetricListResponse {
  items: Metric[]
  total: number
  page: number
  page_size: number
  domain_counts: Record<string, number>
  domains: { value: DomainKey; label: string }[]
  include_merged?: boolean
}

export interface DslToken {
  start: number
  end: number
  kind: string
}

export interface DslParseResult {
  ok: boolean
  metric_key: string | null
  agg: string | null
  measure: string | null
  distinct: boolean
  source_table: string | null
  filters: string[]
  window: string | null
  grain: string | null
  tuple: Tuple | null
  dependencies: string[]
  tokens: DslToken[]
  warnings: string[]
  error: string | null
  error_kind: string | null
  error_offset: number
  source_text: string
}

export interface VersionCompare {
  metric_id: number
  metric_key: string
  version_a: MetricVersion
  version_b: MetricVersion
  tuple_a: Tuple
  tuple_b: Tuple
  dimensions: string[]
  severity: string | null
  conflict_type: string | null
  summary: string
  evidence: Record<string, { field: string; left: unknown; right: unknown }>
  consistent: boolean
}
