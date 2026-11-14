"""Reproduce the retrospective comparison described in FIVE_GAME_PROTOCOL.md."""
import hashlib
import json
from math import comb
from pathlib import Path

import numpy as np

from lotto.research import (
    PAIR_I, PAIR_J, ResearchConfig, candidate_pools, initialize_counts,
    relation_features, select_indices, validate_archive,
)
from lotto.storage import export_draws, read_csv


def evaluate(draws):
    validate_archive(draws)
    config = ResearchConfig()
    warmup = config.window * 2
    numbers = np.asarray([draw.numbers for draw in draws]) - 1
    pools = candidate_pools(len(draws), config)
    results = []
    for index, ((pool, masks, _), draw) in enumerate(zip(pools, draws[warmup:]), warmup):
        counts = initialize_counts(numbers[index - warmup:index], config.window)
        frequency, trend = relation_features(*counts, config)
        scores = np.log(frequency)[pool].mean(axis=1)
        scores += config.relation_weight * trend[pool[:, PAIR_I], pool[:, PAIR_J]].mean(axis=1)
        ranked = np.argsort(-scores, kind="stable")
        aj_r1 = pool[select_indices(masks, ranked, config.games, config.max_overlap)[:5]]
        date_seed = int(draw.date.replace("-", ""))
        aj_d1 = np.random.default_rng(date_seed).permutation(45)[:30].reshape(5, 6)
        portfolios = {"무작위": pool[:5], "AJ-R1": aj_r1, "AJ-D1": aj_d1}
        results.append({
            name: np.isin(tickets, numbers[index]).sum(axis=1).tolist()
            for name, tickets in portfolios.items()
        })
    return results


def summarize(results):
    return {
        name: {
            "winning_rounds": sum(max(row[name]) >= 3 for row in results),
            "winning_rate": sum(max(row[name]) >= 3 for row in results) / len(results),
            "mean_hits": sum(sum(row[name]) for row in results) / (5 * len(results)),
        }
        for name in results[0]
    }


def main():
    archive = read_csv(Path("research/official_1_1248.csv").read_bytes())
    history = read_csv(Path("data/official_history.csv").read_bytes())
    draws = archive + [draw for draw in history if 1248 < draw.round <= 1250]
    if draws[-1].round != 1250:
        raise ValueError("The fixed evaluation requires official draws through round 1250.")
    results = evaluate(draws)
    first_round = 201
    total = comb(45, 6)
    winning = sum(comb(6, k) * comb(39, 6 - k) for k in range(3, 7))
    payload = {
        "first_round": first_round,
        "last_round": draws[-1].round,
        "round_count": len(results),
        "data_sha256": hashlib.sha256(export_draws(draws)).hexdigest(),
        "overall": summarize(results),
        "fair_draw_reference": {
            "무작위": 1 - comb(total - winning, 5) / comb(total, 5),
            "AJ-D1": (5 * winning - comb(5, 2) * comb(6, 3) ** 2) / total,
        },
        "blocks": [
            {"first": first_round + i, "last": first_round + i + len(block) - 1,
             "count": len(block), "methods": summarize(block)}
            for i in range(0, len(results), 100)
            for block in [results[i:i + 100]]
        ],
    }
    output = Path("research/results/five_game_comparison.json")
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["overall"], ensure_ascii=False, indent=2))
    print(payload["fair_draw_reference"])


if __name__ == "__main__":
    main()
