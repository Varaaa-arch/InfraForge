"""add deployment token application scope

Revision ID: a7d2e5f8c1b4
Revises: f3a9c1d2e4b7
Create Date: 2026-11-18 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7d2e5f8c1b4"
down_revision: Union[str, Sequence[str], None] = "f3a9c1d2e4b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_deployment_tokens_application_id"


def upgrade() -> None:
    """Tambahkan scope aplikasi opsional pada deployment token."""
    op.add_column(
        "deployment_tokens",
        sa.Column("application_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        FK_NAME,
        "deployment_tokens",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_deployment_tokens_application_id"),
        "deployment_tokens",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    """Hapus scope aplikasi dari deployment token."""
    op.drop_index(
        op.f("ix_deployment_tokens_application_id"),
        table_name="deployment_tokens",
    )
    op.drop_constraint(FK_NAME, "deployment_tokens", type_="foreignkey")
    op.drop_column("deployment_tokens", "application_id")
