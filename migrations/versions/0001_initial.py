"""Initial booking schema with database-enforced overlap protection."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.CheckConstraint("duration_minutes BETWEEN 5 AND 480", name="ck_service_duration"),
    )
    op.create_index("ix_services_owner_id", "services", ["owner_id"])
    op.create_table(
        "schedule_windows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("service_id", sa.Uuid(), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_schedule_weekday"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_schedule_order"),
    )
    op.create_index("ix_schedule_windows_service_id", "schedule_windows", ["service_id"])
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("service_id", sa.Uuid(), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_booking_order"),
        sa.CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_booking_status"),
    )
    op.execute("""
        ALTER TABLE bookings ADD CONSTRAINT ex_booking_overlap
        EXCLUDE USING gist (
            service_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        ) WHERE (status = 'confirmed')
    """)
    op.create_index("ix_booking_customer_start", "bookings", ["customer_id", "starts_at"])
    op.create_index("ix_booking_service_start", "bookings", ["service_id", "starts_at"])


def downgrade():
    op.drop_table("bookings")
    op.drop_table("schedule_windows")
    op.drop_table("services")
    op.drop_table("users")
    # btree_gist may be shared by other schemas; retain the extension.
