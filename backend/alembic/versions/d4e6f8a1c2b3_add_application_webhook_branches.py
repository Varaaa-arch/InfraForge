"""add application webhook branches

Revision ID: d4e6f8a1c2b3
Revises: c8e4a1d9f2b3
Create Date: 2026-11-19 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e6f8a1c2b3"
down_revision: Union[str, Sequence[str], None] = "c8e4a1d9f2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Tambahkan daftar branch pemicu webhook per aplikasi."""
    op.add_column(
        "applications",
        sa.Column(
            "webhook_branches",
            sa.JSON(),
            nullable=True,
            comment=(
                "Daftar branch exact yang memicu deployment webhook; "
                "NULL berarti fallback ke branch"
            ),
        ),
    )


def downgrade() -> None:
    """Hapus daftar branch pemicu webhook dari aplikasi."""
    op.drop_column("applications", "webhook_branches")
