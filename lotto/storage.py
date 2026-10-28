from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3

from .core import Draw, match

CSV_FIELDS = ["round", "date", "n1", "n2", "n3", "n4", "n5", "n6", "bonus"]


def connect(path: str | Path = "data/lotto.sqlite3"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS draws (
            round INTEGER PRIMARY KEY, date TEXT NOT NULL, numbers TEXT NOT NULL,
            bonus INTEGER NOT NULL, source TEXT NOT NULL, collected_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, target_round INTEGER NOT NULL,
            created_at TEXT NOT NULL, mode TEXT NOT NULL, numbers TEXT NOT NULL,
            settings TEXT NOT NULL
        );
    """)
    return db


def load_draws(db):
    return [Draw(r["round"], r["date"], tuple(json.loads(r["numbers"])), r["bonus"], r["source"]) for r in db.execute("SELECT * FROM draws ORDER BY round")]


def save_draws(db, draws: list[Draw]) -> int:
    if len({d.round for d in draws}) != len(draws):
        raise ValueError("가져올 데이터에 중복 회차가 있습니다.")
    existing = {d.round: d for d in load_draws(db)}
    for d in draws:
        old = existing.get(d.round)
        if old and (old.date, old.numbers, old.bonus) != (d.date, d.numbers, d.bonus):
            raise ValueError(f"{d.round}회가 저장된 결과와 다릅니다. 원본을 확인하세요. 기존 데이터는 유지했습니다.")
    now = datetime.now(timezone.utc).isoformat()
    new = [d for d in draws if d.round not in existing]
    with db:
        db.executemany("INSERT INTO draws VALUES (?,?,?,?,?,?)", [(d.round, d.date, json.dumps(d.numbers), d.bonus, d.source, now) for d in new])
    return len(new)


def read_csv(raw: bytes) -> list[Draw]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not set(CSV_FIELDS) <= set(reader.fieldnames):
        raise ValueError("CSV 열이 필요합니다: " + ",".join(CSV_FIELDS))
    result = []
    for line, row in enumerate(reader, start=2):
        try:
            result.append(Draw(int(row["round"]), row["date"].strip(), tuple(int(row[f"n{i}"]) for i in range(1, 7)), int(row["bonus"]), "CSV 가져오기"))
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"CSV {line}행: {exc}") from exc
    if not result:
        raise ValueError("CSV에 당첨 이력이 없습니다.")
    if len({d.round for d in result}) != len(result):
        raise ValueError("CSV에 중복 회차가 있습니다.")
    return result


def export_draws(draws) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(CSV_FIELDS)
    for d in draws:
        writer.writerow([d.round, d.date, *d.numbers, d.bonus])
    return stream.getvalue().encode("utf-8-sig")


def save_recommendations(db, target_round, mode, tickets, settings):
    if type(target_round) is not int or target_round < 1:
        raise ValueError("대상 회차는 1 이상의 정수여야 합니다.")
    # 저장 직전에도 유효성을 확인하여 잘못된 기록을 막는다.
    for ticket in tickets:
        Draw(target_round, "2002-12-07", tuple(ticket), next(n for n in range(1, 46) if n not in ticket))
    now = datetime.now(timezone.utc).isoformat()
    with db:
        db.executemany("INSERT INTO recommendations(target_round,created_at,mode,numbers,settings) VALUES (?,?,?,?,?)", [(target_round, now, mode, json.dumps(t), json.dumps(settings, ensure_ascii=False)) for t in tickets])


def recommendation_rows(db):
    draws = {d.round: d for d in load_draws(db)}
    rows = []
    for r in db.execute("SELECT * FROM recommendations ORDER BY id DESC"):
        numbers = tuple(json.loads(r["numbers"]))
        draw = draws.get(r["target_round"])
        hits, rank = match(numbers, draw) if draw else (None, None)
        settings = json.loads(r["settings"])
        historical = r["target_round"] <= settings.get("data_latest_round", 0)
        rows.append({"ID": r["id"], "대상 회차": r["target_round"], "생성 시각(UTC)": r["created_at"], "방식": r["mode"], "번호": " · ".join(map(str, numbers)), "일치": hits, "결과": "추첨 결과 미등록" if draw is None else f"{rank}등" if rank else "미당첨", "구분": "과거 회차 연습" if historical else "추천 기록", "설정": r["settings"]})
    return rows
