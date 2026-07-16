"""Dilemma A — Innovation vs. Hallucination: a capsule's claim is never believed, it is replayed —
fabricated numbers die at counterfactual replay, overfit claims die on author-blind held-out
scenarios, unsafe-but-real gains die at invariant/conformance, and only honestly-better capsules
reach ACTIVE (BLUEPRINT §5, milestone M3 acceptance).

Every capsule here is built the way a real author would build it: the claim is *measured* through
the same `jury.replay` path jurors use (honestly, or by cherry-picking lucky seeds), never invented
by the test — except for the fabricator, whose whole point is a number nobody measured.
"""

from __future__ import annotations

import statistics

from agents.strategist import HeuristicStrategist
from fabric import keyring
from fabric.capsule import (
    Capsule,
    Claim,
    Context,
    Evidence,
    Lifecycle,
    LifecycleState,
    Payload,
    Provenance,
    build_capsule,
)
from fabric.config import AGENTS, QUORUM, REGISTRY_VERSION, SHADOW_N
from fabric.jury import ReplayEpisode, replay, sample_episode, vote_payload
from fabric.lifecycle import run_shadow, submit
from fabric.pawl import pawl_check
from fabric.store import Store

AGENT_IDS = [f"agent:{agent_id}" for agent_id, _site in AGENTS]
STRATEGIST = HeuristicStrategist()


def author_measure(incident_class: str, dims: dict, rule: dict, metric: str, seed: int) -> ReplayEpisode:
    """Measure one episode exactly the way a juror will replay it (single solve path, same seed)."""
    task = sample_episode(incident_class, dims, seed)
    return replay(task, rule, metric, STRATEGIST)


def make_capsule(
    *,
    incident_class: str,
    dims: dict,
    rule: dict,
    metric: str,
    seeds: list[int],
    delta_pct: float,
    author: str = "agent:site-a",
) -> Capsule:
    baseline = 30.0  # illustrative absolute medians; the falsifiable number is delta_pct
    return build_capsule(
        kind="mitigation_rule",
        registry_version=REGISTRY_VERSION,
        context=Context(incident_class=incident_class, dims=dims),
        payload=Payload(rule=rule),
        claim=Claim(
            metric=metric,
            baseline_median=baseline,
            with_capsule_median=round(baseline * (1 + delta_pct / 100), 4),
            delta_pct=delta_pct,
            n_episodes=len(seeds),
        ),
        evidence=Evidence(
            scenario_seeds=list(seeds),
            conformance_required=[
                "no_flagged_flow_bypasses_inspection",
                "quarantine_reversible",
            ],
            trace_digest="0" * 64,
        ),
        provenance=Provenance(author=author, author_epoch=41, derived_from=[]),
        lifecycle=Lifecycle(state=LifecycleState.DRAFT, created_at_sim=10.0),
    )


def submit_capsule(capsule: Capsule, store: Store | None = None, events: list | None = None):
    store = store if store is not None else Store()
    sink = events if events is not None else []
    state, reason = submit(
        capsule,
        store,
        AGENT_IDS,
        sim_time=10.0,
        strategist=STRATEGIST,
        emit=lambda event_type, sim_time, **fields: sink.append({"type": event_type, **fields}),
    )
    return state, reason, store


# --- (a) fabricated claim → dies at counterfactual replay (stage 3) -----------------

def test_fabricated_claim_dies_at_counterfactual_replay():
    """A capsule claiming an effect its author never measured cannot survive replay of the
    author's own seeds: the -90% claim reproduces at roughly -55%, outside CLAIM_TOL."""
    capsule = make_capsule(
        incident_class="ddos_syn_flood",
        dims={"traffic_gbps": [1.0, 9.8], "site_class": ["branch", "campus", "dc"]},
        rule={"rate_limit_pps": 2000, "inspection_depth": 3},
        metric="solve_cost",
        seeds=list(range(2000, 2006)),
        delta_pct=-90.0,  # fabricated: nobody measured this number
    )
    state, reason, _store = submit_capsule(capsule)
    assert state == LifecycleState.REJECTED
    assert "counterfactual replay" in reason


# --- (b) overfit claim → passes counterfactual, dies at held-out (stage 4) ----------

def test_overfit_claim_dies_at_author_blind_heldout():
    """Cherry-picking lucky seeds makes a mediocre rule look great — and the claim *reproduces*
    on those seeds — but jurors' HMAC-private held-out sampling of the declared context is not
    cherry-pickable, and the rule's true median collapses there."""
    # Sampling 10% of devices is only right for tiny fleets; across the declared device range the
    # rule is decisively worse than baseline (population median ≈ +13%, win rate ≈ 0.28).
    dims = {"device_count": [10, 642], "site_class": ["branch", "campus", "dc"]}
    rule = {"quarantine_scope": "flagged_only", "sampled_fraction": 0.1}

    # The overfitting author deterministically scans seeds and keeps the 6 luckiest
    # (small-fleet episodes, where the rule genuinely shines).
    scanned = [
        (seed, author_measure("iot_anomaly_burst", dims, rule, "solve_cost", seed).delta_pct)
        for seed in range(1000, 1080)
    ]
    lucky = sorted(scanned, key=lambda item: item[1])[:6]
    lucky_seeds = [seed for seed, _delta in lucky]
    lucky_median = statistics.median(delta for _seed, delta in lucky)
    assert lucky_median < -50.0  # the cherry-picked story really does look convincing

    capsule = make_capsule(
        incident_class="iot_anomaly_burst",
        dims=dims,
        rule=rule,
        metric="solve_cost",
        seeds=lucky_seeds,
        delta_pct=round(lucky_median, 1),  # honest about the lucky seeds — that is the trick
    )
    state, reason, _store = submit_capsule(capsule)
    assert state == LifecycleState.REJECTED
    assert "author-blind held-out" in reason
    assert "counterfactual replay" not in reason  # it survived stage 3 — the claim reproduces


# --- (c) true but unsafe → passes 3–4, dies at invariant/conformance (stage 5) ------

def test_true_but_unsafe_dies_at_invariant_conformance():
    """A blanket subnet quarantine genuinely cuts solve cost (the local strategist even patches
    the scope live), but the rule *as declared* violates the constitution at campus sites inside
    its own declared context — validated knowledge must be safe as written."""
    dims = {"device_count": [500, 800], "site_class": ["dc", "campus"]}
    rule = {"quarantine_scope": "subnet", "sampled_fraction": 1.0}
    seeds = list(range(3000, 3006))

    episodes = [author_measure("iot_anomaly_burst", dims, rule, "solve_cost", s) for s in seeds]
    measured = statistics.median(e.delta_pct for e in episodes)
    assert measured < -40.0  # the gain is real, honestly measured

    capsule = make_capsule(
        incident_class="iot_anomaly_burst",
        dims=dims,
        rule=rule,
        metric="solve_cost",
        seeds=seeds,
        delta_pct=round(measured, 1),
    )
    state, reason, _store = submit_capsule(capsule)
    assert state == LifecycleState.REJECTED
    assert "invariant/conformance" in reason
    assert "no_blanket_subnet_block_without_compliance_class" in reason
    assert "counterfactual replay" not in reason and "held-out" not in reason


# --- (d) honest capsule → Pawl + Jury + shadow → ACTIVE with quorum cert -------------

def test_honest_capsule_reaches_active_with_quorum_cert():
    """An honestly measured, safe improvement passes every stage: Pawl, 3/3 jury quorum, and
    SHADOW_N shadow episodes with zero invariant hits — and its quorum cert verifies."""
    dims = {"traffic_gbps": [6.0, 10.0], "site_class": ["branch", "campus", "dc"]}
    rule = {"rate_limit_pps": 8000, "inspection_depth": 3}
    seeds = list(range(1000, 1006))

    episodes = [author_measure("ddos_syn_flood", dims, rule, "solve_cost", s) for s in seeds]
    measured = statistics.median(e.delta_pct for e in episodes)
    capsule = make_capsule(
        incident_class="ddos_syn_flood",
        dims=dims,
        rule=rule,
        metric="solve_cost",
        seeds=seeds,
        delta_pct=round(measured, 1),
    )
    assert pawl_check(capsule).ok

    events: list[dict] = []
    state, reason, store = submit_capsule(capsule, events=events)
    assert state == LifecycleState.CANDIDATE, reason

    shadow_tasks = [sample_episode("ddos_syn_flood", dims, 7000 + i) for i in range(SHADOW_N)]
    state, tracker, shadow_reason = run_shadow(
        capsule,
        shadow_tasks,
        store,
        sim_time=20.0,
        strategist=STRATEGIST,
        emit=lambda event_type, sim_time, **fields: events.append({"type": event_type, **fields}),
    )
    assert state == LifecycleState.ACTIVE, shadow_reason
    assert tracker.invariant_hits == 0

    # The proof of verification travels with the insight: lifecycle metadata (never the hashed
    # body) carries a quorum cert whose every ACCEPT signature verifies against juror identities.
    lifecycle = store.lifecycle_of(capsule.capsule_id)
    assert lifecycle["state"] == LifecycleState.ACTIVE.value
    assert lifecycle["confidence"] == tracker.wins / SHADOW_N
    cert = lifecycle["quorum_cert"]
    accepts = [vote for vote in cert["votes"] if vote["verdict"] == "ACCEPT"]
    assert len(accepts) >= QUORUM
    for vote in accepts:
        payload = vote_payload(
            capsule.capsule_id, vote["verdict"], vote["measured_delta"], cert["partition_view"]
        )
        assert keyring.verify(vote["juror"], payload, vote["sig"])
    assert capsule.provenance.author not in cert["jurors"]

    event_types = [event["type"] for event in events]
    assert event_types == ["JURY_VERDICT", "PROMOTED"]


# --- (e) every rejection names its stage --------------------------------------------

def test_every_rejection_names_its_stage_and_pawl_blocks_are_evented():
    """Reason strings are the audit trail: each of the three rejections above names the exact
    pipeline stage that killed it, and a Pawl rejection emits PAWL_BLOCK with the same reason."""
    capsule = make_capsule(
        incident_class="ddos_syn_flood",
        dims={"traffic_gbps": [6.0, 10.0], "site_class": ["branch", "campus", "dc"]},
        rule={"allowlist_subnet": "10.0.0.0/8"},  # no such action exists in the registry
        metric="solve_cost",
        seeds=list(range(4000, 4006)),
        delta_pct=-50.0,
    )
    events: list[dict] = []
    state, reason, _store = submit_capsule(capsule, events=events)
    assert state == LifecycleState.REJECTED
    assert reason.startswith("ratchet monotonicity:")
    assert "registry-only" in reason
    assert [event["type"] for event in events] == ["PAWL_BLOCK"]
    assert events[0]["reason"] == reason
