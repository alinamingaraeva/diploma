"""add feedbacks table and media_refs

Revision ID: fff72140c4a2
Revises: ceb168b3caeb
Create Date: 2026-07-05 13:27:09.501287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fff72140c4a2"
down_revision: Union[str, Sequence[str], None] = "ceb168b3caeb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("media_refs", sa.JSON(), nullable=True))
    op.create_table(
        "message_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("owner_external_id", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_external_id", "message_id", name="uq_feedback_owner_message"),
    )


def downgrade() -> None:
    op.drop_table("message_feedback")
    op.drop_column("chat_messages", "media_refs")
