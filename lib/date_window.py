# -*- coding: utf-8 -*-
"""Date windows for T7 aggregate (数据与规则规格.md §3.6 / §4.3 dateWithin).

week  = previous natural week (Monday–Sunday)
month = previous natural month
range = caller-supplied inclusive [from, to]
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional, Tuple

ISO = re.compile(r'(20\d{2}-\d{2}-\d{2})')
Window = Tuple[date, date]


def parse_iso_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    m = ISO.search(text)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def previous_week(today: Optional[date] = None) -> Window:
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(days=7)
    return start, start + timedelta(days=6)


def previous_month(today: Optional[date] = None) -> Window:
    today = today or date.today()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev


def resolve_window(period: str, date_from: str = '', date_to: str = '',
                   today: Optional[date] = None) -> Window:
    period = (period or '').strip().lower()
    start = parse_iso_date(date_from)
    end = parse_iso_date(date_to)
    if start and end:
        if end < start:
            start, end = end, start
        return start, end
    if period == 'month':
        win = previous_month(today)
    else:
        win = previous_week(today)
    if start and not end:
        return start, win[1] if start <= win[1] else start
    if end and not start:
        return win[0] if win[0] <= end else end, end
    return win


def in_window(value: Any, window: Optional[Window]) -> bool:
    if window is None:
        return True
    d = parse_iso_date(value)
    if d is None:
        return False
    return window[0] <= d <= window[1]


def window_label(window: Window) -> str:
    return '%s～%s' % (window[0].isoformat(), window[1].isoformat())
