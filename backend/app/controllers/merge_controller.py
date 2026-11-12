"""Duplicate-code merge endpoints: preview, execute (idempotent), rollback, list."""
from fastapi import Request
from sqlalchemy.orm import Session

from app.middlewares import audit_logger
from app.models import User
from app.schemas.metric import MetricMergeRequest
from app.services import merge_service


def preview(db: Session, payload: MetricMergeRequest) -> dict:
    return merge_service.preview_merge(db, payload.primary_metric_id, payload.source_metric_id)


def create_merge(request: Request, db: Session, user: User, payload: MetricMergeRequest) -> dict:
    result = merge_service.merge_metrics(
        db, user, payload.primary_metric_id, payload.source_metric_id, payload.reason
    )
    if not result.get("idempotent_reused"):
        merge_id = result["id"]
        audit_logger.record(
            request,
            "METRIC_MERGED",
            "metric_merge",
            merge_id,
            before=result.get("before"),
            after={
                "primary_metric": result.get("primary_metric"),
                "source_metric": result.get("source_metric"),
                "migration": result.get("migration"),
            },
        )
    return result


def rollback(request: Request, db: Session, user: User, merge_id: int) -> dict:
    result = merge_service.rollback_merge(db, user, merge_id)
    audit_logger.record(
        request,
        "METRIC_MERGE_ROLLED_BACK",
        "metric_merge",
        merge_id,
        after={"status": result["status"], "primary_metric": result.get("primary_metric")},
    )
    return result


def list_merges(db: Session, status: str | None = None) -> dict:
    rows = merge_service.list_merges(db, status)
    return {
        "items": [merge_service.serialize_merge(db, row) for row in rows],
        "total": len(rows),
    }


def get_merge(db: Session, merge_id: int) -> dict:
    return merge_service.serialize_merge(db, merge_service.get_merge_or_404(db, merge_id))
