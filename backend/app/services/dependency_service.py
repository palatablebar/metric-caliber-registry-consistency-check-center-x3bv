"""Dependency graph projection + impact closure (downstream consumers)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.algorithms.graph import build_graph, impact_closure
from app.constants.error_codes import AppError, ErrorCode
from app.models import MetricDefinition, MetricDependency, OwnerTeam
from app.services.metric_service import get_metric_or_404


def _load(db: Session):
    # Merged alias entries are kept for historical queries but must never appear
    # as graph nodes: their relations were migrated to the primary metric, so
    # including them would count the same downstream metrics and dashboards twice.
    metrics = db.scalars(
        select(MetricDefinition)
        .where(MetricDefinition.merged_into_metric_id.is_(None))
        .order_by(MetricDefinition.metric_key)
    ).all()
    live_ids = {metric.id for metric in metrics}
    edges = db.scalars(select(MetricDependency).order_by(MetricDependency.id)).all()
    # drop any edge still pointing at an alias (rollback restores them; normal
    # writes keep the graph canonical, this is a defensive guard)
    edges = [
        edge
        for edge in edges
        if edge.from_metric_id in live_ids and (edge.to_metric_id is None or edge.to_metric_id in live_ids)
    ]
    metric_dicts = [
        {
            "id": metric.id,
            "key": metric.metric_key,
            "name": metric.display_name,
            "domain": metric.domain,
            "status": metric.status,
            "consumers": metric.consumers_json or [],
        }
        for metric in metrics
    ]
    edge_dicts = [
        {
            "from_id": edge.from_metric_id,
            "to_id": edge.to_metric_id,
            "to_table": edge.to_table,
            "relation": edge.relation,
            "note": edge.note,
        }
        for edge in edges
    ]
    return metrics, metric_dicts, edge_dicts


def graph_payload(db: Session) -> dict:
    metrics, metric_dicts, edge_dicts = _load(db)
    teams = {team.id: team for team in db.scalars(select(OwnerTeam)).all()}
    graph = build_graph(metric_dicts, [edge for edge in edge_dicts if edge["to_id"]])
    team_of = {metric.metric_key: teams.get(metric.owner_team_id) for metric in metrics}
    for node in graph["nodes"]:
        team = team_of.get(node["key"])
        node["team_code"] = team.code if team else None
        node["team_name"] = team.name if team else None
    table_edges = [edge for edge in edge_dicts if edge.get("to_table")]
    graph["table_edges"] = table_edges
    return graph


def impact_payload(db: Session, metric_id: int) -> dict:
    metric = get_metric_or_404(db, metric_id)
    # historical query on an old code: resolve to the primary metric so the
    # impact closure runs over the migrated, de-duplicated relation graph
    target_id = metric.merged_into_metric_id or metric.id
    target = db.get(MetricDefinition, target_id) or metric
    _metrics, metric_dicts, edge_dicts = _load(db)
    closure = impact_closure(target.id, metric_dicts, [edge for edge in edge_dicts if edge["to_id"]])
    closure["metric_id"] = target.id
    closure["metric_key"] = target.metric_key
    closure["metric_name"] = target.display_name
    closure["domain"] = target.domain
    if target.id != metric.id:
        closure["resolved_from"] = {
            "id": metric.id,
            "metric_key": metric.metric_key,
            "name": metric.display_name,
        }
    return closure
