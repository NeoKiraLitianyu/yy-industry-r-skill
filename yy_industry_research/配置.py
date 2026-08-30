from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


版本 = "2.0.0"
时区 = ZoneInfo("Asia/Shanghai")


def 当前时间() -> str:
    return datetime.now(时区).isoformat(timespec="seconds")
