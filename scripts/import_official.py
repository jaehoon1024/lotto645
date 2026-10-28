"""실행: python -m scripts.import_official --start 1148 --end 1247"""
import argparse
from pathlib import Path

from lotto.collector import fetch_range
from lotto.storage import connect, export_draws, save_draws


def main():
    parser = argparse.ArgumentParser(description="공식 회차 결과 수집 및 로컬 저장")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--db", default="data/lotto.sqlite3")
    parser.add_argument("--csv", default="data/official_history.csv")
    args = parser.parse_args()
    draws = fetch_range(args.start, args.end, lambda done, total: print(f"Verified {done}/{total}", flush=True))
    with connect(args.db) as db:
        count = save_draws(db, draws)
    Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.csv).write_bytes(export_draws(draws))
    print(f"Saved {count} new draws; source: https://www.dhlottery.co.kr/lt645/result")


if __name__ == "__main__":
    main()
