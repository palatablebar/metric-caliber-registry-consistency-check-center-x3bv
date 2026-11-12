from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class MetricDefinition(Base):
    __tablename__ = "metric_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_team_id: Mapped[int] = mapped_column(ForeignKey("owner_teams.id"), nullable=False, index=True)
    # status: draft | active | deprecated | merged (app/constants/metric_status.py)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # BI dashboards / AB experiments that consume this metric (impact closure input)
    consumers_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # When status == "merged" this row is the historical alias entry; the pointer
    # carries the surviving primary metric. The row is never deleted so old codes
    # keep resolving in historical queries.
    merged_into_metric_id: Mapped[int | None] = mapped_column(
        ForeignKey("metric_definitions.id"), nullable=True, index=True
    )
    merge_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    owner_team = relationship("OwnerTeam", back_populates="metrics")
    versions = relationship(
        "MetricVersion", back_populates="metric", cascade="all, delete-orphan", order_by="MetricVersion.version_no"
    )
    outgoing_dependencies = relationship(
        "MetricDependency",
        back_populates="from_metric",
        foreign_keys="MetricDependency.from_metric_id",
        cascade="all, delete-orphan",
    )
    incoming_dependencies = relationship(
        "MetricDependency",
        back_populates="to_metric",
        foreign_keys="MetricDependency.to_metric_id",
    )
    merged_into = relationship(
        "MetricDefinition",
        remote_side=[id],
        foreign_keys=[merged_into_metric_id],
        back_populates="merged_aliases",
    )
    merged_aliases = relationship(
        "MetricDefinition",
        remote_side=[merged_into_metric_id],
        foreign_keys=[merged_into_metric_id],
        back_populates="merged_into",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MetricDefinition {self.metric_key}>"
