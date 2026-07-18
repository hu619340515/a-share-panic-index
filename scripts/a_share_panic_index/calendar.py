"""A股交易日和数据就绪时间判断。"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import exchange_calendars as exchange_calendar
import pandas as pd

from .models import MarketContext


class TradingCalendar:
    def __init__(self, name: str, timezone: str, ready_time: str):
        self.calendar = exchange_calendar.get_calendar(name)
        self.timezone = ZoneInfo(timezone)
        hour, minute = (int(part) for part in ready_time.split(":"))
        self.ready_time = time(hour=hour, minute=minute)

    def now(self) -> datetime:
        return datetime.now(self.timezone)

    def is_session(self, value: date) -> bool:
        return self.calendar.is_session(pd.Timestamp(value))

    def previous_session(self, value: date) -> date:
        timestamp = pd.Timestamp(value)
        if self.calendar.is_session(timestamp):
            return self.calendar.previous_session(timestamp).date()
        return self.calendar.date_to_session(timestamp, direction="previous").date()

    def sessions_in_range(self, start: date, end: date) -> list[date]:
        sessions = self.calendar.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
        return [timestamp.date() for timestamp in sessions]

    def context(
        self,
        requested_date: date | None = None,
        now: datetime | None = None,
    ) -> MarketContext:
        current = now.astimezone(self.timezone) if now else self.now()
        target = requested_date or current.date()
        if requested_date is not None and requested_date > current.date():
            raise ValueError("指定日期不能晚于当前日期")
        trading_day = self.is_session(target)

        if not trading_day:
            previous = self.previous_session(target)
            return MarketContext(target, previous, False, False, "skipped_non_trading_day")

        if requested_date is None and current.date() == target and current.time() < self.ready_time:
            previous = self.previous_session(target)
            return MarketContext(target, previous, True, False, "market_not_ready")

        return MarketContext(target, target, True, True, "ready")
