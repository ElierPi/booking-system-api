"""Create a provider and weekday schedule: python -m app.demo."""

from datetime import time
from getpass import getpass

from sqlalchemy import select

from app.auth import Register
from app.core.database import SessionLocal
from app.core.security import password_hasher
from app.models import ScheduleWindow, Service, User


def main():
    body = Register(
        email=input("Provider email: ").strip(), password=getpass("Password (12+ chars): ")
    )
    with SessionLocal.begin() as db:
        if db.scalar(select(User.id).where(User.email == str(body.email))):
            raise SystemExit("Email already exists. Use a new email; nothing was modified.")
        user = User(
            email=str(body.email),
            password_hash=password_hasher.hash(body.password.get_secret_value()),
        )
        db.add(user)
        db.flush()
        service = Service(
            owner_id=user.id,
            name="Backend consultation",
            timezone="America/Bogota",
            duration_minutes=60,
        )
        db.add(service)
        db.flush()
        db.add_all(
            ScheduleWindow(service_id=service.id, weekday=day, starts_at=time(9), ends_at=time(17))
            for day in range(5)
        )
        service_id = service.id
    print(f"Demo created. Service: {service_id}; Monday-Friday, 09:00-17:00 America/Bogota.")


if __name__ == "__main__":
    main()
