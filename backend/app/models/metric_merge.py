from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class MetricMerge(Base):
    """One duplicate-code consolidation: ``source_metric`` (old code) is folded
    into ``primary_metric`` (surviving code).

    A row is created once per (primary, source) pair and kept for the whole
    lifecycle: rollback flips ``status`` to ``rolled_back`` instead of deleting
    it, and a later re-merge reactivates the same row. The JSON snapshots hold
    the exact pre/post catalog and relation states so the merge can be undone
    and so the before/after catalog, detail and dependency graph stay auditable.
    """

    __tablename__ = "metric_merges"
    __table_args__ = (
        UniqueConstraint("primary_metric_id", "source_metric_id", name="uq_metric_merge_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    primary_metric_id: Mapped[int] = mapped_column(
        ForeignKey("metric_definitions.id"), nullable=False, index=True
    )
    source_metric_id: Mapped[int] = mapped_column(
        ForeignKey("metric_definitions.id"), nullable=False, index=True
    )
    # active | rolled_back (app/constants/merge_status.py)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rolled_back_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # full catalog/relation state captured before the first successful merge
    before_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # catalog/relation state right after the most recent (re-)merge
    after_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    merge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    merged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    primary_metric = relationship(
        "MetricDefinition", foreign_keys=[primary_metric_id]
    )
    source_metric = relationship(
        "MetricDefinition", foreign_keys=[source_metric_id]
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MetricMerge {self.source_metric_id}->{self.primary_metric_id} {self.status}>"
