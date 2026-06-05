"""Initial schema: employees, submissions, line_items, policy_chunks, audit_logs, qa_sessions

Revision ID: 001
Revises:
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024  # voyage-3 output dimension


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "employees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", sa.String(20), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(200), unique=True, nullable=False),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("department", sa.String(100), nullable=False),
        sa.Column("role_title", sa.String(100), nullable=False),
        sa.Column("manager_id", UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_employees_employee_id", "employees", ["employee_id"])

    op.create_table(
        "submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("trip_purpose", sa.Text, nullable=False),
        sa.Column("trip_destination", sa.String(200), nullable=False),
        sa.Column("trip_start_date", sa.Date, nullable=False),
        sa.Column("trip_end_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="draft"),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("snapshot_grade", sa.Integer, nullable=False),
        sa.Column("snapshot_department", sa.String(100), nullable=False),
        sa.Column("reviewer_id", sa.String(200), nullable=True),
        sa.Column("reviewer_note", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_submissions_employee_id", "submissions", ["employee_id"])
    op.create_index("ix_submissions_status", "submissions", ["status"])

    op.create_table(
        "line_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", UUID(as_uuid=True), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receipt_filename", sa.String(300), nullable=True),
        sa.Column("category", sa.String(30), nullable=True),
        sa.Column("vendor", sa.String(200), nullable=True),
        sa.Column("transaction_date", sa.Date, nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(3), default="USD"),
        sa.Column("payment_method", sa.String(100), nullable=True),
        sa.Column("extracted_fields", JSONB, nullable=True),
        sa.Column("verdict", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("citations", JSONB, nullable=True),
        sa.Column("retrieval_score", sa.Float, nullable=True),
        sa.Column("override_verdict", sa.String(20), nullable=True),
        sa.Column("override_note", sa.Text, nullable=True),
        sa.Column("effective_verdict", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_line_items_submission_id", "line_items", ["submission_id"])

    op.create_table(
        "policy_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_id", sa.String(20), nullable=False),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("domain_tags", JSONB, nullable=True),
        sa.Column("source_file", sa.String(200), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("ts_vector", TSVECTOR, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_policy_chunks_policy_id", "policy_chunks", ["policy_id"])
    op.execute(
        "CREATE INDEX ix_policy_chunks_ts_vector ON policy_chunks USING GIN (ts_vector)"
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", UUID(as_uuid=True), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_item_id", UUID(as_uuid=True), sa.ForeignKey("line_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=True),
        sa.Column("old_value", JSONB, nullable=True),
        sa.Column("new_value", JSONB, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_submission_id", "audit_logs", ["submission_id"])

    op.create_table(
        "qa_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(200), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("citations", JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_qa_sessions_user_id", "qa_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("qa_sessions")
    op.drop_table("audit_logs")
    op.drop_table("policy_chunks")
    op.drop_table("line_items")
    op.drop_table("submissions")
    op.drop_table("employees")
