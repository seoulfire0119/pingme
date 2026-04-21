from __future__ import annotations

import calendar
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Target:
    yeonsu_gbn: str
    year_month: str
    date: str
    room_types: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    base_url: str
    telegram_bot_token: str
    telegram_chat_id: str
    username: str
    password: str
    poll_interval_seconds: int
    targets: tuple[Target, ...]
    storage_dir: Path


def _target_days_in_month(year_month: str) -> list[str]:
    year, month = map(int, year_month.split("."))
    result = []
    for week in calendar.monthcalendar(year, month):
        for weekday in (calendar.FRIDAY, calendar.SATURDAY, calendar.SUNDAY):
            day = week[weekday]
            if day != 0:
                result.append(f"{year}-{month:02d}-{day:02d}")
    return sorted(result)


def _build_targets(months: list[str], resorts: list[str], room_types: tuple[str, ...]) -> tuple[Target, ...]:
    today = date.today().isoformat()
    targets: list[Target] = []
    for year_month in months:
        for d in _target_days_in_month(year_month):
            if d < today:
                continue
            for resort in resorts:
                targets.append(Target(
                    yeonsu_gbn=resort.strip(),
                    year_month=year_month.strip(),
                    date=d,
                    room_types=room_types,
                ))
    return tuple(targets)


def _current_and_next_months() -> list[str]:
    today = date.today()
    months = []
    for delta in (0, 1):
        m = today.month + delta
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        months.append(f"{y}.{m:02d}")
    return months


def load_config(env_path: Path) -> Config:
    load_dotenv(env_path)

    storage_dir = Path(".codex-state")
    storage_dir.mkdir(exist_ok=True)

    months = _current_and_next_months()
    resorts = [r.strip() for r in os.getenv("YEONSU_RESORTS", "00003002,00003003,00003004").split(",") if r.strip()]
    room_types = tuple(rt.strip() for rt in os.getenv("YEONSU_ROOM_TYPES", "A,B,C,O").split(",") if rt.strip())

    return Config(
        base_url=os.getenv("YEONSU_BASE_URL", "https://yeonsu.eseoul.go.kr").rstrip("/"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        username=os.getenv("YEONSU_USERNAME", ""),
        password=os.getenv("YEONSU_PASSWORD", ""),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
        targets=_build_targets(months, resorts, room_types),
        storage_dir=storage_dir,
    )
