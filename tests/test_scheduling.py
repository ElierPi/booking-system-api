from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from app.models import ScheduleWindow, Service
from app.scheduling import candidate_slots, unique_local_instant


def test_dst_skips_nonexistent_and_ambiguous_wall_times():
    zone = ZoneInfo("America/New_York")
    assert unique_local_instant(datetime(2027, 3, 14, 2, 30), zone) is None
    assert unique_local_instant(datetime(2027, 11, 7, 1, 30), zone) is None
    assert unique_local_instant(datetime(2027, 3, 14, 3, 30), zone) == datetime(
        2027, 3, 14, 7, 30, tzinfo=UTC
    )


def test_slots_respect_alignment_and_window_boundary():
    service = Service(timezone="America/Bogota", duration_minutes=45)
    window = ScheduleWindow(weekday=0, starts_at=time(9), ends_at=time(11))
    slots = candidate_slots(service, [window], date(2027, 1, 4), datetime(2027, 1, 1, tzinfo=UTC))
    assert [s.starts_at.hour for s in slots] == [14, 14]
    assert [s.starts_at.minute for s in slots] == [0, 45]
    assert slots[-1].ends_at == datetime(2027, 1, 4, 15, 30, tzinfo=UTC)
