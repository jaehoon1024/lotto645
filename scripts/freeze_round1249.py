"""미래 회차 예측을 고정된 AJ-R1 계산식으로 작성한다. 기존 파일은 덮어쓰지 않는다."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from lotto.research import ResearchConfig, candidate_pools, initialize_counts, relation_features, select_indices, PAIR_I, PAIR_J, METHODS
from lotto.storage import read_csv


def main():
    destination=Path("research/forward/AJ-R1_round1249.json")
    if destination.exists():
        print(destination.read_text(encoding="utf-8"))
        return
    raw=Path("research/official_1_1248.csv").read_bytes()
    draws=read_csv(raw)
    assert [d.round for d in draws]==list(range(1,1249))
    cfg=ResearchConfig()
    pool,masks,random_ids=candidate_pools(1249,cfg)[-1]
    numbers=np.asarray([d.numbers for d in draws[-200:]],dtype=np.int8)-1
    p,trend=relation_features(*initialize_counts(numbers,100),cfg)
    frequency=np.log(p)[pool].mean(axis=1)
    pair_change=trend[pool[:,PAIR_I],pool[:,PAIR_J]].mean(axis=1)
    score=frequency+cfg.relation_weight*pair_change
    selected=[random_ids,
              select_indices(masks,np.argsort(-frequency,kind="stable"),cfg.games,cfg.max_overlap),
              select_indices(masks,np.argsort(-score,kind="stable"),cfg.games,cfg.max_overlap)]
    payload={"id":"AJ-R1-forward-1249","target_round":1249,
             "draw_date":(date(2002,12,7)+timedelta(weeks=1248)).isoformat(),
             "created_at":datetime.now(timezone.utc).isoformat(),"model_id":"AJ-R1",
             "status":"frozen_before_draw","history_start":1049,"history_end":1248,
             "data_sha256":hashlib.sha256(raw).hexdigest(),
             "model_code_sha256":hashlib.sha256(Path("lotto/research.py").read_bytes()).hexdigest(),
             "protocol_sha256":hashlib.sha256(Path("research/AJ_R1_PROTOCOL.md").read_bytes()).hexdigest(),
             "selection_rule":"First five of the fixed ten AJ-R1 research tickets; no AJ-R2 applied.",
             "research_predictions":{method:(pool[ids]+1).tolist() for method,ids in zip(METHODS,selected)},
             "recommended_tickets":(pool[selected[2][:5]]+1).tolist(),
             "caveat":"AJ-R1 has no demonstrated advantage in its first retrospective experiment. These are research recommendations, not a higher-probability claim."}
    assert datetime.now(timezone.utc).date()<date.fromisoformat(payload["draw_date"])
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(payload,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
