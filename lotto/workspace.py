"""구매·추천·연구 메모를 함께 보관하는 개인 작업 공간."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID, uuid4

from . import purchases
from .core import Draw


def setup(db):
    purchases.setup(db)
    db.execute("""CREATE TABLE IF NOT EXISTS activity_notes (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL,
        body TEXT NOT NULL, model_id TEXT NOT NULL, target_round INTEGER)""")
    db.commit()


def check_time(value):
    if not isinstance(value,str) or datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("시간대가 있는 기록 시각이 필요합니다.")
    return value


def checked_recommendation(record):
    try:
        target = record["target_round"]
        numbers = tuple(record["numbers"])
        Draw(target,"2002-12-07",numbers,next(n for n in range(1,46) if n not in numbers))
        if not isinstance(record["mode"],str) or not 1 <= len(record["mode"]) <= 100:
            raise ValueError("추천 방식의 형식이 잘못되었습니다.")
        if not isinstance(record["settings"],dict) or len(json.dumps(record["settings"])) > 50_000:
            raise ValueError("추천 설정의 형식이 잘못되었습니다.")
        result = {"target_round":target,"numbers":sorted(numbers),"created_at":check_time(record["created_at"]),
                  "mode":record["mode"],"settings":record["settings"]}
        result["id"] = hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
        if record.get("id",result["id"]) != result["id"]:
            raise ValueError("추천 기록의 ID와 내용이 다릅니다.")
        return result
    except (KeyError,TypeError,StopIteration) as exc:
        raise ValueError("추천 기록의 필수 값이 잘못되었습니다.") from exc


def recommendations(db):
    return [
        checked_recommendation({"target_round":r["target_round"],"created_at":r["created_at"],"mode":r["mode"],
                                "numbers":json.loads(r["numbers"]),"settings":json.loads(r["settings"])})
        for r in db.execute("SELECT * FROM recommendations ORDER BY created_at,id")]


def checked_note(record):
    try:
        UUID(record["id"])
        check_time(record["created_at"])
        if not isinstance(record["title"],str) or not 1 <= len(record["title"].strip()) <= 200:
            raise ValueError("메모 제목은 1~200자입니다.")
        if not isinstance(record["body"],str) or len(record["body"]) > 10_000:
            raise ValueError("메모 본문은 10,000자 이내입니다.")
        if record["model_id"] not in ("전체","AJ-R1","AJ-R2"):
            raise ValueError("메모의 연구 모델을 확인하세요.")
        target = record["target_round"]
        if target is not None and (type(target) is not int or target < 1):
            raise ValueError("대상 회차는 1 이상의 정수입니다.")
        return {k:record[k] for k in ("id","created_at","title","body","model_id","target_round")}
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("메모의 필수 값이 잘못되었습니다.") from exc


def notes(db):
    return [dict(r) for r in db.execute("SELECT * FROM activity_notes ORDER BY created_at DESC,id")]


def add_note(db,title,body,model_id="전체",target_round=None):
    note = checked_note({"id":str(uuid4()),"created_at":datetime.now(timezone.utc).isoformat(),
                         "title":title.strip(),"body":body,"model_id":model_id,"target_round":target_round})
    with db:
        db.execute("INSERT INTO activity_notes VALUES (?,?,?,?,?,?)",tuple(note.values()))
    return note["id"]


def export_payload(db):
    return {"version":2,"purchases":purchases.records(db),"recommendations":recommendations(db),"notes":notes(db)}


def import_payload(db,payload):
    if not isinstance(payload,dict) or payload.get("version") not in (1,2):
        raise ValueError("지원하지 않는 작업 공간 백업입니다.")
    bought = payload.get("purchases",[])
    recs = payload.get("recommendations",[]) if payload["version"] == 2 else []
    memo = payload.get("notes",[]) if payload["version"] == 2 else []
    if any(not isinstance(part,list) or len(part)>10_000 for part in (bought,recs,memo)):
        raise ValueError("각 기록 유형은 최대 10,000개입니다.")
    recs = [checked_recommendation(r) for r in recs]
    memo = [checked_note(n) for n in memo]
    existing_recs = {r["id"] for r in recommendations(db)}
    existing_notes = {n["id"]:n for n in notes(db)}
    checked_notes = existing_notes.copy()
    for n in memo:
        if n["id"] in checked_notes and n != checked_notes[n["id"]]:
            raise ValueError("같은 ID의 메모 내용이 달라 복원을 중단했습니다.")
        checked_notes[n["id"]] = n
    inserted_recs = inserted_notes = 0
    with db:
        inserted_purchases = purchases.import_records(db,bought,commit=False)
        for r in recs:
            if r["id"] not in existing_recs:
                db.execute("INSERT INTO recommendations(target_round,created_at,mode,numbers,settings) VALUES (?,?,?,?,?)",
                           (r["target_round"],r["created_at"],r["mode"],json.dumps(r["numbers"]),json.dumps(r["settings"],ensure_ascii=False)))
                existing_recs.add(r["id"])
                inserted_recs += 1
        for n in memo:
            if n["id"] not in existing_notes:
                db.execute("INSERT INTO activity_notes VALUES (?,?,?,?,?,?)",tuple(n.values()))
                existing_notes[n["id"]] = n
                inserted_notes += 1
    return {"purchases":inserted_purchases,"recommendations":inserted_recs,"notes":inserted_notes}


def backup(db):
    return json.dumps(export_payload(db),ensure_ascii=False,indent=2).encode("utf-8")


def restore(db,raw):
    if len(raw)>5_000_000:
        raise ValueError("백업 파일은 5MB 이내여야 합니다.")
    try:
        return import_payload(db,json.loads(raw.decode("utf-8-sig")))
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError("유효한 JSON 백업 파일이 아닙니다.") from exc
