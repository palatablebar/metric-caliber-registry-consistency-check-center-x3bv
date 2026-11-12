export const MERGE_STATUSES = ['active', 'rolled_back'] as const
export type MergeStatusValue = (typeof MERGE_STATUSES)[number]
export const MERGE_STATUS_LABELS: Record<string, string> = {
  active: '已合并',
  rolled_back: '已回滚',
}
