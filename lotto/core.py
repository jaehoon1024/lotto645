from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from math import comb
import random


@dataclass(frozen=True)
class Draw:
    round: int
    date: str
    numbers: tuple[int, ...]
    bonus: int
    source: str = "CSV"

    def __post_init__(self):
        if type(self.round) is not int or self.round < 1:
            raise ValueError("회차는 1 이상의 정수여야 합니다.")
        date.fromisoformat(self.date)
        if len(self.numbers) != 6 or len(set(self.numbers)) != 6:
            raise ValueError("본번호는 중복 없는 6개여야 합니다.")
        if any(type(n) is not int or not 1 <= n <= 45 for n in (*self.numbers, self.bonus)):
            raise ValueError("번호는 1~45의 정수여야 합니다.")
        if self.bonus in self.numbers:
            raise ValueError("보너스번호는 본번호와 달라야 합니다.")
        object.__setattr__(self, "numbers", tuple(sorted(self.numbers)))


def parse_numbers(value: str) -> tuple[int, ...]:
    try:
        values = tuple(int(x) for x in value.replace(",", " ").split())
    except ValueError as exc:
        raise ValueError("번호는 쉼표 또는 공백으로 구분한 정수로 입력하세요.") from exc
    if len(set(values)) != len(values) or any(not 1 <= x <= 45 for x in values):
        raise ValueError("중복 없이 1~45 번호를 입력하세요.")
    return tuple(sorted(values))


def stats(draws: list[Draw]) -> dict:
    draws = sorted(draws, key=lambda d: d.round)
    frequency = Counter(n for d in draws for n in d.numbers)
    last = {n: max((d.round for d in draws if n in d.numbers), default=None) for n in range(1, 46)}
    latest = draws[-1].round if draws else None
    return {
        "frequency": {n: frequency[n] for n in range(1, 46)},
        "gap": {n: latest - last[n] if last[n] is not None else None for n in range(1, 46)},
        "odd": Counter(sum(n % 2 for n in d.numbers) for d in draws),
        "sums": [sum(d.numbers) for d in draws],
        "consecutive": Counter(sum(b == a + 1 for a, b in zip(d.numbers, d.numbers[1:])) for d in draws),
        "pairs": Counter(pair for d in draws for pair in combinations(d.numbers, 2)),
        "zones": Counter((n - 1) // 10 for d in draws for n in d.numbers),
        "repeats": [len(set(a.numbers) & set(b.numbers)) for a, b in zip(draws, draws[1:]) if b.round == a.round + 1],
    }


def generate(count: int = 5, *, mode: str = "random", include=(), exclude=(),
             odd_count: int | None = None, sum_min: int = 21, sum_max: int = 255,
             max_overlap: int = 6, draws: list[Draw] | None = None,
             seed: int | None = None) -> list[tuple[int, ...]]:
    if mode not in {"random", "condition", "weighted"}:
        raise ValueError("지원하지 않는 추천 방식입니다.")
    if type(count) is not int or not 1 <= count <= 100:
        raise ValueError("게임 수는 1~100이어야 합니다.")
    include, exclude = set(include), set(exclude)
    if any(type(n) is not int or not 1 <= n <= 45 for n in include | exclude):
        raise ValueError("번호 범위는 1~45입니다.")
    if include & exclude or len(include) > 6 or 45 - len(exclude) < 6:
        raise ValueError("포함·제외 번호가 충돌하거나 선택 가능한 번호가 부족합니다.")
    if odd_count is not None and odd_count not in range(7):
        raise ValueError("홀수 개수는 0~6이어야 합니다.")
    if not 0 <= max_overlap <= 6 or sum_min > sum_max:
        raise ValueError("합계 범위 또는 게임 간 중복 상한을 확인하세요.")
    if count > 1 and len(include) > max_overlap:
        raise ValueError("포함 번호 개수가 게임 간 중복 상한보다 큽니다.")
    pool = sorted(set(range(1, 46)) - include - exclude)
    needed = 6 - len(include)
    if comb(len(pool), needed) < count:
        raise ValueError("가능한 서로 다른 조합보다 게임 수가 많습니다.")
    if odd_count is not None:
        remaining_odds = odd_count - sum(n % 2 for n in include)
        if remaining_odds < 0 or remaining_odds > needed or remaining_odds > sum(n % 2 for n in pool) or needed - remaining_odds > sum(n % 2 == 0 for n in pool):
            raise ValueError("포함·제외 번호로는 지정한 홀짝 구성을 만들 수 없습니다.")
    if sum(include) + sum(pool[:needed]) > sum_max or sum(include) + sum(pool[-needed:] if needed else []) < sum_min:
        raise ValueError("포함·제외 번호로는 지정한 합계를 만들 수 없습니다.")
    if mode == "weighted" and not draws:
        raise ValueError("통계 가중 추천은 당첨 이력을 먼저 가져와야 합니다.")
    rng = random.Random(seed)
    frequency = Counter(n for d in (draws or []) for n in d.numbers)

    def accept(candidate):
        return (sum_min <= sum(candidate) <= sum_max
                and (odd_count is None or sum(n % 2 for n in candidate) == odd_count))

    # 작은 후보 공간은 전수 확인하여 좁은 조건에서도 불필요한 재시도를 피한다.
    candidates = None
    if comb(len(pool), needed) <= 100_000:
        candidates = [tuple(sorted(include | set(c))) for c in combinations(pool, needed)]
        candidates = [c for c in candidates if accept(c)]
        if len(candidates) < count:
            raise ValueError("조건을 만족하는 서로 다른 조합이 부족합니다.")
    result = []
    seen = set()
    for _ in range(100_000):
        if candidates is not None:
            if not candidates:
                break
            if mode == "weighted":
                weights = [sum(frequency[n] + 1 for n in c) for c in candidates]
                idx = rng.choices(range(len(candidates)), weights=weights)[0]
            else:
                idx = rng.randrange(len(candidates))
            candidate = candidates.pop(idx)
        elif mode == "weighted":
            available = pool.copy()
            selected = set(include)
            for _ in range(needed):
                n = rng.choices(available, weights=[frequency[x] + 1 for x in available])[0]
                available.remove(n)
                selected.add(n)
            candidate = tuple(sorted(selected))
        else:
            candidate = tuple(sorted(include | set(rng.sample(pool, needed))))
        if candidate in seen or not accept(candidate):
            continue
        if any(len(set(candidate) & set(old)) > max_overlap for old in result):
            continue
        result.append(candidate)
        seen.add(candidate)
        if len(result) == count:
            return result
    raise ValueError("현재 조건으로 요청한 게임 수를 생성하지 못했습니다. 조건을 완화하거나 게임 수를 줄여 주세요.")


def match(numbers, draw: Draw) -> tuple[int, int | None]:
    values = tuple(numbers)
    if len(values) != 6 or len(set(values)) != 6 or any(type(n) is not int or not 1 <= n <= 45 for n in values):
        raise ValueError("확인할 번호는 1~45의 중복 없는 정수 6개여야 합니다.")
    hits = len(set(values) & set(draw.numbers))
    rank = 1 if hits == 6 else (2 if draw.bonus in values else 3) if hits == 5 else 4 if hits == 4 else 5 if hits == 3 else None
    return hits, rank


def backtest(draws: list[Draw], *, warmup=30, games=5, window=100, seed=42) -> list[dict]:
    ordered = sorted(draws, key=lambda d: d.round)
    if len({d.round for d in ordered}) != len(ordered):
        raise ValueError("검증 데이터에 중복 회차가 있습니다.")
    if warmup < 1 or window < 1 or len(ordered) <= warmup:
        raise ValueError("학습 구간보다 많은 당첨 이력이 필요합니다.")
    if any(b.round != a.round + 1 for a, b in zip(ordered, ordered[1:])):
        raise ValueError("과거 검증에는 누락 없는 연속 회차가 필요합니다.")
    rows = []
    for i in range(warmup, len(ordered)):
        history = ordered[max(0, i - window):i]
        for mode in ("random", "weighted"):
            tickets = generate(games, mode=mode, draws=history, seed=seed + ordered[i].round * 2 + (mode == "weighted"))
            for ticket in tickets:
                hits, rank = match(ticket, ordered[i])
                rows.append({"회차": ordered[i].round, "방식": mode, "일치": hits, "등수": rank or 0})
    return rows
