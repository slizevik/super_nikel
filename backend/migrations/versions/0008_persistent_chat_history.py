"""Persist chat sessions and answer history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_persistent_chat_history"
down_revision = "0007_library_full_text_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_chat_sessions_title_nonempty",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("translated_question", sa.String(length=2000), nullable=True),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(question)) > 0",
            name="ck_chat_messages_question_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(answer)) > 0",
            name="ck_chat_messages_answer_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chat_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_messages_chat_created_at",
        "chat_messages",
        ["chat_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_chat_created_at", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
