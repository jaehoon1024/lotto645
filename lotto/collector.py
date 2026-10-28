"""동행복권 결과 페이지의 조회 응답을 검증하여 변환한다.

공식적으로 보장된 공개 API가 아니므로 실패 시 CSV 입력을 사용한다.
"""
from __future__ import annotations

from datetime import datetime
import json
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core import Draw

ENDPOINT = "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do"
SOURCE = "https://www.dhlottery.co.kr/lt645/result"


def parse_response(payload: dict) -> list[Draw]:
    try:
        rows = payload["data"]["list"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("조회 결과가 비어 있습니다.")
        result = []
        for row in rows:
            day = datetime.strptime(str(row["ltRflYmd"]), "%Y%m%d").date().isoformat()
            result.append(Draw(int(row["ltEpsd"]), day, tuple(int(row[f"tm{i}WnNo"]) for i in range(1, 7)), int(row["bnsWnNo"]), SOURCE))
        if len({d.round for d in result}) != len(result):
            raise ValueError("조회 응답에 중복 회차가 있습니다.")
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"공식 조회 응답을 검증하지 못했습니다: {exc}") from exc


def fetch_batch(round_number: int) -> list[Draw]:
    url = ENDPOINT + "?" + urlencode({"srchDir": "center", "srchLtEpsd": round_number})
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 LottoLab/1.0", "Referer": SOURCE, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("응답 크기가 예상 범위를 초과했습니다.")
        return parse_response(json.loads(raw.decode("utf-8")))
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"{round_number}회 결과를 가져오지 못했습니다. 네트워크 또는 사이트 응답을 확인하고 CSV 입력을 사용하세요. ({exc})") from exc


def fetch_range(start: int, end: int, progress=None) -> list[Draw]:
    if not 1 <= start <= end or end - start >= 1500:
        raise ValueError("1 이상의 회차를 시작≤끝으로 입력하세요. 한 번에 최대 1,500회입니다.")
    pending = set(range(start, end + 1))
    found = {}
    total = len(pending)
    while pending:
        requested = max(pending)
        batch = fetch_batch(requested)
        if requested not in {d.round for d in batch}:
            raise RuntimeError(f"요청한 {requested}회 결과가 응답에 없습니다. 아직 추첨되지 않았거나 조회가 제한된 회차일 수 있습니다. 저장하지 않았습니다.")
        for d in batch:
            if start <= d.round <= end:
                if d.round in found and found[d.round] != d:
                    raise RuntimeError("동일 회차의 응답이 달라 수집을 중단했습니다.")
                found[d.round] = d
                pending.discard(d.round)
        if progress:
            progress(total - len(pending), total)
        if pending:
            time.sleep(0.35)
    return sorted(found.values(), key=lambda d: d.round)
