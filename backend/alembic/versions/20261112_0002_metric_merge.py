"""duplicate metric-code merge: merged pointer + metric_merges

Revision ID: 20261112_0002
Revises: 20261110_0001
Create Date: 2026-11-12

Runtime bootstrap is still ``Base.metadata.create_all`` (fresh compose stacks
need no migration step); this revision upgrades existing databases with the
self-referencing merge pointer on ``metric_definitions`` and the
``metric_merges`` audit/snapshot table.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261112_0002"
down_revision = "20261110_0001"
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    if _is_sqlite():
        # SQLite's ALTER TABLE ADD COLUMN cannot carry a foreign key, and a
        # single batch rebuild that both adds columns and creates a
        # self-referential FK trips Alembic's column reorder cycle. Add the
        # plain columns first, then rebuild once purely for the constraint/index.
        op.add_column(
            "metric_definitions",
            sa.Column("merged_into_metric_id", sa.Integer(), nullable=True),
        )
        op.add_column(
            "metric_definitions",
            sa.Column("merge_reason", sa.String(length=255), nullable=True),
        )
        with op.batch_alter_table("metric_definitions") as batch_op:
            batch_op.create_foreign_key(
                "fk_metric_definitions_merged_into",
                "metric_definitions",
                ["merged_into_metric_id"],
                ["id"],
            )
            batch_op.create_index(
                "ix_metric_definitions_merged_into_metric_id",
                ["merged_into_metric_id"],
            )
    else:
        op.add_column(
            "metric_definitions",
            sa.Column("merged_into_metric_id", sa.Integer(), nullable=True),
        )
        op.add_column(
            "metric_definitions",
            sa.Column("merge_reason", sa.String(length=255), nullable=True),
        )
        op.create_foreign_key(
            "fk_metric_definitions_merged_into",
            "metric_definitions",
            "metric_definitions",
            ["merged_into_metric_id"],
            ["id"],
        )
        op.create_index(
            "ix_metric_definitions_merged_into_metric_id",
            "metric_definitions",
            ["merged_into_metric_id"],
        )

    op.create_table(
        "metric_merges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("primary_metric_id", sa.Integer(), nullable=False),
        sa.Column("source_metric_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("merged_by", sa.String(length=120), nullable=True),
        sa.Column("rolled_back_by", sa.String(length=120), nullable=True),
        sa.Column("before_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("after_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("merge_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("merged_at", sa.DateTime(), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["primary_metric_id"], ["metric_definitions.id"]),
        sa.ForeignKeyConstraint(["source_metric_id"], ["metric_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("primary_metric_id", "source_metric_id", name="uq_metric_merge_pair"),
    )
    op.create_index("ix_metric_merges_primary_metric_id", "metric_merges", ["primary_metric_id"])
    op.create_index("ix_metric_merges_source_metric_id", "metric_merges", ["source_metric_id"])
    op.create_index("ix_metric_merges_status", "metric_merges", ["status"])


def downgrade() -> None:
    op.drop_index("ix_metric_merges_status", table_name="metric_merges")
    op.drop_index("ix_metric_merges_source_metric_id", table_name="metric_merges")
    op.drop_index("ix_metric_merges_primary_metric_id", table_name="metric_merges")
    op.drop_table("metric_merges")
    if _is_sqlite():
        with op.batch_alter_table("metric_definitions") as batch_op:
            batch_op.drop_index("ix_metric_definitions_merged_into_metric_id")
            batch_op.drop_constraint("fk_metric_definitions_merged_into", type_="foreignkey")
            batch_op.drop_column("merge_reason")
            batch_op.drop_column("merged_into_metric_id")
    else:
        op.drop_index("ix_metric_definitions_merged_into_metric_id", table_name="metric_definitions")
        op.drop_constraint("fk_metric_definitions_merged_into", "metric_definitions", type_="foreignkey")
        op.drop_column("metric_definitions", "merge_reason")
        op.drop_column("metric_definitions", "merged_into_metric_id")
