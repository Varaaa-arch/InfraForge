"""add_alert_channels_and_events

Revision ID: c3d8f2a1b7e4
Revises: 8361833b1efa
Create Date: 2026-11-12 07:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d8f2a1b7e4'
down_revision: Union[str, Sequence[str], None] = '8361833b1efa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    alert_channel_type = sa.Enum(
        'discord', 'telegram', name='alert_channel_type'
    )
    alert_status = sa.Enum('firing', 'resolved', name='alert_status')

    op.create_table(
        'alert_channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', alert_channel_type, nullable=False),
        sa.Column('encrypted_discord_webhook_url', sa.Text(), nullable=True),
        sa.Column('encrypted_telegram_bot_token', sa.Text(), nullable=True),
        sa.Column('telegram_chat_id', sa.String(length=100), nullable=True),
        sa.Column(
            'enabled', sa.Boolean(), server_default='true', nullable=False
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_alert_channels_id'), 'alert_channels', ['id'], unique=False
    )

    op.create_table(
        'alert_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('alert_name', sa.String(length=255), nullable=False),
        sa.Column('status', alert_status, nullable=False),
        sa.Column(
            'severity',
            sa.String(length=20),
            server_default='unknown',
            nullable=False,
        ),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('labels', sa.JSON(), nullable=False),
        sa.Column('annotations', sa.JSON(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_alert_events_id'), 'alert_events', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_alert_events_fingerprint'),
        'alert_events',
        ['fingerprint'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_alert_events_fingerprint'), table_name='alert_events'
    )
    op.drop_index(op.f('ix_alert_events_id'), table_name='alert_events')
    op.drop_table('alert_events')
    op.drop_index(
        op.f('ix_alert_channels_id'), table_name='alert_channels'
    )
    op.drop_table('alert_channels')
    sa.Enum(name='alert_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='alert_channel_type').drop(op.get_bind(), checkfirst=True)
