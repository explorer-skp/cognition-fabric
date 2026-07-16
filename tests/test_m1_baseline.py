"""M1 acceptance (BLUEPRINT §10): five agents process a storm; per-class solve costs are high and
roughly flat over time (there is no memory yet, so nothing ratchets down).
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

import pytest

from agents.agent import run_baseline_storm
from agents.strategist import HeuristicStrategist, LLMStrategist
from fabric.config import AGENTS, STORM_SIZE
from world.taskgen import generate

STORM_SEED = 424242

# A "high" cost is one well above the reuse band (BLUEPRINT §11: reuse ≈ 4–8 units). The memoryless
# baseline must sit clearly above it for every class.
HIGH_COST_FLOOR = 12.0


def _by_class(events) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for record in events.of_type("SOLVE"):
        grouped[record["incident_class"]].append(record["solve_cost"])
    return grouped


def test_all_five_agents_process_the_storm():
    events = run_baseline_storm(STORM_SEED, n=STORM_SIZE)
    solves = events.of_type("SOLVE")
    assert len(solves) == STORM_SIZE
    agents_seen = {r["agent"] for r in solves}
    assert agents_seen == {aid for aid, _ in AGENTS}


def test_per_class_costs_are_high():
    events = run_baseline_storm(STORM_SEED, n=STORM_SIZE)
    grouped = _by_class(events)
    # Every implemented incident class shows up in the storm.
    assert len(grouped) == 3
    for cls, costs in grouped.items():
        assert median(costs) > HIGH_COST_FLOOR, f"{cls} median {median(costs)} not high"


def test_per_class_costs_are_roughly_flat_over_time():
    events = run_baseline_storm(STORM_SEED, n=STORM_SIZE)
    for cls, costs in _by_class(events).items():
        half = len(costs) // 2
        first, second = median(costs[:half]), median(costs[half:])
        ratio = second / first
        # No memory ⇒ no downward ratchet: the two halves stay within a generous band of each other.
        assert 0.6 <= ratio <= 1.6, f"{cls} not flat: first={first}, second={second}, ratio={ratio}"


def test_baseline_run_is_deterministic():
    a = run_baseline_storm(STORM_SEED, n=STORM_SIZE)
    b = run_baseline_storm(STORM_SEED, n=STORM_SIZE)
    assert a.records() == b.records()


def test_baseline_run_hits_no_invariants():
    events = run_baseline_storm(STORM_SEED, n=STORM_SIZE)
    assert sum(r["invariant_hits"] for r in events.of_type("SOLVE")) == 0


def test_strategist_does_real_search():
    # Cold discovery must cost more than a single attempt (that gap is what the ratchet removes).
    strat = HeuristicStrategist()
    tasks = generate(STORM_SEED, 20)
    attempts = [strat.solve(t).attempts for t in tasks]
    assert min(attempts) >= 1
    assert median(attempts) > 1


def test_llm_strategist_is_a_stub():
    task = generate(STORM_SEED, 1)[0]
    with pytest.raises(NotImplementedError):
        LLMStrategist().solve(task)
