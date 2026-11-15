"""create_api_tokens

Revision ID: 2abe02d9fbdc
Revises: d8b14f0d4e53
Create Date: 2026-11-15 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2abe02d9fbdc'
down_revision: Union[str, Sequence[str], None] = 'd8b14f0d4e53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_tokens_token_hash', 'api_tokens', ['token_hash'], unique=True)
    op.create_index('ix_api_tokens_user_id', 'api_tokens', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_api_tokens_user_id', table_name='api_tokens')
    op.drop_index('ix_api_tokens_token_hash', table_name='api_tokens')
    op.drop_table('api_tokens')
