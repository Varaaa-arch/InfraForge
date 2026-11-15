"""add_role_to_users

Revision ID: 631d7c1523a9
Revises: e7a1c4d9b2f6
Create Date: 2026-11-14 18:29:54.694923

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '631d7c1523a9'
down_revision: Union[str, Sequence[str], None] = 'e7a1c4d9b2f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column(
            'role',
            sa.String(length=20),
            nullable=False,
            server_default='viewer',
            comment=(
                "Peran RBAC: admin (akses penuh), developer (deploy & konfigurasi), "
                "viewer (read-only). User baru default viewer."
            ),
        ),
    )

    op.execute("UPDATE users SET role = 'developer'")
    op.execute("UPDATE users SET role = 'admin' WHERE username = 'admin'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'role')
