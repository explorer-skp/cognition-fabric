"""M3 unit tests: Pawl check ordering and reasons, sortition determinism + author exclusion,
the single solve path's reuse budget, shadow thresholds, and the lifecycle transition guard."""

from __future__ import annotations

import hashlib

import pytest

from agents.strategist import HeuristicStrategist
from fabric.capsule import LifecycleState
from fabric.config import DEFAULT_ACTION, JURY_K, MAX_ATTEMPTS, REUSE_REFINE_MAX, SHADOW_N
from fabric.jury import sample_episode, select_jury
from fabric.lifecycle import ShadowTracker, check_transition, shadow_verdict
from fabric.pawl import PawlContext, pawl_check
from tests.test_dilemma_a import AGENT_IDS, make_capsule

HONEST = dict(
    incident_class="ddos_syn_flood",
    dims={"traffic_gbps": [6.0, 10.0], "site_class": ["branch", "campus", "dc"]},
    rule={"rate_limit_pps": 8000, "inspection_depth": 3},
    metric="solve_cost",
    seeds=list(range(1000, 1006)),
    delta_pct=-50.0,
)


def capsule_with(**overrides):
    return make_capsule(**{**HONEST, **overrides})


# --- Pawl: ordered checks, one reason each ------------------------------------------

def test_pawl_passes_honest_capsule():
    result = pawl_check(capsule_with())
    assert result.ok and result.reason == "ok"


def test_pawl_check_order_first_failure_wins():
    """A capsule failing several checks is reported against the earliest — schema (check 1)
    outranks the unknown-dimension ratchet block (check 2), which outranks the rest."""
    capsule = capsule_with(
        rule={"allowlist_subnet": "10.0.0.0/8"},  # would fail check 2
        dims={},  # would fail check 3
        delta_pct=-50.0,
    )
    capsule.sig = "0" * 64  # tampered — must be caught by check 1 before anything else
    result = pawl_check(capsule)
    assert not result.ok and result.check == "schema"

    untampered = capsule_with(rule={"allowlist_subnet": "10.0.0.0/8"}, dims={})
    result = pawl_check(untampered)
    assert result.check == "ratchet monotonicity"  # check 2 fires before bounded context


def test_pawl_ratchet_unknown_dimension_reason():
    result = pawl_check(capsule_with(rule={"allowlist_subnet": "10.0.0.0/8"}))
    assert not result.ok
    assert result.reason == (
        "ratchet monotonicity: unknown action dimension 'allowlist_subnet' "
        "— control-plane vocabulary is registry-only"
    )


def test_pawl_ratchet_loosening_reason_is_distinct_and_compliance_scoped():
    """Loosening a COMPLIANCE floor blocks with the monotonicity reason (distinct from the
    unknown-dimension reason); the same rule in a non-compliance context is not a ratchet matter."""
    loosening = capsule_with(
        rule={"rate_limit_pps": 8000, "inspection_depth": 1},
        dims={"traffic_gbps": [6.0, 10.0], "site_class": ["dc"]},
    )
    result = pawl_check(loosening)
    assert not result.ok
    assert result.reason == (
        "ratchet monotonicity: capsule loosens COMPLIANCE bound inspection_depth 2→1"
    )

    branch_only = capsule_with(
        rule={"rate_limit_pps": 8000, "inspection_depth": 1},
        dims={"traffic_gbps": [6.0, 10.0], "site_class": ["branch"]},
    )
    assert pawl_check(branch_only).check != "ratchet monotonicity"


def test_pawl_omitted_site_class_is_compliance_scoped():
    """A context that omits site_class applies everywhere, dc included — omission never widens
    what a capsule may loosen (fail-secure)."""
    capsule = capsule_with(
        rule={"rate_limit_pps": 8000, "inspection_depth": 1},
        dims={"traffic_gbps": [6.0, 10.0]},
    )
    result = pawl_check(capsule)
    assert result.check == "ratchet monotonicity" and "loosens COMPLIANCE bound" in result.reason


def test_pawl_bounded_context_blocks_wildcards_and_wide_intervals():
    assert pawl_check(capsule_with(dims={})).check == "bounded context"
    wide = capsule_with(dims={"traffic_gbps": [1.0, 12.0]})  # full class space = wildcard-wide
    result = pawl_check(wide)
    assert result.check == "bounded context" and "exceeds cap" in result.reason


def test_pawl_falsifiable_claim_checks():
    assert pawl_check(capsule_with(delta_pct=5.0)).check == "falsifiable claim"
    too_few = capsule_with(seeds=[1, 2, 3], delta_pct=-50.0)
    result = pawl_check(too_few)
    assert result.check == "falsifiable claim" and "below minimum" in result.reason


def test_pawl_rate_and_reputation():
    capsule = capsule_with()
    isolated = pawl_check(capsule, PawlContext(reputation=0.2))
    assert isolated.check == "rate/reputation" and "isolation floor" in isolated.reason
    throttled = pawl_check(capsule, PawlContext(reputation=1.0, submissions_in_window=3))
    assert throttled.check == "rate/reputation" and "allowance" in throttled.reason
    assert pawl_check(capsule, PawlContext(reputation=1.0, submissions_in_window=2)).ok


# --- Sortition: deterministic, verifiable, author excluded ---------------------------

def test_sortition_is_deterministic_and_verifiable():
    capsule = capsule_with()
    jury = select_jury(AGENT_IDS, capsule.capsule_id, epoch=41, author="agent:site-a")
    assert jury == select_jury(AGENT_IDS, capsule.capsule_id, epoch=41, author="agent:site-a")
    assert len(jury) == JURY_K

    # Anyone can recompute the committee: k lowest sha256(agent_id ‖ capsule_id ‖ epoch).
    def draw(agent_id: str) -> str:
        return hashlib.sha256(f"{agent_id}:{capsule.capsule_id}:41".encode()).hexdigest()

    expected = sorted((a for a in AGENT_IDS if a != "agent:site-a"), key=draw)[:JURY_K]
    assert jury == expected


def test_sortition_always_excludes_author():
    for author in AGENT_IDS:
        for salt in range(10):
            fake_id = hashlib.sha256(f"capsule-{salt}".encode()).hexdigest()
            jury = select_jury(AGENT_IDS, fake_id, epoch=salt, author=author)
            assert author not in jury and len(jury) == JURY_K


def test_sortition_reseeds_with_capsule_and_epoch():
    """The draw depends on the capsule's own hash and the epoch — an author cannot precompute a
    friendly committee before the capsule (and hence its id) exists."""
    ids = [hashlib.sha256(f"c{i}".encode()).hexdigest() for i in range(8)]
    juries = {tuple(select_jury(AGENT_IDS, cid, epoch=1, author="agent:site-a")) for cid in ids}
    epoch_juries = {
        tuple(select_jury(AGENT_IDS, ids[0], epoch=e, author="agent:site-a")) for e in range(8)
    }
    assert len(juries) > 1 and len(epoch_juries) > 1


# --- The single solve path: reuse budget (binding decision M3.1) ---------------------

def test_solve_with_prior_uses_reuse_budget():
    strategist = HeuristicStrategist()
    task = sample_episode("ddos_syn_flood", {"traffic_gbps": [6.0, 10.0]}, seed=1234)
    cold = strategist.solve(task, prior=None)
    warm = strategist.solve(task, prior={"rate_limit_pps": 8000, "inspection_depth": 3})
    assert warm.attempts <= 1 + REUSE_REFINE_MAX
    assert cold.attempts > 1 + REUSE_REFINE_MAX  # discovery costs; reuse doesn't
    assert cold.attempts <= MAX_ATTEMPTS


def test_solve_merges_partial_prior_over_default_action():
    strategist = HeuristicStrategist()
    task = sample_episode("ddos_syn_flood", {"traffic_gbps": [6.0, 10.0]}, seed=1234)
    result = strategist.solve(task, prior={"rate_limit_pps": 8000})
    assert set(result.action) == set(DEFAULT_ACTION)  # partial rule completed from the default


# --- Shadow staging thresholds (decision M3.5) ---------------------------------------

def test_shadow_verdict_thresholds():
    promote, confidence, reason = shadow_verdict(ShadowTracker(steps=SHADOW_N, wins=7))
    assert promote and confidence == 0.7 and "won 7/10" in reason

    promote, _confidence, reason = shadow_verdict(ShadowTracker(steps=SHADOW_N, wins=6))
    assert not promote and "below promotion threshold" in reason

    promote, _confidence, reason = shadow_verdict(
        ShadowTracker(steps=SHADOW_N, wins=10, invariant_hits=1)
    )
    assert not promote and "invariant hit" in reason  # zero tolerance beats a perfect record

    with pytest.raises(ValueError):
        shadow_verdict(ShadowTracker(steps=SHADOW_N - 1, wins=7))


# --- Lifecycle transition guard (§4) --------------------------------------------------

def test_lifecycle_transition_guard():
    check_transition(LifecycleState.DRAFT, LifecycleState.SUBMITTED)
    check_transition(LifecycleState.JURY, LifecycleState.CANDIDATE)
    check_transition(LifecycleState.CANDIDATE, LifecycleState.ACTIVE)
    for illegal in (
        (LifecycleState.DRAFT, LifecycleState.ACTIVE),
        (LifecycleState.SUBMITTED, LifecycleState.CANDIDATE),
        (LifecycleState.REJECTED, LifecycleState.ACTIVE),
        (LifecycleState.ACTIVE, LifecycleState.CANDIDATE),
    ):
        with pytest.raises(ValueError):
            check_transition(*illegal)
