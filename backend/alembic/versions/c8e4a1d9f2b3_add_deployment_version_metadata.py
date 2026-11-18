"""add deployment version metadata

Revision ID: c8e4a1d9f2b3
Revises: a7d2e5f8c1b4
Create Date: 2026-11-18 21:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8e4a1d9f2b3"
down_revision: Union[str, Sequence[str], None] = "a7d2e5f8c1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Tambahkan tag rilis dan identitas pemicu pada deployment."""
    op.add_column(
        "deployments",
        sa.Column(
            "tag",
            sa.String(length=100),
            nullable=True,
            comment="Git tag yang menunjuk tepat ke commit deployment, jika ada",
        ),
    )
    op.add_column(
        "deployments",
        sa.Column(
            "triggered_by",
            sa.String(length=160),
            nullable=True,
            comment=(
                "Identitas pemicu: username, deploy-token:<nama>, atau webhook"
            ),
        ),
    )


def downgrade() -> None:
    """Hapus metadata versi dari deployment."""
    op.drop_column("deployments", "triggered_by")
    op.drop_column("deployments", "tag")
