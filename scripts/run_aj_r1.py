"""실행: python -m scripts.run_aj_r1 [--null-repeats 199]"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from lotto.research import ResearchConfig, candidate_pools, config_dict, evaluate, fair_history, validate_archive
from lotto.storage import read_csv


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--null-repeats",type=int,default=199)
    parser.add_argument("--output",default="research/results/AJ-R1")
    args = parser.parse_args()
    if args.null_repeats < 0:
        raise ValueError("null-repeats must be nonnegative")
    cfg = ResearchConfig(null_repeats=args.null_repeats)
    dataset = Path("research/official_1_1248.csv")
    draws = read_csv(dataset.read_bytes())
    validate_archive(draws)
    if len(draws) != 1248:
        raise ValueError("The fixed experiment requires exactly rounds 1..1248")
    out = Path(args.output)
    if (out / "summary.json").exists():
        raise ValueError("Completed results are preserved. Use --output with a new directory for a reproduction.")
    out.mkdir(parents=True,exist_ok=True)
    manifest = {"model":"AJ-R1", "kind":"retrospective_exploration", "started_at":datetime.now(timezone.utc).isoformat(),
                "config":config_dict(cfg), "data_sha256":digest(dataset),
                "protocol_sha256":digest("research/AJ_R1_PROTOCOL.md"), "code_sha256":digest("lotto/research.py"),
                "data_source":"https://www.dhlottery.co.kr/lt645/result"}
    (out / "manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    start = time.monotonic()
    pools = candidate_pools(len(draws),cfg)
    numbers = np.asarray([d.numbers for d in draws],dtype=np.int8) - 1
    bonuses = np.asarray([d.bonus for d in draws],dtype=np.int8) - 1
    real = evaluate(numbers,pools,cfg,bonuses=bonuses)
    print("Actual experiment complete: " + json.dumps({k:v for k,v in real.items() if k != "rows"}),flush=True)
    frame = pd.DataFrame(real["rows"])
    frame.to_csv(out / "per_round.csv",index=False,encoding="utf-8-sig")
    frame["구간 시작"] = 201 + ((frame["회차"] - 201) // cfg.block) * cfg.block
    blocks = frame.groupby(["구간 시작","방식"],sort=False).agg(
        구간끝=("회차","max"),회차수=("회차","size"),평균일치=("평균 일치","mean"),
        당첨게임=("3개 이상 게임","sum"),당첨회차=("한 게임 이상 당첨","sum"),
        **{f"{r}등":(f"{r}등 게임","sum") for r in range(1,6)}).reset_index()
    blocks.to_csv(out / "blocks_100.csv",index=False,encoding="utf-8-sig")
    null_rows = []
    for repeat in range(cfg.null_repeats):
        synthetic = fair_history(len(draws),cfg.seed + 10_000_000 + repeat)
        score = evaluate(synthetic,pools,cfg,keep_rows=False)
        null_rows.append({"repeat":repeat + 1,"primary_delta":score["primary_delta"],"random_delta":score["random_delta"]})
        if (repeat + 1) % 5 == 0 or repeat + 1 == cfg.null_repeats:
            pd.DataFrame(null_rows).to_csv(out / "fair_null.csv",index=False)
            print(f"Fair null {repeat + 1}/{cfg.null_repeats}; elapsed {time.monotonic() - start:.1f}s",flush=True)
    null = np.asarray([r["primary_delta"] for r in null_rows])
    p_value = float((1 + (null >= real["primary_delta"]).sum()) / (len(null) + 1)) if len(null) else None
    pivot = blocks.pivot(index="구간 시작",columns="방식",values="평균일치")
    summary = {"means":real["means"],"primary_delta":real["primary_delta"],"random_delta":real["random_delta"],
               "tested_rounds":len(draws) - 200,"complete_blocks":int((blocks[blocks["방식"]=="AJ-R1"]["회차수"]==100).sum()),
               "partial_block_rounds":48,"positive_blocks_vs_frequency":int((pivot["AJ-R1"]>pivot["빈도 기준"]).sum()),
               "total_blocks":len(pivot),"one_sided_fair_null_p":p_value,"null_repeats":len(null),
               "null_delta_2_5_97_5_percentiles":np.quantile(null,[0.025,0.975]).tolist() if len(null) else None,
               "elapsed_seconds":time.monotonic() - start}
    (out / "summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SUMMARY " + json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
