"""ensure media_refs column and message_feedback table

Revision ID: a1b2c3d4e5f6
Revises: fff72140c4a2
Create Date: 2026-08-21 09:16:00.000000

The previous revision was marked applied before these objects existed
in the live database, so this migration is idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "fff72140c4a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS media_refs JSON")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS message_feedback (
            id UUID PRIMARY KEY,
            message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
            owner_external_id TEXT NOT NULL,
            value VARCHAR NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_feedback_owner_message UNIQUE (owner_external_id, message_id)
        )
        """
    )


def downgrade() -> None:
    op.drop_table("message_feedback")
    op.drop_column("chat_messages", "media_refs")
