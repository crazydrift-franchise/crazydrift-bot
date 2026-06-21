"""add antikrizisnik bot tables

Revision ID: 0001_ak_bot
Revises:
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_ak_bot"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ak_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger, nullable=False, unique=True, index=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("business_type", sa.String(255), nullable=True),
        sa.Column("employee_count", sa.String(50), nullable=True),
        sa.Column("city", sa.String(255), nullable=True),
        sa.Column("utm_source", sa.String(255), nullable=True),
        sa.Column("session_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("last_active_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("cd_lead_sent", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_table(
        "ak_signals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("ak_users.id"), nullable=False, index=True),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("source_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "ak_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("ak_users.id"), nullable=False, index=True),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("section", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ak_messages")
    op.drop_table("ak_signals")
    op.drop_table("ak_users")
