"""Calendar rules separated from transport and persistence."""

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import ScheduleWindow, Service
from app.schemas import Slot


def unique_local_instant(local: datetime, zone: ZoneInfo) -> datetime | None:
    """Skip nonexistent or ambiguous wall times rather than silently choosing a DST fold."""
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        return None
    utc = first.astimezone(UTC)
    if utc.astimezone(zone).replace(tzinfo=None) != local:
        return None
    return utc


def candidate_slots(
    service: Service,
    windows: Iterable[ScheduleWindow],
    day: date,
    now: datetime,
) -> list[Slot]:
    zone = ZoneInfo(service.timezone)
    duration = timedelta(minutes=service.duration_minutes)
    slots: list[Slot] = []
    for window in windows:
        if window.weekday != day.weekday():
            continue
        cursor = datetime.combine(day, window.starts_at)
        end = datetime.combine(day, window.ends_at)
        while cursor + duration <= end:
            start_utc = unique_local_instant(cursor, zone)
            end_utc = unique_local_instant(cursor + duration, zone)
            # A slot must have the configured duration in real elapsed time, too.
            if (
                start_utc is not None
                and end_utc is not None
                and end_utc - start_utc == duration
                and start_utc > now
            ):
                slots.append(Slot(starts_at=start_utc, ends_at=end_utc))
            cursor += duration
    return sorted(slots, key=lambda slot: slot.starts_at)


def within_horizon(day: date, service: Service, now: datetime) -> bool:
    today = now.astimezone(ZoneInfo(service.timezone)).date()
    return today <= day <= today + timedelta(days=365)
