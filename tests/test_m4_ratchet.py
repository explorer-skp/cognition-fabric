"""M4 acceptance (BLUEPRINT §10): the ratchet is measured, not asserted.

Over a shaped repeat-incident storm (the mix is shaped to guarantee applicable-task supply — the
*mechanism* is under test; absolute economics are deferred to M7): repeat incidents at ≥ 3
non-author sites solve at reuse cost ≤ 0.5 × discovery; the per-class staircase steps down and never
rises; Lane A cumulative cost lands below Lane B on the identical stream; and — the controlled
experiment's control — Lane B is byte-identical to a standalone fabric-off baseline run.
"""

from __future__ import annotations

from agents.agent import run_baseline_storm, run_twin_lane
from demo.demo_smoke import repeat_incident_storm
from fabric.config import STORM_SIZE
from ui.metrics import (
    cumulative_cost,
    insight_lead_times,
    non_author_reuse_sites,
    ratchet_staircase,
    reuse_vs_discovery,
)

SEED = 424242


def _shaped_lanes():
    tasks = repeat_incident_storm(STORM_SIZE)
    return run_twin_lane(SEED, len(tasks), tasks=tasks)


# --- reuse at other sites, at half the discovery cost ---------------------------

def test_repeat_incidents_reuse_at_three_plus_non_author_sites_at_half_cost():
    lane_a, _lane_b = _shaped_lanes()
    records = lane_a.records()
    sites = non_author_reuse_sites(records)
    assert len(sites) >= 3, f"only {sorted(sites)} reused a capsule they did not author"
    ddos = reuse_vs_discovery(records)["ddos_syn_flood"]
    assert ddos["reuse_median"] <= 0.5 * ddos["discovery_median"], ddos


# --- the ratchet staircase steps down and never rises ---------------------------

def test_staircase_is_monotone_non_increasing_and_steps_down():
    lane_a, _ = _shaped_lanes()
    stairs = ratchet_staircase(lane_a.records())["ddos_syn_flood"]
    assert all(stairs[i] >= stairs[i + 1] for i in range(len(stairs) - 1)), stairs
    assert stairs[-1] < stairs[0], "staircase never stepped down"


# --- the controlled experiment: Lane A below Lane B -----------------------------

def test_lane_a_cumulative_below_lane_b_on_shaped_storm():
    lane_a, lane_b = _shaped_lanes()
    assert cumulative_cost(lane_a.records()) < cumulative_cost(lane_b.records())


def test_lane_a_cumulative_below_lane_b_on_natural_stream():
    lane_a, lane_b = run_twin_lane(SEED, STORM_SIZE)  # natural TaskGen stream, both lanes
    assert cumulative_cost(lane_a.records()) < cumulative_cost(lane_b.records())


# --- Lane B ≡ the M1 baseline (the control is the baseline) ---------------------

def test_lane_b_is_byte_identical_to_the_fabric_off_baseline():
    _lane_a, lane_b = run_twin_lane(SEED, STORM_SIZE)  # natural stream
    baseline = run_baseline_storm(SEED, STORM_SIZE)
    assert lane_b.records() == baseline.records()


# --- determinism + insight lead time --------------------------------------------

def test_twin_lane_is_deterministic():
    a1, b1 = _shaped_lanes()
    a2, b2 = _shaped_lanes()
    assert a1.records() == a2.records()
    assert b1.records() == b2.records()


def test_insight_lead_times_are_present_and_non_negative():
    lane_a, _ = _shaped_lanes()
    leads = insight_lead_times(lane_a.records())
    assert leads, "no capsule reached ACTIVE mesh-wide"
    assert all(v >= 0 for v in leads.values())
