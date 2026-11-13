"""add_exporter_instance_to_servers

Revision ID: e7a1c4d9b2f6
Revises: c3d8f2a1b7e4
Create Date: 2026-11-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a1c4d9b2f6'
down_revision: Union[str, Sequence[str], None] = 'c3d8f2a1b7e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'servers',
        sa.Column(
            'exporter_instance',
            sa.String(length=253),
            nullable=True,
            comment=(
                "Label instance Prometheus (job=node-exporter) untuk metrik server ini, "
                "mis. host.docker.internal:9100. NULL = metrik belum tersedia."
            ),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('servers', 'exporter_instance')
