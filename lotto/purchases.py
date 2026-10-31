"""구매 사실은 사용자 입력으로 기록하며, 결과는 당첨 데이터로 매번 계산한다."""
from datetime import datetime, timezone
from contextlib import nullcontext
import json
from uuid import UUID, uuid4

from .core import Draw, match
from .storage import load_draws


def setup(db):
    db.execute("""CREATE TABLE IF NOT EXISTS purchases (
        id TEXT PRIMARY KEY, target_round INTEGER NOT NULL, numbers TEXT NOT NULL,
        copies INTEGER NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
        updated_at TEXT NOT NULL)""")
    db.commit()


def validate(record):
    if not isinstance(record, dict):
        raise ValueError("구매 기록 형식이 잘못되었습니다.")
    try:
        UUID(record["id"])
        target = record["target_round"]
        nums = record["numbers"]
        if not isinstance(nums, (list, tuple)) or type(target) is not int:
            raise ValueError("회차와 번호 형식을 확인하세요.")
        if len(nums) != 6 or any(type(n) is not int or not 1 <= n <= 45 for n in nums):
            raise ValueError("구매 번호는 1~45 정수 6개여야 합니다.")
        Draw(target, "2002-12-07", tuple(nums), next(n for n in range(1, 46) if n not in nums))
        if type(record["copies"]) is not int or not 1 <= record["copies"] <= 100:
            raise ValueError("구매 수량은 1~100입니다.")
        for field in ("created_at", "updated_at"):
            parsed = datetime.fromisoformat(record[field])
            if parsed.tzinfo is None:
                raise ValueError("기록 시각에 시간대가 필요합니다.")
        if record["status"] not in ("purchased", "void"):
            raise ValueError("구매 상태를 확인하세요.")
    except (KeyError, TypeError, StopIteration, AttributeError) as exc:
        raise ValueError("구매 기록의 필수 값이 누락되거나 잘못되었습니다.") from exc
    return {**{k: record[k] for k in ("id", "target_round", "copies", "created_at", "status", "updated_at")}, "numbers": sorted(record["numbers"])}


def records(db):
    return [{**dict(row), "numbers": json.loads(row["numbers"])} for row in db.execute("SELECT * FROM purchases ORDER BY target_round DESC, created_at DESC, id")]


def import_records(db, payload, *, commit=True):
    if not isinstance(payload, list) or len(payload) > 10_000:
        raise ValueError("구매 기록은 최대 10,000개까지 가져올 수 있습니다.")
    validated = [validate(r) for r in payload]
    if len({r["id"] for r in validated}) != len(validated):
        raise ValueError("백업에 중복된 구매 ID가 있습니다.")
    existing = {r["id"]: r for r in records(db)}
    pending = []
    for r in validated:
        old = existing.get(r["id"])
        if old and any(old[k] != r[k] for k in ("target_round", "numbers", "copies", "created_at")):
            raise ValueError("동일 구매 ID의 내용이 달라 가져오기를 취소했습니다.")
        if old and datetime.fromisoformat(r["updated_at"]) <= datetime.fromisoformat(old["updated_at"]):
            continue
        pending.append(r)
    with (db if commit else nullcontext()):
        for r in pending:
            db.execute("""INSERT INTO purchases VALUES (?,?,?,?,?,?,?) ON CONFLICT(id)
                DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at""",
                (r["id"], r["target_round"], json.dumps(sorted(r["numbers"])), r["copies"], r["created_at"], r["status"], r["updated_at"]))
    return len(pending)


def add(db, target_round, numbers, copies=1, purchase_id=None):
    now = datetime.now(timezone.utc).isoformat()
    r = {"id": purchase_id or str(uuid4()), "target_round": target_round,
         "numbers": sorted(numbers), "copies": copies, "created_at": now,
         "status": "purchased", "updated_at": now}
    validate(r)
    existing = next((p for p in records(db) if p["id"] == r["id"]), None)
    if existing:
        if (existing["target_round"], existing["numbers"], existing["copies"]) != (target_round, sorted(numbers), copies):
            raise ValueError("이미 다른 내용으로 저장된 구매 ID입니다.")
        return r["id"]
    import_records(db, [r])
    return r["id"]


def void(db, purchase_id):
    with db:
        db.execute("UPDATE purchases SET status='void', updated_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), purchase_id))


def report(db):
    draws = {d.round: d for d in load_draws(db)}
    result = []
    for p in records(db):
        draw = draws.get(p["target_round"])
        hits, rank = match(p["numbers"], draw) if draw else (None, None)
        result.append({"ID": p["id"], "회차": p["target_round"], "번호": " · ".join(map(str, p["numbers"])),
                       "수량": p["copies"], "구매액": p["copies"] * 1000,
                       "상태": "구매 완료" if p["status"] == "purchased" else "등록 취소",
                       "일치": hits, "결과": "등록 취소" if p["status"] == "void" else "추첨 결과 미등록" if draw is None else f"{rank}등" if rank else "미당첨",
                       "기록 시각(UTC)": p["created_at"]})
    return result


def history_for_generation(db, target_round):
    return [tuple(p["numbers"]) for p in records(db) if p["status"] == "purchased" and p["target_round"] <= target_round]


def backup(db):
    return json.dumps({"version": 1, "purchases": records(db)}, ensure_ascii=False, indent=2).encode("utf-8")


def restore(db, raw):
    if len(raw) > 5_000_000:
        raise ValueError("백업 파일이 너무 큽니다.")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("지원하지 않는 백업 형식입니다.")
        return import_records(db, payload.get("purchases"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("유효한 구매 이력 JSON 파일이 아닙니다.") from exc
