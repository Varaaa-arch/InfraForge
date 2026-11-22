"""add tls_domains and tls_domain_checks

Revision ID: a1f2b3c4d5e6
Revises: e6b1f4c9a2d7
Create Date: 2026-11-22 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e6b1f4c9a2d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Buat tabel target TLS/SSL dan riwayat pemeriksaan sertifikat."""
    domain_status = sa.Enum(
        "pending",
        "healthy",
        "expiring",
        "expired",
        "invalid",
        "error",
        name="tls_domain_status",
    )
    op.create_table(
        "tls_domains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=True,
            comment="Label ramah untuk target",
        ),
        sa.Column(
            "host",
            sa.String(length=253),
            nullable=False,
            comment="Hostname atau alamat IP target",
        ),
        sa.Column("port", sa.Integer(), server_default="443", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "warning_days",
            sa.Integer(),
            server_default="30",
            nullable=False,
            comment="Ambang hari sebelum expiry dianggap expiring",
        ),
        sa.Column(
            "status", domain_status, server_default="pending", nullable=False
        ),
        sa.Column("days_remaining", sa.Integer(), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("protocol", sa.String(length=32), nullable=True),
        sa.Column("trusted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alerted_status", sa.String(length=20), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host", "port", name="uq_tls_domains_host_port"),
    )
    op.create_index(op.f("ix_tls_domains_id"), "tls_domains", ["id"], unique=False)

    op.create_table(
        "tls_domain_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tls_domain_id", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("days_remaining", sa.Integer(), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("protocol", sa.String(length=32), nullable=True),
        sa.Column("trusted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("alert_sent", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["tls_domain_id"], ["tls_domains.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tls_domain_checks_id"),
        "tls_domain_checks",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tls_domain_checks_tls_domain_id"),
        "tls_domain_checks",
        ["tls_domain_id"],
        unique=False,
    )


def downgrade() -> None:
    """Hapus tabel target TLS/SSL dan riwayat pemeriksaan."""
    op.drop_index(
        op.f("ix_tls_domain_checks_tls_domain_id"),
        table_name="tls_domain_checks",
    )
    op.drop_index(
        op.f("ix_tls_domain_checks_id"), table_name="tls_domain_checks"
    )
    op.drop_table("tls_domain_checks")
    op.drop_index(op.f("ix_tls_domains_id"), table_name="tls_domains")
    op.drop_table("tls_domains")
    sa.Enum(name="tls_domain_status").drop(op.get_bind(), checkfirst=True)
