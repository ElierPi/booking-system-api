from datetime import datetime, time
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Service(Base):
    """A single independently bookable resource with capacity one."""

    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("duration_minutes BETWEEN 5 AND 480", name="ck_service_duration"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(80))
    duration_minutes: Mapped[int] = mapped_column(Integer)


class ScheduleWindow(Base):
    __tablename__ = "schedule_windows"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_schedule_weekday"),
        CheckConstraint("ends_at > starts_at", name="ck_schedule_order"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    service_id: Mapped[UUID] = mapped_column(ForeignKey("services.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[time] = mapped_column(Time(timezone=False))
    ends_at: Mapped[time] = mapped_column(Time(timezone=False))


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_booking_order"),
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_booking_status"),
        ExcludeConstraint(
            ("service_id", "="),
            (func.tstzrange(text("starts_at"), text("ends_at"), "[)"), "&&"),
            where=text("status = 'confirmed'"),
            using="gist",
            name="ex_booking_overlap",
        ),
        Index("ix_booking_customer_start", "customer_id", "starts_at"),
        Index("ix_booking_service_start", "service_id", "starts_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    service_id: Mapped[UUID] = mapped_column(ForeignKey("services.id"))
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(9), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
