from datetime import datetime
import json

import pytest

from lotto import purchases
from lotto.core import Draw, generate
from lotto.refresh import completed_round
from lotto.storage import connect, save_draws


@pytest.fixture
def db(tmp_path):
    db = connect(tmp_path / "purchase.sqlite3")
    purchases.setup(db)
    yield db
    db.close()


def test_purchase_and_result_recalculated_after_refresh(db):
    identity = purchases.add(db, 1248, (1, 2, 3, 4, 5, 7), copies=2)
    assert purchases.report(db)[0]["결과"] == "추첨 결과 미등록"
    save_draws(db, [Draw(1248, "2026-10-31", (1, 2, 3, 4, 5, 6), 7)])
    row = purchases.report(db)[0]
    assert row["결과"] == "2등" and row["구매액"] == 2000
    purchases.void(db, identity)
    assert purchases.report(db)[0]["결과"] == "등록 취소"
    assert purchases.history_for_generation(db, 1249) == []


def test_json_backup_restore_is_idempotent_and_atomic(db, tmp_path):
    purchases.add(db, 1248, (3, 5, 8, 10, 25, 27))
    raw = purchases.backup(db)
    other = connect(tmp_path / "other.sqlite3")
    purchases.setup(other)
    assert purchases.restore(other, raw) == 1
    assert purchases.restore(other, raw) == 0
    payload = json.loads(raw)
    payload["purchases"].append({"id": "broken"})
    with pytest.raises(ValueError):
        purchases.restore(other, json.dumps(payload).encode())
    assert len(purchases.records(other)) == 1
    other.close()


def test_repeat_save_does_not_double_count(db):
    identity = purchases.add(db, 1248, (1, 2, 3, 4, 5, 6))
    purchases.add(db, 1248, (1, 2, 3, 4, 5, 6), purchase_id=identity)
    assert len(purchases.records(db)) == 1
    with pytest.raises(ValueError):
        purchases.add(db, 1249, (1, 2, 3, 4, 5, 6), purchase_id=identity)


def test_next_generation_respects_purchase_history(db):
    ticket = (1, 2, 3, 4, 5, 6)
    purchases.add(db, 1248, ticket)
    purchases.add(db, 1250, (40, 41, 42, 43, 44, 45))
    history = purchases.history_for_generation(db, 1249)
    assert history == [ticket]
    with pytest.raises(ValueError):
        generate(1, include=ticket, purchased=history)
    result = generate(10, purchased=history, history_overlap=2, seed=42)
    assert all(len(set(t) & set(ticket)) <= 2 for t in result)


def test_refresh_uses_korea_time_and_waits_until_saturday_21():
    assert completed_round(datetime.fromisoformat("2026-10-31T20:59:00+09:00")) == 1247
    assert completed_round(datetime.fromisoformat("2026-10-31T21:00:00+09:00")) == 1248
    assert completed_round(datetime.fromisoformat("2026-11-01T01:00:00+09:00")) == 1248
    assert completed_round(datetime.fromisoformat("2026-10-31T11:59:00+00:00")) == 1247
