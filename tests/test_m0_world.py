"""M0 acceptance (BLUEPRINT §10): a seeded run of 20 tasks prints identical episode metrics across
two runs; plus sanity on the scenario shape, the clock, the bus, and the registry.
"""

from __future__ import annotations

import asyncio

import pytest

from fabric.config import DEFAULT_ACTION, INCIDENT_CLASSES
from fabric.registry import DIMENSIONS, INVARIANTS, conforms
from world.bus import Bus, Message
from world.cost import solve_cost
from world.scenarios import simulate
from world.simclock import SimClock
from world.taskgen import generate


def _action(**overrides) -> dict:
    action = dict(DEFAULT_ACTION)
    action.update(overrides)
    return action


# --- M0 acceptance criterion --------------------------------------------------
def test_twenty_task_run_identical_metrics_across_two_runs():
    tasks = generate(seed=424242, n=20)
    assert len(tasks) == 20

    def metrics_of(stream):
        return [simulate(t.params, DEFAULT_ACTION, t.seed).as_dict() for t in stream]

    run_a = metrics_of(tasks)
    run_b = metrics_of(generate(seed=424242, n=20))
    assert run_a == run_b


# --- scenario shape: right action region ⇒ lower cost -------------------------
def test_ddos_good_action_beats_bad_action():
    params = {"incident_class": "ddos_syn_flood", "site_class": "campus",
              "traffic_gbps": 8.0, "device_count": 200}
    good = _action(rate_limit_pps=8000, inspection_depth=3)   # threshold ~ 1000*traffic
    bad = _action(rate_limit_pps=2000, inspection_depth=7)    # far under-provisioned
    cost_good = solve_cost(1, simulate(params, good, seed=7))
    cost_bad = solve_cost(1, simulate(params, bad, seed=7))
    assert cost_good < cost_bad


def test_iot_good_action_beats_bad_action():
    params = {"incident_class": "iot_anomaly_burst", "site_class": "branch",
              "traffic_gbps": 3.0, "device_count": 250}
    good = _action(sampled_fraction=0.5, quarantine_scope="flagged_only")
    bad = _action(sampled_fraction=0.1, quarantine_scope="none")
    assert solve_cost(1, simulate(params, good, 7)) < solve_cost(1, simulate(params, bad, 7))


def test_cert_good_action_beats_bad_action():
    params = {"incident_class": "cert_expiry_storm", "site_class": "dc",
              "traffic_gbps": 2.0, "device_count": 300}
    good = _action(retry_backoff_ms=200, block_ttl_s=120)
    bad = _action(retry_backoff_ms=800, block_ttl_s=300)
    assert solve_cost(1, simulate(params, good, 7)) < solve_cost(1, simulate(params, bad, 7))


def test_unsafe_action_registers_invariant_hit():
    # Inspection off during a flagged-flow incident bypasses inspection → invariant hit → punished.
    params = {"incident_class": "ddos_syn_flood", "site_class": "branch",
              "traffic_gbps": 5.0, "device_count": 100}
    unsafe = _action(inspection_depth=0)
    m = simulate(params, unsafe, seed=1)
    assert m.invariant_hits >= 1
    # Blanket subnet block off a compliance-classed site trips its own invariant.
    subnet_unsafe = _action(quarantine_scope="subnet")
    assert simulate({**params, "incident_class": "iot_anomaly_burst"}, subnet_unsafe, 1).invariant_hits >= 1


def test_unknown_incident_class_fails_secure():
    params = {"incident_class": "does_not_exist", "site_class": "dc",
              "traffic_gbps": 1.0, "device_count": 10}
    with pytest.raises(ValueError):
        simulate(params, DEFAULT_ACTION, seed=1)


# --- clock --------------------------------------------------------------------
def test_simclock_is_monotone():
    clock = SimClock()
    assert clock.now == 0.0
    clock.advance(2.5)
    assert clock.now == 2.5
    clock.set(5.0)
    assert clock.now == 5.0
    with pytest.raises(ValueError):
        clock.set(1.0)
    with pytest.raises(ValueError):
        clock.advance(-1.0)


# --- bus: deterministic (sim_time, seq) ordering ------------------------------
def test_bus_delivers_in_time_then_sequence_order():
    clock = SimClock()
    bus = Bus(clock)
    seen: list[float] = []
    bus.subscribe("TASK", lambda m: seen.append(m.sim_time))
    bus.publish("TASK", Message("TASK", "world", 2.0), at=2.0)
    bus.publish("TASK", Message("TASK", "world", 1.0), at=1.0)
    bus.publish("TASK", Message("TASK", "world", 3.0), at=3.0)
    delivered = asyncio.run(bus.run_until_empty())
    assert delivered == 3
    assert seen == [1.0, 2.0, 3.0]
    assert clock.now == 3.0


def test_bus_rejects_unknown_topic_and_past_publish():
    clock = SimClock(10.0)
    bus = Bus(clock)
    with pytest.raises(ValueError):
        bus.subscribe("NOPE", lambda m: None)
    with pytest.raises(ValueError):
        bus.publish("TASK", Message("TASK", "world", 1.0), at=1.0)  # into the past


# --- registry -----------------------------------------------------------------
def test_registry_dimensions_and_invariants_present():
    for name in ("rate_limit_pps", "inspection_depth", "quarantine_scope",
                 "retry_backoff_ms", "sampled_fraction", "block_ttl_s",
                 "traffic_gbps", "device_count", "site_class"):
        assert name in DIMENSIONS
    assert conforms("inspection_depth", 3)
    assert not conforms("inspection_depth", 8)
    assert conforms("quarantine_scope", "flagged_only")
    assert not conforms("quarantine_scope", "everything")
    assert len(INVARIANTS) == 4
    assert len(INCIDENT_CLASSES) == 3
