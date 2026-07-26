"""add git repository metadata to projects

Revision ID: 91b157b5aceb
Revises: c9263b26c431
Create Date: 2026-07-26 10:33:58.257126

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '91b157b5aceb'
down_revision: Union[str, Sequence[str], None] = 'c9263b26c431'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    git_provider_enum = postgresql.ENUM('github', 'gitlab', 'bitbucket', name='git_provider')
    git_provider_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('projects', sa.Column('repository_url', sa.String(length=500), nullable=True))
    op.add_column('projects', sa.Column('default_branch', sa.String(length=100), nullable=True))
    op.add_column('projects', sa.Column('provider', git_provider_enum, nullable=True))
    op.add_column('projects', sa.Column('repository_connected_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'repository_connected_at')
    op.drop_column('projects', 'provider')
    op.drop_column('projects', 'default_branch')
    op.drop_column('projects', 'repository_url')

    postgresql.ENUM(name='git_provider').drop(op.get_bind(), checkfirst=True)
