from dataclasses import replace

import numpy as np

from lotto import research
from lotto.research import ResearchConfig, advance_counts, candidate_pools, evaluate, fair_history, initialize_counts, relation_features, select_indices


def test_rolling_counts_equal_full_recomputation():
    numbers = fair_history(220, 52)
    counts = initialize_counts(numbers,100)
    for target_index in range(200,220):
        fresh = initialize_counts(numbers[target_index - 200:target_index],100)
        for incremental, direct in zip(counts,fresh):
            np.testing.assert_array_equal(incremental,direct)
        advance_counts(counts,numbers[target_index - 200],numbers[target_index - 100],numbers[target_index])


def test_frequency_only_equivalence_when_relation_weight_zero():
    config = replace(ResearchConfig(),candidates=64,relation_weight=0)
    numbers = fair_history(210,66)
    result = evaluate(numbers,candidate_pools(len(numbers),config),config)
    assert result["primary_delta"] == 0
    for target in range(201,211):
        rows = [r for r in result["rows"] if r["회차"] == target]
        assert rows[1]["평균 일치"] == rows[2]["평균 일치"]


def test_each_prediction_uses_only_prior_200_rounds(monkeypatch):
    numbers = fair_history(212,3)
    config = replace(ResearchConfig(),candidates=64)
    observed = []
    original = research.relation_features

    def spy(*args):
        observed.append([v.copy() for v in args[:4]])
        return original(*args)

    monkeypatch.setattr(research,"relation_features",spy)
    result = evaluate(numbers,candidate_pools(len(numbers),config),config)
    for offset, counts in enumerate(observed):
        direct = initialize_counts(numbers[offset:offset + 200],100)
        for actual, expected in zip(counts,direct):
            np.testing.assert_array_equal(actual,expected)
    assert all(r["학습 끝"] == r["회차"] - 1 for r in result["rows"])


def test_same_relation_windows_have_zero_trend():
    history = fair_history(100,77)
    counts = initialize_counts(np.concatenate([history,history]),100)
    p, trend = relation_features(*counts)
    assert np.all(p>0)
    np.testing.assert_allclose(trend,0)


def test_candidates_and_portfolios_are_reproducible_and_valid():
    config = ResearchConfig()
    first = candidate_pools(201,config)[0]
    second = candidate_pools(201,config)[0]
    np.testing.assert_array_equal(first[0],second[0])
    pool,masks,selection = first
    assert len(pool) == len(set(map(tuple,pool)))
    assert all(len(set(t)) == 6 and all(0<=n<45 for n in t) for t in pool)
    for order in (range(len(pool)),range(len(pool)-1,-1,-1)):
        ids = select_indices(masks,order)
        assert len(ids)==10 and len(set(ids))==10
        assert all((masks[int(a)]&masks[int(b)]).bit_count()<=3 for i,a in enumerate(ids) for b in ids[i+1:])
