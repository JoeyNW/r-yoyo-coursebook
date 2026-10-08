"""Request bodies."""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_TIME = re.compile(r'^\d{2}:\d{2}$')


def _time(value: str) -> str:
    if not _TIME.fullmatch(value):
        raise ValueError('time')
    hour, minute = (int(part) for part in value.split(':'))
    if hour > 23 or minute > 59:
        raise ValueError('time')
    return f'{hour:02d}:{minute:02d}'


def _date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError('date') from exc


def _optional_date(value: str | None) -> str | None:
    if value is None or value == '':
        return None
    return _date(value)


def _required_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError('blank')
    return text


class RegisterIn(BaseModel):
    login_name: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=40)

    @field_validator('login_name')
    @classmethod
    def normalize_login(cls, value: str) -> str:
        name = value.strip().casefold()
        if not name or any(char.isspace() for char in name):
            raise ValueError('login')
        return name

    @field_validator('display_name')
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _required_text(value)


class LoginIn(BaseModel):
    login_name: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @field_validator('login_name')
    @classmethod
    def normalize_login(cls, value: str) -> str:
        return value.strip().casefold()


class FamilyIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)

    @field_validator('name')
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _required_text(value)


class InviteAcceptIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)

    @field_validator('code')
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class ScheduleIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    local_time: str
    effective_from: str | None = None

    @field_validator('local_time')
    @classmethod
    def check_time(cls, value: str) -> str:
        return _time(value)

    @field_validator('effective_from')
    @classmethod
    def check_from(cls, value: str | None) -> str | None:
        return _optional_date(value)


class CourseIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = None
    teacher: str = Field(default='', max_length=40)
    location: str = Field(default='', max_length=80)
    notes: str = Field(default='', max_length=500)
    schedules: list[ScheduleIn] = Field(default_factory=list, max_length=14)

    @field_validator('name')
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _required_text(value)


class CoursePatch(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    color: str | None = None
    teacher: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)
    active: bool | None = None

    @field_validator('name')
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _required_text(value)


class PackageIn(BaseModel):
    title: str = Field(min_length=1, max_length=40)
    total_units: int = Field(gt=0, le=9999)
    opening_consumed_units: int = Field(default=0, ge=0, le=9999)
    start_date: str | None = None
    expiry_date: str | None = None
    notes: str = Field(default='', max_length=500)

    @field_validator('title')
    @classmethod
    def strip_title(cls, value: str) -> str:
        return _required_text(value)

    @field_validator('start_date', 'expiry_date')
    @classmethod
    def check_dates(cls, value: str | None) -> str | None:
        return _optional_date(value)


class PackagePatch(BaseModel):
    title: str | None = Field(default=None, max_length=40)
    total_units: int | None = Field(default=None, gt=0, le=9999)
    opening_consumed_units: int | None = Field(default=None, ge=0, le=9999)
    start_date: str | None = None
    expiry_date: str | None = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator('title')
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _required_text(value)

    @field_validator('start_date', 'expiry_date')
    @classmethod
    def check_dates(cls, value: str | None) -> str | None:
        return _optional_date(value)


class ReplaceScheduleIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    local_time: str
    effective_on: str

    @field_validator('local_time')
    @classmethod
    def check_time(cls, value: str) -> str:
        return _time(value)

    @field_validator('effective_on')
    @classmethod
    def check_on(cls, value: str) -> str:
        return _date(value)


class EndScheduleIn(BaseModel):
    last_date: str

    @field_validator('last_date')
    @classmethod
    def check_last(cls, value: str) -> str:
        return _date(value)


class LessonIn(BaseModel):
    course_id: int
    local_date: str
    local_time: str
    source: Literal['planned', 'manual']
    status: Literal['attended', 'leave', 'canceled']
    charge: bool = False
    notes: str = Field(default='', max_length=500)

    @field_validator('local_date')
    @classmethod
    def check_date(cls, value: str) -> str:
        return _date(value)

    @field_validator('local_time')
    @classmethod
    def check_time(cls, value: str) -> str:
        return _time(value)


class LessonPatch(BaseModel):
    status: Literal['attended', 'leave', 'canceled']
    charge: bool = False
    notes: str | None = Field(default=None, max_length=500)
    confirm: bool = False


class ConfirmIn(BaseModel):
    confirm: bool = False
