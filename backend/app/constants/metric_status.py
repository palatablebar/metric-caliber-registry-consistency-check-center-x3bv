"""Metric lifecycle status — mirrored by frontend/src/constants/metricStatus.ts."""
from enum import Enum


class MetricStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    # alias entry left behind after a duplicate-code merge; its data still exists
    # for historical queries and it points at the surviving primary metric
    MERGED = "merged"


ALL_METRIC_STATUSES = [s.value for s in MetricStatus]
# write endpoints only accept the lifecycle statuses; ``merged`` is set by the
# merge workflow, never directly through PATCH /metrics
WRITABLE_METRIC_STATUSES = [
    MetricStatus.DRAFT.value,
    MetricStatus.ACTIVE.value,
    MetricStatus.DEPRECATED.value,
]
STATUS_LABELS = {
    MetricStatus.DRAFT.value: "草稿",
    MetricStatus.ACTIVE.value: "生效",
    MetricStatus.DEPRECATED.value: "已下线",
    MetricStatus.MERGED.value: "已并入主指标",
}
