#!/usr/bin/env python3
"""Quick test of operating hours logic."""

from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
OPERATING_START_HOUR = 17
OPERATING_END_HOUR = 4

def is_within_operating_hours() -> bool:
    h = datetime.now(IST).hour
    return h >= OPERATING_START_HOUR or h < OPERATING_END_HOUR

def seconds_until_window_opens() -> int:
    now = datetime.now(IST)
    next_open = now.replace(hour=OPERATING_START_HOUR, minute=0, second=0, microsecond=0)
    if now >= next_open:
        next_open += timedelta(days=1)
    return max(0, int((next_open - now).total_seconds()))

if __name__ == "__main__":
    now_utc = datetime.now(timezone.utc)
    now_ist = datetime.now(IST)

    print(f"Current time (UTC): {now_utc.isoformat()}")
    print(f"Current time (IST): {now_ist.isoformat()}")
    print(f"Current hour (IST): {now_ist.hour}")
    print()
    print(f"Within operating hours (17:00–04:00 IST)? {is_within_operating_hours()}")

    if not is_within_operating_hours():
        wait = seconds_until_window_opens()
        h, m = divmod(wait // 60, 60)
        print(f"Seconds until window opens: {wait}")
        print(f"Time until window opens: {h}h {m}m")
    else:
        print("Currently within operating window — polling is active")
