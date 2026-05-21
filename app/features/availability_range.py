from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import find_service, windows_for
from app.core.database import get_db
from app.core.security import current_user
from app.models import Booking, User
from app.scheduling import candidate_slots, within_horizon
from app.schemas import Slot

router = APIRouter(tags=["Schedules"])


class DayAvailability(BaseModel):
    day: date
    slots: list[Slot]


@router.get("/services/{service_id}/availability-range", response_model=list[DayAvailability])
def availability_range(
    service_id: UUID,
    day_from: date,
    day_to: date,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not 0 <= (day_to - day_from).days <= 30:
        raise HTTPException(422, "Choose an inclusive range of at most 31 days")
    service = find_service(db, service_id)
    now = datetime.now(UTC)
    if not all(within_horizon(day, service, now) for day in (day_from, day_to)):
        raise HTTPException(422, "Dates must be within the next 365 days")
    windows = windows_for(db, service_id)
    days = []
    for delta in range((day_to - day_from).days + 1):
        day = day_from + timedelta(days=delta)
        days.append(DayAvailability(day=day, slots=candidate_slots(service, windows, day, now)))
    candidates = sorted(
        (slot for day in days for slot in day.slots), key=lambda slot: slot.starts_at
    )
    if not candidates:
        return days
    booked = db.scalars(
        select(Booking)
        .where(
            Booking.service_id == service_id,
            Booking.status == "confirmed",
            Booking.starts_at < candidates[-1].ends_at,
            Booking.ends_at > candidates[0].starts_at,
        )
        .order_by(Booking.starts_at)
    ).all()
    # Confirmed bookings cannot overlap; a monotonic sweep avoids N*M comparisons.
    index = 0
    available = set()
    for slot in candidates:
        while index < len(booked) and booked[index].ends_at <= slot.starts_at:
            index += 1
        if index == len(booked) or booked[index].starts_at >= slot.ends_at:
            available.add(slot.starts_at)
    return [
        DayAvailability(day=day.day, slots=[s for s in day.slots if s.starts_at in available])
        for day in days
    ]
