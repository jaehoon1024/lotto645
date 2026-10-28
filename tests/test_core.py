from datetime import date, timedelta
from itertools import combinations

import pytest

from lotto import core
from lotto.core import Draw, generate, match, parse_numbers, stats


def history(count=45):
    return [Draw(i + 1, (date(2020, 1, 4) + timedelta(weeks=i)).isoformat(), tuple(sorted({(i + k) % 45 + 1 for k in range(6)})), (i + 7) % 45 + 1, "TEST") for i in range(count)]


@pytest.mark.parametrize("ticket,rank,hits", [
    ((1, 2, 3, 4, 5, 6), 1, 6), ((1, 2, 3, 4, 5, 7), 2, 5),
    ((1, 2, 3, 4, 5, 8), 3, 5), ((1, 2, 3, 4, 8, 9), 4, 4),
    ((1, 2, 3, 8, 9, 10), 5, 3), ((1, 2, 8, 9, 10, 11), None, 2),
])
def test_prize_rules(ticket, rank, hits):
    assert match(ticket, Draw(1, "2002-12-07", (1, 2, 3, 4, 5, 6), 7)) == (hits, rank)


@pytest.mark.parametrize("seed", range(10))
def test_constraints_across_many_seeds(seed):
    tickets = generate(8, include=[3], exclude=[8, 45], odd_count=3, sum_min=90, sum_max=180, max_overlap=3, seed=seed)
    assert len(set(tickets)) == 8
    for ticket in tickets:
        assert len(set(ticket)) == 6
        assert 3 in ticket and 8 not in ticket and 45 not in ticket
        assert sum(n % 2 for n in ticket) == 3
        assert 90 <= sum(ticket) <= 180
    assert all(len(set(a) & set(b)) <= 3 for a, b in combinations(tickets, 2))


def test_impossible_constraints():
    for kwargs in [{"include": [1], "exclude": [1]}, {"include": [1, 3, 5], "odd_count": 1}, {"include": [40, 41, 42], "sum_max": 50}, {"include": [1, 2, 3, 4, 5, 6]}, {"exclude": list(range(1, 41))}]:
        with pytest.raises(ValueError):
            generate(5, **kwargs)


def test_full_fixed_ticket_and_single_remaining_slot():
    assert generate(1, include=[1, 2, 3, 4, 5, 6]) == [(1, 2, 3, 4, 5, 6)]
    tickets = generate(3, include=[1, 2, 3, 4, 5], exclude=list(range(9, 46)), seed=1)
    assert set(tickets) == {(1, 2, 3, 4, 5, n) for n in [6, 7, 8]}


def test_weighted_requires_history():
    with pytest.raises(ValueError):
        generate(mode="weighted")
    assert len(generate(mode="weighted", draws=history(), seed=1)) == 5


def test_uniform_random_basic_distribution():
    # 엄밀한 분포 증명이 아니라 번호 고정이나 범위 누락을 탐지한다.
    tickets = generate(100, seed=45)
    counts = {n: sum(n in t for t in tickets) for n in range(1, 46)}
    assert all(2 <= c <= 30 for c in counts.values())


def test_statistics_excludes_bonus_and_uses_round_gap():
    draws = [Draw(1, "2002-12-07", (1, 2, 3, 4, 5, 6), 7), Draw(3, "2002-12-21", (2, 3, 4, 5, 6, 8), 1)]
    result = stats(draws)
    assert sum(result["frequency"].values()) == 12
    assert result["frequency"][7] == 0
    assert result["gap"][1] == 2 and result["gap"][7] is None
    assert result["repeats"] == []
    assert result["pairs"][(2, 3)] == 2


def test_backtest_never_passes_future_draws(monkeypatch):
    records = history(20)
    seen = []
    original = core.generate

    def spy(count, **kwargs):
        seen.append([d.round for d in kwargs["draws"]])
        return original(count, **kwargs)

    monkeypatch.setattr(core, "generate", spy)
    rows = core.backtest(records, warmup=10, games=2, window=5)
    assert len(rows) == 10 * 2 * 2
    for index, rounds in enumerate(seen):
        target_round = 11 + index // 2
        assert max(rounds) == target_round - 1 and len(rounds) == 5
        assert all(r < target_round for r in rounds)


def test_backtest_rejects_missing_rounds():
    records = history(20)
    with pytest.raises(ValueError, match="연속"):
        core.backtest(records[:5] + records[6:], warmup=10)


def test_bad_input_numbers():
    for text in ["1,1,2", "0 1", "46", "a"]:
        with pytest.raises(ValueError):
            parse_numbers(text)
    assert parse_numbers("3, 1 2") == (1, 2, 3)
    with pytest.raises(ValueError):
        match((1, 1, 2, 3, 4, 5), history(1)[0])
