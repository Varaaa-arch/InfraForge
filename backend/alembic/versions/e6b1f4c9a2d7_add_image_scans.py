"""add image_scans

Revision ID: e6b1f4c9a2d7
Revises: d4e6f8a1c2b3
Create Date: 2026-11-22 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6b1f4c9a2d7"
down_revision: Union[str, Sequence[str], None] = "d4e6f8a1c2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Buat tabel riwayat scan kerentanan image."""
    scan_status = sa.Enum(
        "pending",
        "running",
        "completed",
        "failed",
        name="image_scan_status",
    )
    op.create_table(
        "image_scans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            nullable=True,
            comment="Project terkait (opsional); dihapus bersama project",
        ),
        sa.Column(
            "image_name",
            sa.String(length=500),
            nullable=False,
            comment="Referensi image yang dipindai, mis. nginx:1.27",
        ),
        sa.Column(
            "image_digest",
            sa.String(length=128),
            nullable=True,
            comment="ImageID/digest yang dilaporkan scanner",
        ),
        sa.Column(
            "status",
            scan_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "overall_severity",
            sa.String(length=20),
            nullable=True,
            comment="Severity tertinggi: critical/high/medium/low/none/unknown",
        ),
        sa.Column(
            "critical_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("high_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("medium_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("low_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "findings",
            sa.JSON(),
            nullable=True,
            comment=(
                "Daftar temuan CVE ringkas (dibatasi IMAGE_SCAN_MAX_FINDINGS)"
            ),
        ),
        sa.Column(
            "scanner", sa.String(length=50), server_default="trivy", nullable=False
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "requested_by",
            sa.String(length=160),
            nullable=True,
            comment="Username pemicu scan",
        ),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_image_scans_id"), "image_scans", ["id"], unique=False)
    op.create_index(
        op.f("ix_image_scans_project_id"),
        "image_scans",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_scans_image_name"),
        "image_scans",
        ["image_name"],
        unique=False,
    )


def downgrade() -> None:
    """Hapus tabel riwayat scan kerentanan image."""
    op.drop_index(op.f("ix_image_scans_image_name"), table_name="image_scans")
    op.drop_index(op.f("ix_image_scans_project_id"), table_name="image_scans")
    op.drop_index(op.f("ix_image_scans_id"), table_name="image_scans")
    op.drop_table("image_scans")
    sa.Enum(name="image_scan_status").drop(op.get_bind(), checkfirst=True)
