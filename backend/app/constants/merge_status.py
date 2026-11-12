"""Lifecycle of a duplicate-code merge record (app/models/metric_merge.py)."""
from enum import Enum


class MergeStatus(str, Enum):
    # the alias metric currently points at the primary metric
    ACTIVE = "active"
    # the merge was undone; catalog and relations were restored from the snapshot
    ROLLED_BACK = "rolled_back"


ALL_MERGE_STATUSES = [s.value for s in MergeStatus]
MERGE_STATUS_LABELS = {
    MergeStatus.ACTIVE.value: "已合并",
    MergeStatus.ROLLED_BACK.value: "已回滚",
}
