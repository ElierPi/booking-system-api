from datetime import datetime, time
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ServiceIn(Input):
    name: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="America/Bogota", max_length=80)
    duration_minutes: int = Field(ge=5, le=480)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use a valid IANA timezone, such as America/Bogota") from None
        return value


class ServiceOut(ServiceIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    owner_id: UUID


class WindowIn(Input):
    weekday: int = Field(ge=0, le=6, description="Monday=0, Sunday=6")
    starts_at: time
    ends_at: time

    @model_validator(mode="after")
    def valid_interval(self):
        for value in (self.starts_at, self.ends_at):
            if value.tzinfo is not None or value.second or value.microsecond:
                raise ValueError("Use local times with minute precision and no UTC offset")
        if self.ends_at <= self.starts_at:
            raise ValueError("Window must end after it starts, on the same day")
        return self


class WindowOut(WindowIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    service_id: UUID


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class BookingIn(Input):
    service_id: UUID
    starts_at: AwareDatetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    service_id: UUID
    customer_id: UUID
    starts_at: datetime
    ends_at: datetime
    status: BookingStatus
    created_at: datetime


class BookingPage(BaseModel):
    items: list[BookingOut]
    total: int
    limit: int
    offset: int


class Slot(BaseModel):
    starts_at: datetime
    ends_at: datetime
