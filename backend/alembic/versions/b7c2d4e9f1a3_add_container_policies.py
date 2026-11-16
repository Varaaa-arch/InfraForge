"""add_container_policies

Revision ID: b7c2d4e9f1a3
Revises: 9c4e1f7a2b6d
Create Date: 2026-11-16 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2d4e9f1a3'
down_revision: Union[str, Sequence[str], None] = '9c4e1f7a2b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'container_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('container_name', sa.String(length=100), nullable=False),
        sa.Column('container_id', sa.String(length=64), nullable=True),
        sa.Column('compose_project', sa.String(length=100), nullable=True),
        sa.Column('compose_service', sa.String(length=100), nullable=True),
        sa.Column('cpu_limit_cores', sa.Float(), nullable=True),
        sa.Column('cpu_quota', sa.Integer(), nullable=True),
        sa.Column(
            'cpu_period', sa.Integer(), server_default='100000', nullable=False
        ),
        sa.Column('memory_limit_bytes', sa.BigInteger(), nullable=True),
        sa.Column(
            'restart_policy', sa.String(length=20), server_default='no', nullable=False
        ),
        sa.Column(
            'auto_heal_enabled', sa.Boolean(), server_default='false', nullable=False
        ),
        sa.Column(
            'unhealthy_threshold', sa.Integer(), server_default='3', nullable=False
        ),
        sa.Column('max_restarts', sa.Integer(), server_default='3', nullable=False),
        sa.Column(
            'restart_cooldown_seconds',
            sa.Integer(),
            server_default='300',
            nullable=False,
        ),
        sa.Column('unhealthy_streak', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_health_status', sa.String(length=20), nullable=True),
        sa.Column('last_restart_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'restart_count_window', sa.Integer(), server_default='0', nullable=False
        ),
        sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint('container_name'),
    )
    op.create_index(
        op.f('ix_container_policies_id'), 'container_policies', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_container_policies_container_name'),
        'container_policies',
        ['container_name'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_container_policies_container_name'), table_name='container_policies'
    )
    op.drop_index(op.f('ix_container_policies_id'), table_name='container_policies')
    op.drop_table('container_policies')
