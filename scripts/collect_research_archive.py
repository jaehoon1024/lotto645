"""공식 결과를 배치별 검증·저장하는 재개 가능한 전체 이력 수집."""
from datetime import date, timedelta
from pathlib import Path
import time

from lotto.collector import fetch_batch
from lotto.storage import export_draws, read_csv


def main():
    path = Path("research/official_1_1248.csv")
    path.parent.mkdir(exist_ok=True)
    known = {d.round:d for d in read_csv(path.read_bytes())} if path.exists() else {}
    seed = Path("data/official_history.csv")
    if seed.exists():
        for d in read_csv(seed.read_bytes()):
            if 1 <= d.round <= 1248:
                known.setdefault(d.round,d)
    while len(known) < 1248:
        missing = next(r for r in range(1,1249) if r not in known)
        target = min(missing + 5,1248)
        for attempt in range(3):
            try:
                batch = fetch_batch(target)
                break
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(2)
        if missing not in {d.round for d in batch}:
            raise ValueError(f"Missing round {missing} not included in batch {target}")
        for d in batch:
            if not 1 <= d.round <= 1248:
                continue
            if d.date != (date(2002,12,7) + timedelta(weeks=d.round-1)).isoformat():
                raise ValueError(f"Unexpected date in round {d.round}")
            old = known.get(d.round)
            if old and (old.date,old.numbers,old.bonus) != (d.date,d.numbers,d.bonus):
                raise ValueError(f"Conflicting round {d.round}")
            known[d.round] = d
        path.write_bytes(export_draws(sorted(known.values(),key=lambda d:d.round)))
        print(f"Verified {len(known)}/1248, covered through {max(r for r in range(1,1249) if all(x in known for x in range(1,r+1)))}",flush=True)
        time.sleep(0.35)
    print("Archive complete: research/official_1_1248.csv",flush=True)


if __name__ == "__main__":
    main()
