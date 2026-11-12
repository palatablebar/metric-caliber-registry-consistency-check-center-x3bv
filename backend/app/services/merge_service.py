"""Duplicate metric-code consolidation.

The governance committee can fold a duplicate registration (the *source* / old
code) into one surviving *primary* metric. The whole workflow is built around
five guarantees:

1. the old code is never deleted — its row stays queryable, gains ``status =
   merged`` and a ``merged_into_metric_id`` pointer at the primary metric;
2. dependencies and BI-dashboard relations are migrated exactly once, with
   duplicate edges collapsed, so the dependency graph never counts the same
   downstream twice;
3. every merge runs in a single DB transaction — any failure rolls the catalog
   and the relations back to the pre-merge snapshot;
4. submitting the same (primary, source) pair again is idempotent and only ever
   takes effect once;
5. before/after catalog, detail and graph states are captured in the merge
   record so the consolidation stays auditable and reversible.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.error_codes import AppError, ErrorCode
from app.constants.merge_status import MERGE_STATUS_LABELS, MergeStatus
from app.constants.metric_status import MetricStatus
from app.models import MetricDefinition, MetricDependency, MetricMerge, User
from app.services import dependency_service
from app.utils.formatters import iso
from app.utils.logger import log_event


# --------------------------------------------------------------------------- loading
def get_merge_or_404(db: Session, merge_id: int) -> MetricMerge:
    merge = db.get(MetricMerge, merge_id)
    if merge is None:
        raise AppError(ErrorCode.MERGE_NOT_FOUND, detail={"merge_id": merge_id})
    return merge


def find_merge(db: Session, primary_id: int, source_id: int) -> MetricMerge | None:
    return db.scalar(
        select(MetricMerge).where(
            MetricMerge.primary_metric_id == primary_id,
            MetricMerge.source_metric_id == source_id,
        )
    )


def list_merges(db: Session, status: str | None = None) -> list[MetricMerge]:
    stmt = select(MetricMerge).order_by(MetricMerge.id.desc())
    if status:
        stmt = stmt.where(MetricMerge.status == status)
    return list(db.scalars(stmt).all())


# --------------------------------------------------------------------------- snapshots
def _snapshot_metric(metric: MetricDefinition) -> dict:
    return {
        "id": metric.id,
        "metric_key": metric.metric_key,
        "display_name": metric.display_name,
        "domain": metric.domain,
        "owner_team_id": metric.owner_team_id,
        "status": metric.status,
        "description": metric.description,
        "consumers": list(metric.consumers_json or []),
        "merged_into_metric_id": metric.merged_into_metric_id,
        "merge_reason": metric.merge_reason,
    }


def _snapshot_edge(edge: MetricDependency) -> dict:
    return {
        "id": edge.id,
        "from_metric_id": edge.from_metric_id,
        "to_metric_id": edge.to_metric_id,
        "to_table": edge.to_table,
        "relation": edge.relation,
        "note": edge.note,
    }


def _collect_snapshot(db: Session, metric_ids: set[int]) -> dict:
    """Immutable picture of the two metrics and every edge touching either one,
    taken before any mutation — rollback restores exactly this state."""
    metrics = list(
        db.scalars(select(MetricDefinition).where(MetricDefinition.id.in_(metric_ids))).all()
    )
    edges = list(
        db.scalars(
            select(MetricDependency).where(
                (MetricDependency.from_metric_id.in_(metric_ids))
                | (MetricDependency.to_metric_id.in_(metric_ids))
            )
        ).all()
    )
    return {
        "metrics": [_snapshot_metric(metric) for metric in metrics],
        "edges": [_snapshot_edge(edge) for edge in edges],
        "captured_at": iso(datetime.now()),
    }


def _canonical_edge_set(primary_id: int, source_id: int, edges: list[MetricDependency]) -> list[dict]:
    """Re-point every edge touching the old code at the primary metric, collapsing
    duplicates (including self-loops created by the re-pointing itself)."""
    def canon(value: int | None) -> int | None:
        return primary_id if value == source_id else value

    seen: set[tuple] = set()
    canonical: list[dict] = []
    for edge in edges:
        from_id = canon(edge.from_metric_id)
        to_id = canon(edge.to_metric_id)
        to_table = edge.to_table
        key = (from_id, to_id, to_table)
        if key in seen:
            continue
        seen.add(key)
        canonical.append(
            {
                "from_metric_id": from_id,
                "to_metric_id": to_id,
                "to_table": to_table,
                "relation": edge.relation,
                "note": edge.note,
            }
        )
    return canonical


# --------------------------------------------------------------------------- verification summary
def _graph_summary(db: Session) -> dict:
    """Lightweight graph projection used to compare before/after states. After a
    merge the alias is excluded here, so each downstream is counted once."""
    graph = dependency_service.graph_payload(db)
    return {
        "node_count": graph["stats"]["node_count"],
        "edge_count": graph["stats"]["edge_count"],
        "cycle_count": graph["stats"]["cycle_count"],
        "orphan_count": graph["stats"]["orphan_count"],
        "node_keys": [node["key"] for node in graph["nodes"]],
        "edges": [
            {"from_key": edge["from_key"], "to_key": edge["to_key"], "relation": edge["relation"]}
            for edge in graph["edges"]
        ],
        "table_edges": graph["table_edges"],
    }


def _verification(db: Session, primary: MetricDefinition, source: MetricDefinition) -> dict:
    return {
        "primary": _snapshot_metric(primary),
        "source": _snapshot_metric(source),
        "graph": _graph_summary(db),
        "primary_boards": list(primary.consumers_json or []),
        "source_boards": list(source.consumers_json or []),
    }


# --------------------------------------------------------------------------- preview
def preview_merge(db: Session, primary_id: int, source_id: int) -> dict:
    """Dry-run: what would move, what would collapse — nothing is written."""
    primary, source = _load_pair(db, primary_id, source_id)
    involved_ids = {primary.id, source.id}
    edges = list(
        db.scalars(
            select(MetricDependency).where(
                (MetricDependency.from_metric_id.in_(involved_ids))
                | (MetricDependency.to_metric_id.in_(involved_ids))
            )
        ).all()
    )
    canonical = _canonical_edge_set(primary.id, source.id, edges)
    migrated, dropped = _edge_migration_plan(primary.id, source.id, edges, canonical)
    source_boards = list(source.consumers_json or [])
    primary_boards = list(primary.consumers_json or [])
    boards_to_add = [board for board in source_boards if board not in primary_boards]
    existing = find_merge(db, primary.id, source.id)
    return {
        "primary_metric": _snapshot_metric(primary),
        "source_metric": _snapshot_metric(source),
        "edges_before": len(edges),
        "edges_after": len(canonical),
        "edges_migrated_count": len(migrated),
        "edges_migrated": migrated,
        "duplicate_edges_dropped_count": len(dropped),
        "duplicate_edges_dropped": dropped,
        "boards_to_merge": boards_to_add,
        "primary_boards_after": primary_boards + boards_to_add,
        "source_versions_kept": len(source.versions),
        "already_merged": existing is not None and existing.status == MergeStatus.ACTIVE.value,
        "existing_merge_id": existing.id if existing else None,
    }


def _edge_migration_plan(primary_id: int, source_id: int, edges: list[MetricDependency], canonical: list[dict]):
    """Classify each original edge: migrated (re-pointed/kept) or dropped as a
    duplicate. Each surviving relation is migrated exactly once."""
    migrated: list[dict] = []
    dropped: list[dict] = []
    seen_keys: set[tuple] = set()

    def canon(value: int | None) -> int | None:
        return primary_id if value == source_id else value

    for edge in edges:
        from_id = canon(edge.from_metric_id)
        to_id = canon(edge.to_metric_id)
        key = (from_id, to_id, edge.to_table)
        rendered = {
            "edge_id": edge.id,
            "from_metric_id": from_id,
            "to_metric_id": to_id,
            "to_table": edge.to_table,
            "relation": edge.relation,
        }
        if key in seen_keys:
            dropped.append(rendered)
        else:
            seen_keys.add(key)
            migrated.append(rendered)
    return migrated, dropped


# --------------------------------------------------------------------------- validation
def _load_pair(db: Session, primary_id: int, source_id: int) -> tuple[MetricDefinition, MetricDefinition]:
    if primary_id == source_id:
        raise AppError(
            ErrorCode.MERGE_SAME_METRIC,
            detail={"primary_metric_id": primary_id, "source_metric_id": source_id},
        )
    primary = db.get(MetricDefinition, primary_id)
    if primary is None:
        raise AppError(ErrorCode.METRIC_NOT_FOUND, detail={"metric_id": primary_id})
    source = db.get(MetricDefinition, source_id)
    if source is None:
        raise AppError(ErrorCode.METRIC_NOT_FOUND, detail={"metric_id": source_id})
    return primary, source


def _assert_mergeable(primary: MetricDefinition, source: MetricDefinition) -> None:
    if source.status == MetricStatus.MERGED.value and source.merged_into_metric_id == primary.id:
        # already merged into this exact primary — handled as idempotent by caller
        return
    if source.status == MetricStatus.MERGED.value:
        raise AppError(
            ErrorCode.METRIC_ALREADY_MERGED,
            detail={
                "source_metric_id": source.id,
                "merged_into_metric_id": source.merged_into_metric_id,
            },
        )
    if primary.status == MetricStatus.MERGED.value:
        raise AppError(
            ErrorCode.MERGE_CONFLICT,
            message="主指标本身已被并入其他指标，不能作为合并目标",
            detail={"primary_metric_id": primary.id, "merged_into_metric_id": primary.merged_into_metric_id},
        )


# --------------------------------------------------------------------------- merge
def merge_metrics(db: Session, user: User, primary_id: int, source_id: int, reason: str | None) -> dict:
    """Fold ``source_id`` into ``primary_id`` inside one transaction.

    Repeating the same (primary, source) pair returns the existing active merge
    without touching any data — the combination only ever takes effect once.
    """
    primary, source = _load_pair(db, primary_id, source_id)

    # ---- idempotency: same pair submitted again ----
    existing = find_merge(db, primary.id, source.id)
    if existing is not None and existing.status == MergeStatus.ACTIVE.value:
        log_event(
            "METRIC_MERGE_IDEMPOTENT",
            merge_id=existing.id,
            primary=primary.metric_key,
            source=source.metric_key,
            actor=user.email,
        )
        return serialize_merge(db, existing, reused=True)

    _assert_mergeable(primary, source)

    # a source already pointing at a *different* primary is rejected above;
    # a rolled-back row for this pair gets reactivated below.
    involved_ids = {primary.id, source.id}
    try:
        # ---- snapshot BEFORE any mutation ----
        if existing is None:
            before_snapshot = _collect_snapshot(db, involved_ids)
        else:
            # re-merge after rollback: keep the original first-merge snapshot
            before_snapshot = existing.before_snapshot_json or _collect_snapshot(db, involved_ids)
        before_verification = _verification(db, primary, source)

        edges = list(
            db.scalars(
                select(MetricDependency).where(
                    (MetricDependency.from_metric_id.in_(involved_ids))
                    | (MetricDependency.to_metric_id.in_(involved_ids))
                )
            ).all()
        )
        canonical = _canonical_edge_set(primary.id, source.id, edges)
        migrated, dropped = _edge_migration_plan(primary.id, source.id, edges, canonical)

        # ---- 1. relations: remove old rows, write the de-duplicated canonical set ----
        old_edge_ids = [edge.id for edge in edges]
        if old_edge_ids:
            for edge in edges:
                db.delete(edge)
            db.flush()
        for row in canonical:
            db.add(MetricDependency(**row))

        # ---- 2. dashboard consumers: union once, preserving order, no duplicates ----
        merged_boards = list(primary.consumers_json or [])
        for board in source.consumers_json or []:
            if board not in merged_boards:
                merged_boards.append(board)
        primary.consumers_json = merged_boards

        # ---- 3. old code stays queryable but clearly points at the primary ----
        source.status = MetricStatus.MERGED.value
        source.merged_into_metric_id = primary.id
        source.merge_reason = reason

        # ---- 4. upsert the merge record (one row per pair for its whole lifecycle) ----
        now = datetime.now()
        if existing is None:
            merge = MetricMerge(
                primary_metric_id=primary.id,
                source_metric_id=source.id,
                status=MergeStatus.ACTIVE.value,
                reason=reason,
                merged_by=user.display_name or user.email,
                before_snapshot_json=before_snapshot,
                merge_count=1,
                merged_at=now,
            )
            db.add(merge)
        else:
            merge = existing
            merge.status = MergeStatus.ACTIVE.value
            merge.reason = reason
            merge.merged_by = user.display_name or user.email
            merge.merge_count = int(merge.merge_count or 1) + 1
            merge.merged_at = now
            merge.rolled_back_at = None
            merge.rolled_back_by = None
        db.flush()

        after_verification = _verification(db, primary, source)
        merge.after_snapshot_json = {
            "snapshot": _collect_snapshot(db, involved_ids),
            "verification": after_verification,
            # keep the pre-merger verification next to the post-merger one so
            # the before/after panel works when the record is re-read later
            "before_verification": before_verification,
        }
        db.flush()

        db.commit()
        db.refresh(merge)
        log_event(
            "METRIC_MERGED",
            merge_id=merge.id,
            primary=primary.metric_key,
            source=source.metric_key,
            edges_migrated=len(migrated),
            duplicates_dropped=len(dropped),
            actor=user.email,
        )
        payload = serialize_merge(db, merge)
        payload["migration"] = {
            "edges_before": len(edges),
            "edges_after": len(canonical),
            "edges_migrated": migrated,
            "duplicate_edges_dropped": dropped,
            "boards_merged": merged_boards,
        }
        payload["before"] = before_verification
        payload["after"] = after_verification
        return payload
    except IntegrityError:
        # concurrent submission of the same (primary, source) pair: the unique
        # constraint rejected our row, so the other transaction already owns
        # this combination — answer idempotently instead of failing
        db.rollback()
        winner = find_merge(db, primary_id, source_id)
        if winner is not None and winner.status == MergeStatus.ACTIVE.value:
            log_event(
                "METRIC_MERGE_IDEMPOTENT_RACE",
                merge_id=winner.id,
                primary=primary.metric_key,
                source=source.metric_key,
                actor=user.email,
            )
            return serialize_merge(db, winner, reused=True)
        log_event(
            "METRIC_MERGE_FAILED",
            primary=primary.metric_key,
            source=source.metric_key,
            actor=user.email,
            reason="integrity",
        )
        raise AppError(
            ErrorCode.MERGE_CONFLICT,
            message="合并与当前目录状态冲突，请刷新合并台账后重试",
            detail={"primary_metric_id": primary_id, "source_metric_id": source_id},
        )
    except Exception:
        # any other failure restores catalog + relations to the pre-merge state
        db.rollback()
        log_event(
            "METRIC_MERGE_FAILED",
            primary=primary.metric_key,
            source=source.metric_key,
            actor=user.email,
        )
        raise


# --------------------------------------------------------------------------- rollback
def rollback_merge(db: Session, user: User, merge_id: int) -> dict:
    """Undo a merge: restore both metrics and every relation from the snapshot
    captured before the first successful merge."""
    merge = get_merge_or_404(db, merge_id)
    if merge.status != MergeStatus.ACTIVE.value:
        raise AppError(
            ErrorCode.MERGE_CONFLICT,
            message="该合并记录已经回滚，无需重复操作",
            detail={"merge_id": merge.id, "status": merge.status},
        )
    snapshot = merge.before_snapshot_json or {}
    metric_snapshots = {row["id"]: row for row in snapshot.get("metrics", [])}
    edge_snapshots = snapshot.get("edges", [])
    involved_ids = set(metric_snapshots)
    if merge.primary_metric_id not in metric_snapshots or merge.source_metric_id not in metric_snapshots:
        raise AppError(
            ErrorCode.MERGE_CONFLICT,
            message="合并前快照不完整，无法安全回滚",
            detail={"merge_id": merge.id},
        )
    try:
        # ---- restore metric rows from the immutable snapshot ----
        metrics = {
            metric.id: metric
            for metric in db.scalars(
                select(MetricDefinition).where(MetricDefinition.id.in_(involved_ids))
            ).all()
        }
        for metric_id, saved in metric_snapshots.items():
            metric = metrics.get(metric_id)
            if metric is None:
                raise AppError(
                    ErrorCode.MERGE_CONFLICT,
                    message="快照中的指标已不存在，无法回滚",
                    detail={"metric_id": metric_id},
                )
            metric.display_name = saved["display_name"]
            metric.domain = saved["domain"]
            metric.owner_team_id = saved["owner_team_id"]
            metric.status = saved["status"]
            metric.description = saved["description"]
            metric.consumers_json = list(saved["consumers"])
            metric.merged_into_metric_id = saved["merged_into_metric_id"]
            metric.merge_reason = saved["merge_reason"]

        # ---- rebuild relations exactly as they were before the merge ----
        current_edges = list(
            db.scalars(
                select(MetricDependency).where(
                    (MetricDependency.from_metric_id.in_(involved_ids))
                    | (MetricDependency.to_metric_id.in_(involved_ids))
                )
            ).all()
        )
        for edge in current_edges:
            db.delete(edge)
        db.flush()
        for saved in edge_snapshots:
            db.add(
                MetricDependency(
                    id=saved["id"],
                    from_metric_id=saved["from_metric_id"],
                    to_metric_id=saved["to_metric_id"],
                    to_table=saved["to_table"],
                    relation=saved["relation"],
                    note=saved["note"],
                )
            )

        merge.status = MergeStatus.ROLLED_BACK.value
        merge.rolled_back_at = datetime.now()
        merge.rolled_back_by = user.display_name or user.email
        db.flush()
        db.commit()
        db.refresh(merge)
        log_event(
            "METRIC_MERGE_ROLLED_BACK",
            merge_id=merge.id,
            primary=merge.primary_metric_id,
            source=merge.source_metric_id,
            actor=user.email,
        )
        return serialize_merge(db, merge, restored=True)
    except Exception:
        db.rollback()
        log_event("METRIC_MERGE_ROLLBACK_FAILED", merge_id=merge.id, actor=user.email)
        raise


# --------------------------------------------------------------------------- serialisation
def serialize_merge(db: Session, merge: MetricMerge, reused: bool = False, restored: bool = False) -> dict:
    primary = db.get(MetricDefinition, merge.primary_metric_id)
    source = db.get(MetricDefinition, merge.source_metric_id)
    after_snapshot = merge.after_snapshot_json or {}
    return {
        "id": merge.id,
        "status": merge.status,
        "status_label": MERGE_STATUS_LABELS.get(merge.status, merge.status),
        "reason": merge.reason,
        "merge_count": merge.merge_count,
        "merged_by": merge.merged_by,
        "rolled_back_by": merge.rolled_back_by,
        "merged_at": iso(merge.merged_at),
        "rolled_back_at": iso(merge.rolled_back_at),
        "created_at": iso(merge.created_at),
        "updated_at": iso(merge.updated_at),
        "idempotent_reused": reused,
        "rolled_back_now": restored,
        "primary_metric": _snapshot_metric(primary) if primary else None,
        "source_metric": _snapshot_metric(source) if source else None,
        "before_snapshot": merge.before_snapshot_json,
        "after_snapshot": after_snapshot,
        # stable before/after views available both on the write response and
        # when the record is re-read from the ledger
        "before": after_snapshot.get("before_verification"),
        "after": after_snapshot.get("verification"),
    }
