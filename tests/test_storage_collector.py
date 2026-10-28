import json

import pytest

from lotto import collector
from lotto.core import Draw
from lotto.storage import (connect, export_draws, load_draws, read_csv,
                           recommendation_rows, save_draws, save_recommendations)


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "test.sqlite3")
    yield connection
    connection.close()


def draw(round=1):
    return Draw(round, "2002-12-07", (1, 2, 3, 4, 5, 6), 7, "TEST")


def test_csv_round_trip():
    records = [draw()]
    result = read_csv(export_draws(records))
    assert result[0].numbers == records[0].numbers
    assert result[0].bonus == 7
    with pytest.raises(ValueError, match="중복 회차"):
        read_csv(export_draws(records * 2))


def test_invalid_csv_row_and_headers():
    with pytest.raises(ValueError, match="CSV 열"):
        read_csv(b"round,date\n1,2002-12-07")
    for raw in [b"round,date,n1,n2,n3,n4,n5,n6,bonus\n1,2002-12-07,1,1,3,4,5,6,7", b"round,date,n1,n2,n3,n4,n5,n6,bonus\n1,bad,1,2,3,4,5,6,7"]:
        with pytest.raises(ValueError, match="2행"):
            read_csv(raw)


def test_conflict_import_is_atomic(db):
    save_draws(db, [draw()])
    conflict = Draw(1, "2002-12-07", (1, 2, 3, 4, 5, 8), 7)
    with pytest.raises(ValueError, match="저장된 결과와"):
        save_draws(db, [draw(2), conflict])
    assert len(load_draws(db)) == 1
    assert save_draws(db, [draw()]) == 0


def test_saved_recommendation_resolves_after_draw_import(db):
    save_recommendations(db, 1, "균등 무작위", [(1, 2, 3, 4, 5, 7)], {})
    assert recommendation_rows(db)[0]["결과"] == "추첨 결과 미등록"
    save_draws(db, [draw()])
    assert recommendation_rows(db)[0]["결과"] == "2등"


def test_official_response_parser():
    payload = {"data": {"list": [{"ltEpsd": 1247, "ltRflYmd": "20261024", **{f"tm{i}WnNo": n for i, n in enumerate([8, 14, 21, 22, 42, 45], 1)}, "bnsWnNo": 24}]}}
    result = collector.parse_response(payload)
    assert result[0].round == 1247 and result[0].date == "2026-10-24"
    assert result[0].numbers == (8, 14, 21, 22, 42, 45)
    for bad in [{}, {"data": {"list": []}}, {"data": {"list": [{}]}}]:
        with pytest.raises(ValueError):
            collector.parse_response(bad)


def test_fetch_range_reuses_batch_results(monkeypatch):
    calls = []

    def fake_fetch(requested):
        calls.append(requested)
        return [draw(i) for i in range(max(1, requested - 9), requested + 1)]

    monkeypatch.setattr(collector, "fetch_batch", fake_fetch)
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    result = collector.fetch_range(1, 21)
    assert len(result) == 21 and len(calls) == 3
    assert [d.round for d in result] == list(range(1, 22))


def test_future_or_missing_requested_round_is_rejected(monkeypatch):
    monkeypatch.setattr(collector, "fetch_batch", lambda _: [draw(1)])
    with pytest.raises(RuntimeError, match="응답에 없습니다"):
        collector.fetch_range(1, 2)
