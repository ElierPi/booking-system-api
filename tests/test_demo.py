import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app import demo
from app.core.database import SessionLocal
from app.models import ScheduleWindow, Service, User


def test_demo_creates_weekday_schedule_and_duplicate_run_is_atomic(client, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "demo@example.com")
    monkeypatch.setattr(demo, "getpass", lambda _: "Demo-password-12345")
    demo.main()
    with pytest.raises(SystemExit, match="Email already exists"):
        demo.main()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Service)) == 1
        windows = db.scalars(select(ScheduleWindow).order_by(ScheduleWindow.weekday)).all()
        assert [window.weekday for window in windows] == list(range(5))
        service = db.scalar(select(Service))
        assert service.timezone == "America/Bogota" and service.duration_minutes == 60
        assert all(window.service_id == service.id for window in windows)
    assert (
        client.post(
            "/api/v1/auth/token",
            data={
                "username": "demo@example.com",
                "password": "Demo-password-12345",
            },
        ).status_code
        == 200
    )


def test_demo_validates_credentials_before_writing(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "invalid")
    monkeypatch.setattr(demo, "getpass", lambda _: "short")
    with pytest.raises(ValidationError):
        demo.main()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
