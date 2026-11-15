"""add_slack_channel_and_min_severity

Revision ID: 9c4e1f7a2b6d
Revises: 2abe02d9fbdc
Create Date: 2026-11-15 16:30:00.000000

Catatan: PostgreSQL tidak mendukung penghapusan nilai enum. Saat downgrade,
kolom baru dihapus tetapi nilai ``slack`` pada ``alert_channel_type`` tetap ada
(tidak berbahaya dan tidak dapat dipakai tanpa kolom konfigurasi).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c4e1f7a2b6d'
down_revision: Union[str, Sequence[str], None] = '2abe02d9fbdc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE alert_channel_type ADD VALUE IF NOT EXISTS 'slack'")
    op.add_column(
        'alert_channels',
        sa.Column('encrypted_slack_webhook_url', sa.Text(), nullable=True),
    )
    op.add_column(
        'alert_channels',
        sa.Column(
            'min_severity',
            sa.String(length=20),
            server_default='info',
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('alert_channels', 'min_severity')
    op.drop_column('alert_channels', 'encrypted_slack_webhook_url')
