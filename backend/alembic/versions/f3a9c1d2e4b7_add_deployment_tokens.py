"""add_deployment_tokens

Revision ID: f3a9c1d2e4b7
Revises: b7c2d4e9f1a3
Create Date: 2026-11-17 09:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d2e4b7'
down_revision: Union[str, Sequence[str], None] = 'b7c2d4e9f1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'deployment_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'], ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['project_id'], ['projects.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_deployment_tokens_id'), 'deployment_tokens', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_deployment_tokens_project_id'),
        'deployment_tokens',
        ['project_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_deployment_tokens_token_hash'),
        'deployment_tokens',
        ['token_hash'],
        unique=True,
    )
    op.add_column(
        'deployments',
        sa.Column(
            'trigger_source',
            sa.String(length=20),
            server_default='manual',
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('deployments', 'trigger_source')
    op.drop_index(
        op.f('ix_deployment_tokens_token_hash'), table_name='deployment_tokens'
    )
    op.drop_index(
        op.f('ix_deployment_tokens_project_id'), table_name='deployment_tokens'
    )
    op.drop_index(op.f('ix_deployment_tokens_id'), table_name='deployment_tokens')
    op.drop_table('deployment_tokens')
