"""미래 회차 예측을 고정된 AJ-R1 계산식으로 작성한다. 기존 파일은 덮어쓰지 않는다."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from lotto.research import ResearchConfig, candidate_pools, initialize_counts, relation_features, select_indices, PAIR_I, PAIR_J, METHODS
from lotto.storage import read_csv


def main():
    destination=Path("research/forward/AJ-D1_round1250.json")
    if destination.exists():
        print(destination.read_text(encoding="utf-8"))
        return
    draws=read_csv(Path("research/official_1_1248.csv").read_bytes())
    draws += [d for d in read_csv(Path("data/official_history.csv").read_bytes()) if d.round>1248]
    from lotto.storage import export_draws
    raw=export_draws(draws)
    assert [d.round for d in draws]==list(range(1,1250))
    cfg=ResearchConfig()
    pool,masks,random_ids=candidate_pools(1250,cfg)[-1]
    numbers=np.asarray([d.numbers for d in draws[-200:]],dtype=np.int8)-1
    p,trend=relation_features(*initialize_counts(numbers,100),cfg)
    frequency=np.log(p)[pool].mean(axis=1)
    pair_change=trend[pool[:,PAIR_I],pool[:,PAIR_J]].mean(axis=1)
    score=frequency+cfg.relation_weight*pair_change
    selected=[random_ids,
              select_indices(masks,np.argsort(-frequency,kind="stable"),cfg.games,cfg.max_overlap),
              select_indices(masks,np.argsort(-score,kind="stable"),cfg.games,cfg.max_overlap)]
    payload={"id":"AJ-D1-forward-1250","target_round":1250,
             "draw_date":(date(2002,12,7)+timedelta(weeks=1249)).isoformat(),
             "created_at":datetime.now(timezone.utc).isoformat(),"model_id":"AJ-D1",
             "status":"frozen_before_draw","history_start":1050,"history_end":1249,
             "data_sha256":hashlib.sha256(raw).hexdigest(),
             "model_code_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "baseline_model_code_sha256":hashlib.sha256(Path("lotto/research.py").read_bytes()).hexdigest(),
             "protocol_sha256":hashlib.sha256(Path("research/AJ_R1_PROTOCOL.md").read_bytes()).hexdigest(),
             "selection_rule":"AJ-D1: default_rng(20261114).permutation(1..45), first 30 numbers reshaped into five sorted six-number tickets. No history score or outcome-dependent filtering. AJ-R1 baselines retained separately; AJ-R2 not applied.",
             "research_predictions":{method:(pool[ids]+1).tolist() for method,ids in zip(METHODS,selected)},
             "recommended_tickets":np.sort(np.random.default_rng(20261114).permutation(np.arange(1,46))[:30].reshape(5,6),axis=1).tolist(),
             "portfolio_seed":20261114,
             "unique_number_count":30,
             "baseline_history_start":1050,
             "caveat":"AJ-D1 is an unvalidated diversification rule, not a predictive model. Five games cover 30 distinct numbers. No purchase recorded. AJ-R1 retrospective results remain unchanged."}
    assert datetime.now(timezone.utc).date()<date.fromisoformat(payload["draw_date"])
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(payload,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
