from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import current_user
from app.models import Booking, ScheduleWindow, Service, User
from app.scheduling import candidate_slots, within_horizon
from app.schemas import (
    BookingIn,
    BookingOut,
    BookingPage,
    ServiceIn,
    ServiceOut,
    Slot,
    WindowIn,
    WindowOut,
)

router = APIRouter()


def find_service(db: Session, service_id: UUID) -> Service:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(404, "Service not found")
    return service


def lock_owned_service(db: Session, service_id: UUID, owner_id: UUID) -> Service:
    service = db.scalar(
        select(Service)
        .where(
            Service.id == service_id,
            Service.owner_id == owner_id,
        )
        .with_for_update()
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    return service


def windows_for(db: Session, service_id: UUID) -> list[ScheduleWindow]:
    return list(
        db.scalars(
            select(ScheduleWindow)
            .where(ScheduleWindow.service_id == service_id)
            .order_by(ScheduleWindow.weekday, ScheduleWindow.starts_at)
        )
    )


@router.post("/services", response_model=ServiceOut, status_code=201, tags=["Services"])
def create_service(
    body: ServiceIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    service = Service(owner_id=user.id, **body.model_dump())
    db.add(service)
    db.commit()
    return service


@router.get("/services", response_model=list[ServiceOut], tags=["Services"])
def list_services(
    mine: bool = False,
    search: str | None = Query(None, min_length=1, max_length=120),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Service)
    if mine:
        query = query.where(Service.owner_id == user.id)
    if search is not None:
        if not search.strip():
            raise HTTPException(422, "Search must contain non-whitespace characters")
        query = query.where(Service.name.icontains(search.strip(), autoescape=True))
    return db.scalars(query.order_by(Service.name, Service.id).limit(limit).offset(offset)).all()


@router.get("/services/{service_id}", response_model=ServiceOut, tags=["Services"])
def get_service(
    service_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return find_service(db, service_id)


@router.post(
    "/services/{service_id}/windows", response_model=WindowOut, status_code=201, tags=["Schedules"]
)
def add_window(
    service_id: UUID,
    body: WindowIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    lock_owned_service(db, service_id, user.id)
    overlap = db.scalar(
        select(ScheduleWindow.id).where(
            ScheduleWindow.service_id == service_id,
            ScheduleWindow.weekday == body.weekday,
            ScheduleWindow.starts_at < body.ends_at,
            ScheduleWindow.ends_at > body.starts_at,
        )
    )
    if overlap:
        raise HTTPException(409, "Schedule windows cannot overlap")
    window = ScheduleWindow(service_id=service_id, **body.model_dump())
    db.add(window)
    db.commit()
    return window


@router.get("/services/{service_id}/windows", response_model=list[WindowOut], tags=["Schedules"])
def list_windows(
    service_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    find_service(db, service_id)
    return windows_for(db, service_id)


@router.delete("/services/{service_id}/windows/{window_id}", status_code=204, tags=["Schedules"])
def delete_window(
    service_id: UUID,
    window_id: UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    lock_owned_service(db, service_id, user.id)
    window = db.scalar(
        select(ScheduleWindow).where(
            ScheduleWindow.id == window_id,
            ScheduleWindow.service_id == service_id,
        )
    )
    if window is None:
        raise HTTPException(404, "Window not found")
    db.delete(window)
    db.commit()
    return Response(status_code=204)


@router.get("/services/{service_id}/availability", response_model=list[Slot], tags=["Schedules"])
def availability(
    service_id: UUID,
    day: date,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    service = find_service(db, service_id)
    now = datetime.now(UTC)
    if not within_horizon(day, service, now):
        raise HTTPException(422, "Date must be within the next 365 days")
    candidates = candidate_slots(service, windows_for(db, service_id), day, now)
    if not candidates:
        return []
    bookings = db.scalars(
        select(Booking).where(
            Booking.service_id == service_id,
            Booking.status == "confirmed",
            Booking.starts_at < candidates[-1].ends_at,
            Booking.ends_at > candidates[0].starts_at,
        )
    ).all()
    return [
        slot
        for slot in candidates
        if not any(
            booking.starts_at < slot.ends_at and booking.ends_at > slot.starts_at
            for booking in bookings
        )
    ]


@router.post("/bookings", response_model=BookingOut, status_code=201, tags=["Bookings"])
def create_booking(
    body: BookingIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    # SHARE allows competing bookings, while blocking schedule edits (FOR UPDATE).
    service = db.scalar(
        select(Service).where(Service.id == body.service_id).with_for_update(read=True)
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    now = datetime.now(UTC)
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
    booking = Booking(
        service_id=service.id,
        customer_id=user.id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        status="confirmed",
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23P01":
            raise HTTPException(409, "Slot already booked") from None
        raise
    return booking


@router.get("/bookings", response_model=BookingPage, tags=["Bookings"])
def list_bookings(
    as_provider: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    condition = Service.owner_id == user.id if as_provider else Booking.customer_id == user.id
    query = select(Booking).join(Service, Booking.service_id == Service.id).where(condition)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(Booking.starts_at, Booking.id).limit(limit).offset(offset)
    ).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def visible_booking(db: Session, booking_id: UUID, user_id: UUID, lock: bool = False) -> Booking:
    query = (
        select(Booking)
        .join(Service, Booking.service_id == Service.id)
        .where(
            Booking.id == booking_id,
            or_(Booking.customer_id == user_id, Service.owner_id == user_id),
        )
    )
    if lock:
        query = query.with_for_update(of=Booking)
    booking = db.scalar(query)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    return booking


@router.get("/bookings/{booking_id}", response_model=BookingOut, tags=["Bookings"])
def get_booking(
    booking_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return visible_booking(db, booking_id, user.id)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut, tags=["Bookings"])
def cancel_booking(
    booking_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    booking = visible_booking(db, booking_id, user.id, lock=True)
    if booking.status == "cancelled":
        return booking
    if booking.starts_at <= datetime.now(UTC):
        raise HTTPException(409, "A started booking cannot be cancelled")
    booking.status = "cancelled"
    db.commit()
    return booking
