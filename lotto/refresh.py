from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .collector import fetch_range
from .storage import save_draws


def completed_round(now=None):
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    if now.tzinfo is None:
        raise ValueError("시간대가 있는 시각이 필요합니다.")
    now = now.astimezone(ZoneInfo("Asia/Seoul"))
    # 토요일 21시부터 확인한다. 미발표 회차는 조회 실패로 유지하고 재시도한다.
    last_saturday = now.date() - timedelta(days=(now.weekday() - 5) % 7)
    if now.weekday() == 5 and now.hour < 21:
        last_saturday -= timedelta(days=7)
    return max(0, (last_saturday - datetime(2002, 12, 7).date()).days // 7 + 1)


def refresh(db, start, end):
    if end < start:
        return 0
    return save_draws(db, fetch_range(start, end))
