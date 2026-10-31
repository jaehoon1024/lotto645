from copy import deepcopy
import json

import pytest

from lotto import purchases,workspace
from lotto.storage import connect,save_recommendations


@pytest.fixture
def db(tmp_path):
    connection=connect(tmp_path / "workspace.sqlite3")
    workspace.setup(connection)
    yield connection
    connection.close()


def populate(db):
    purchases.add(db,1248,(3,5,8,10,25,27))
    save_recommendations(db,1249,"AJ-R1 연구 추천",[(9,15,21,27,38,42)],{"frozen_id":"AJ-R1-forward-1249"})
    workspace.add_note(db,"지속성 가설","한 번에 한 가지씩 바꿉니다.","AJ-R2",1249)


def test_full_backup_restores_three_record_types_and_is_idempotent(db,tmp_path):
    populate(db)
    payload=workspace.backup(db)
    other=connect(tmp_path / "other.sqlite3")
    workspace.setup(other)
    assert workspace.restore(other,payload)=={"purchases":1,"recommendations":1,"notes":1}
    assert workspace.restore(other,payload)=={"purchases":0,"recommendations":0,"notes":0}
    assert workspace.export_payload(other)==workspace.export_payload(db)
    other.close()


def test_existing_purchase_v1_backup_migrates(db):
    purchases.add(db,1248,(1,2,3,4,5,6))
    raw=purchases.backup(db)
    assert workspace.restore(db,raw)=={"purchases":0,"recommendations":0,"notes":0}


def test_invalid_recommendation_prevents_partial_purchase_import(db,tmp_path):
    source=connect(tmp_path / "source.sqlite3")
    workspace.setup(source)
    populate(source)
    payload=workspace.export_payload(source)
    payload["recommendations"][0]["numbers"]=[1,1,1,1,1,1]
    with pytest.raises(ValueError):
        workspace.import_payload(db,payload)
    assert purchases.records(db)==[]
    source.close()


def test_conflicting_note_is_rejected_without_overwriting(db):
    populate(db)
    payload=deepcopy(workspace.export_payload(db))
    payload["notes"][0]["body"]="다른 내용"
    with pytest.raises(ValueError):
        workspace.import_payload(db,payload)
    assert workspace.notes(db)[0]["body"]=="한 번에 한 가지씩 바꿉니다."


def test_public_forward_prediction_is_frozen_and_not_aj_r2():
    from pathlib import Path
    payload=json.loads(Path("research/forward/AJ-R1_round1249.json").read_text(encoding="utf-8"))
    assert payload["target_round"]==1249 and payload["history_end"]==1248
    assert payload["model_id"]=="AJ-R1"
    tickets=payload["recommended_tickets"]
    assert len(tickets)==5 and len(set(map(tuple,tickets)))==5
    assert tickets==payload["research_predictions"]["AJ-R1"][:5]
    assert all(len(set(t))==6 and all(1<=n<=45 for n in t) for t in tickets)
