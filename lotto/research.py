"""AJ-R1 first fixed exploratory experiment. No purchase data is used."""
from dataclasses import asdict, dataclass
from datetime import date, timedelta

import numpy as np


@dataclass(frozen=True)
class ResearchConfig:
    window: int = 100
    block: int = 100
    games: int = 10
    candidates: int = 512
    max_overlap: int = 3
    prior: float = 20.0
    relation_weight: float = 0.25
    seed: int = 20261101
    null_repeats: int = 199


METHODS = ("무작위", "빈도 기준", "AJ-R1")
PAIR_I, PAIR_J = np.triu_indices(6, 1)


def validate_archive(draws):
    if len(draws) < 201:
        raise ValueError("At least 201 consecutive rounds are required")
    if [d.round for d in draws] != list(range(1, len(draws) + 1)):
        raise ValueError("Archive must start at round 1 with no gaps or duplicates")
    for d in draws:
        expected = date(2002, 12, 7) + timedelta(weeks=d.round - 1)
        if d.date != expected.isoformat():
            raise ValueError(f"Unexpected date for round {d.round}")


def masks_for(tickets):
    return [sum(1 << int(n) for n in t) for t in tickets]


def select_indices(masks, order, games=10, overlap=3):
    selected, chosen_masks = [], []
    for index in order:
        candidate = masks[int(index)]
        if all((candidate & old).bit_count() <= overlap for old in chosen_masks):
            selected.append(int(index))
            chosen_masks.append(candidate)
            if len(selected) == games:
                return np.asarray(selected)
    raise ValueError("Not enough candidates under fixed portfolio constraints")


def candidate_pools(total_rounds, config=ResearchConfig()):
    pools = []
    for target in range(2 * config.window + 1, total_rounds + 1):
        rng = np.random.default_rng(config.seed + target * 1009)
        raw = np.sort(np.argpartition(rng.random((config.candidates, 45)), 5, axis=1)[:, :6], axis=1)
        _, indices = np.unique(raw, axis=0, return_index=True)
        pool = raw[np.sort(indices)].astype(np.int8)
        masks = masks_for(pool)
        random_selection = select_indices(masks, range(len(pool)), config.games, config.max_overlap)
        pools.append((pool, masks, random_selection))
    return pools


def initialize_counts(numbers, window):
    presence = np.zeros((2 * window, 45), dtype=np.int64)
    presence[np.arange(2 * window)[:, None], numbers[:2 * window]] = 1
    a, b = presence[:window], presence[window:]
    return a.sum(axis=0), b.sum(axis=0), a.T @ a, b.T @ b


def relation_features(freq_a, freq_b, pairs_a, pairs_b, config=ResearchConfig()):
    p_a = (freq_a + config.prior * 6 / 45) / (config.window + config.prior)
    p_b = (freq_b + config.prior * 6 / 45) / (config.window + config.prior)
    correction = (5 / 6) * (45 / 44)
    expected_a = config.window * np.outer(p_a, p_a) * correction
    expected_b = config.window * np.outer(p_b, p_b) * correction
    residual_a = (pairs_a - expected_a) / np.sqrt(expected_a + 1)
    residual_b = (pairs_b - expected_b) / np.sqrt(expected_b + 1)
    return p_b, residual_b - residual_a


def advance_counts(counts, leaving, crossing, entering):
    fa, fb, pa, pb = counts
    fa[leaving] -= 1
    fa[crossing] += 1
    fb[crossing] -= 1
    fb[entering] += 1
    pa[np.ix_(leaving, leaving)] -= 1
    pa[np.ix_(crossing, crossing)] += 1
    pb[np.ix_(crossing, crossing)] -= 1
    pb[np.ix_(entering, entering)] += 1


def evaluate(numbers, pools, config=ResearchConfig(), bonuses=None, keep_rows=True):
    numbers = np.asarray(numbers, dtype=np.int8)
    warmup = config.window * 2
    if len(numbers) <= warmup or len(pools) != len(numbers) - warmup:
        raise ValueError("History and candidate pool lengths do not match")
    counts = initialize_counts(numbers, config.window)
    sums = np.zeros(3)
    rows = []
    for index in range(warmup, len(numbers)):
        p_b, trend = relation_features(*counts, config)
        pool, masks, random_selection = pools[index - warmup]
        frequency = np.log(p_b)[pool].mean(axis=1)
        pair_change = trend[pool[:, PAIR_I], pool[:, PAIR_J]].mean(axis=1)
        selection = [random_selection,
                     select_indices(masks, np.argsort(-frequency, kind="stable"), config.games, config.max_overlap),
                     select_indices(masks, np.argsort(-(frequency + config.relation_weight * pair_change), kind="stable"), config.games, config.max_overlap)]
        target_mask = masks_for([numbers[index]])[0]
        for method_index, chosen in enumerate(selection):
            hits = np.asarray([(masks[int(i)] & target_mask).bit_count() for i in chosen])
            mean_hits = float(hits.mean())
            sums[method_index] += mean_hits
            if keep_rows:
                row = {"회차":index + 1,"방식":METHODS[method_index],"평균 일치":mean_hits,
                       "3개 이상 게임":int((hits >= 3).sum()),"한 게임 이상 당첨":int((hits >= 3).any()),
                       "학습 시작":index - warmup + 1,"학습 끝":index}
                ranks = []
                for ticket_index, hit in zip(chosen, hits):
                    bonus_hit = bonuses is not None and int(bonuses[index]) in pool[int(ticket_index)]
                    rank = 1 if hit == 6 else (2 if bonus_hit else 3) if hit == 5 else 4 if hit == 4 else 5 if hit == 3 else 0
                    ranks.append(rank)
                row.update({f"{r}등 게임":ranks.count(r) for r in range(1,6)})
                rows.append(row)
        # Outcome index is added only after all three predictions have been scored.
        advance_counts(counts, numbers[index - warmup], numbers[index - config.window], numbers[index])
    averages = sums / (len(numbers) - warmup)
    return {"means":dict(zip(METHODS,map(float,averages))),
            "primary_delta":float(averages[2] - averages[1]),
            "random_delta":float(averages[2] - averages[0]), "rows":rows}


def fair_history(total_rounds, seed):
    rng = np.random.default_rng(seed)
    return np.sort(np.argpartition(rng.random((total_rounds,45)),5,axis=1)[:,:6],axis=1).astype(np.int8)


def config_dict(config=ResearchConfig()):
    return asdict(config)
