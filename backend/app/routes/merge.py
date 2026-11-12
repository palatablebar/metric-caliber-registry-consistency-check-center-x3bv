from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.controllers import merge_controller
from app.middlewares.auth import get_current_user
from app.middlewares.rbac import require_roles
from app.models import User
from app.schemas.metric import MetricMergeRequest

router = APIRouter(tags=["metric-merges"])

# consolidating the catalog is a governance-committee (admin) action only
ADMIN = require_roles("admin")


@router.post("/metrics/merges/preview")
def preview_merge(
    payload: MetricMergeRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(ADMIN),
):
    return merge_controller.preview(db, payload)


@router.post("/metrics/merges")
def create_merge(
    request: Request,
    payload: MetricMergeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(ADMIN),
):
    return merge_controller.create_merge(request, db, user, payload)


@router.get("/metrics/merges")
def list_merges(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return merge_controller.list_merges(db, status)


@router.get("/metrics/merges/{merge_id}")
def get_merge(
    merge_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return merge_controller.get_merge(db, merge_id)


@router.post("/metrics/merges/{merge_id}/rollback")
def rollback_merge(
    merge_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(ADMIN),
):
    return merge_controller.rollback(request, db, user, merge_id)
