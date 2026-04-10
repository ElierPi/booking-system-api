from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import visible_booking, windows_for
from app.core.database import get_db
from app.core.security import current_user
from app.models import Service, User
from app.scheduling import candidate_slots, within_horizon
from app.schemas import BookingOut, Input

router = APIRouter(tags=["Bookings"])


class RescheduleIn(Input):
    starts_at: AwareDatetime


@router.post("/bookings/{booking_id}/reschedule", response_model=BookingOut)
def reschedule_booking(
    booking_id: UUID,
    body: RescheduleIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    booking = visible_booking(db, booking_id, user.id, lock=True)
    now = datetime.now(UTC)
    if booking.status != "confirmed" or booking.starts_at <= now:
        raise HTTPException(409, "Only future confirmed bookings can be rescheduled")
    service = db.scalar(
        select(Service).where(Service.id == booking.service_id).with_for_update(read=True)
    )
    day = body.starts_at.astimezone(ZoneInfo(service.timezone)).date()
    if not within_horizon(day, service, now):
        raise HTTPException(422, "Date must be within the next 365 days")
    start = body.starts_at.astimezone(UTC)
    slot = next(
        (
            slot
            for slot in candidate_slots(service, windows_for(db, service.id), day, now)
            if slot.starts_at == start
        ),
        None,
    )
    if slot is None:
        raise HTTPException(422, "Start must match a future slot in the service schedule")
    booking.starts_at, booking.ends_at = slot.starts_at, slot.ends_at
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23P01":
            raise HTTPException(409, "Slot already booked; original booking preserved") from None
        raise
    return booking
