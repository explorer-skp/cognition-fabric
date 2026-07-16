"""M5 unit tests: probe determinism, excision-aware ACTIVE derivation (tombstoned ancestry and the
quarantine watermark), the pure reputation fold, and excise's transitive-closure edge cases
(BLUEPRINT §6.4, §4; binding decisions M5.1/M5.4/M5.5)."""

from __future__ import annotations

from agents.strategist import HeuristicStrategist
from fabric.capsule import (
    Claim,
    Context,
    Evidence,
    Lifecycle,
    LifecycleState,
    Payload,
    Provenance,
    build_capsule,
)
from fabric.config import REGISTRY_VERSION
from fabric.excision import descendants, excise, reputation
from fabric.gossip import ShadowLedger, derive_state, sign_shadow_record
from fabric.probes import GOLDEN_SUITE, clean_baselines, probe
from fabric.store import Store
from tests.test_dilemma_a import AGENT_IDS
from tests.test_m4_gossip_reuse import _records

STRATEGIST = HeuristicStrategist()
NODE_IDS = set(AGENT_IDS)


def _capsule(rule: dict, *, author: str = "agent:site-a", derived_from: tuple[str, ...] = (),
             dims: dict | None = None, seeds: tuple[int, ...] = (1, 2, 3, 4)):
    return build_capsule(
        kind="mitigation_rule",
        registry_version=REGISTRY_VERSION,
        context=Context(
            incident_class="ddos_syn_flood",
            dims=dims or {"traffic_gbps": [6.0, 10.0], "site_class": ["branch", "campus", "dc"]},
        ),
        payload=Payload(rule=dict(rule)),
        claim=Claim(metric="solve_cost", baseline_median=30.0, with_capsule_median=18.0,
                    delta_pct=-40.0, n_episodes=len(seeds)),
        evidence=Evidence(scenario_seeds=list(seeds), conformance_required=[], trace_digest="0" * 64),
        provenance=Provenance(author=author, author_epoch=1, derived_from=list(derived_from)),
        lifecycle=Lifecycle(state=LifecycleState.CANDIDATE, created_at_sim=0.0),
    )


def _quorum(ledger: ShadowLedger, capsule_id: str, base_seed: int) -> None:
    """A mesh quorum of signed records (unit-level: the pure derivation is under test here — the
    dilemma tests earn their records through real shadow_step replays)."""
    _records(ledger, capsule_id, [("agent:site-b", base_seed + i) for i in range(3)])
    _records(ledger, capsule_id, [("agent:site-c", base_seed + 10 + i) for i in range(3)])


# --- probe determinism (decision M5.1: pinned suite, deterministic baselines) --------

def test_probe_is_deterministic_and_clean_on_an_empty_fabric():
    """Same (store, ledger) in, byte-equal report out — and with no capsules the probe replays the
    clean baselines themselves, so it can never alarm."""
    assert len(GOLDEN_SUITE) == 12
    baselines = clean_baselines(STRATEGIST)
    assert baselines == clean_baselines(STRATEGIST)  # baselines are a pure function
    store, ledger = Store(), ShadowLedger()
    first = probe(store, ledger, STRATEGIST, baselines, node_ids=NODE_IDS)
    second = probe(store, ledger, STRATEGIST, baselines, node_ids=NODE_IDS)
    assert first == second
    assert first.clean and all(row.capsule_id is None for row in first.rows)
    assert all(row.metrics == row.baseline for row in first.rows)


def test_probe_is_deterministic_with_an_active_capsule():
    store, ledger = Store(), ShadowLedger()
    capsule = _capsule({"rate_limit_pps": 8000, "inspection_depth": 3})
    store.add(capsule)
    _quorum(ledger, capsule.capsule_id, 100)
    baselines = clean_baselines(STRATEGIST)
    first = probe(store, ledger, STRATEGIST, baselines, node_ids=NODE_IDS)
    assert first == probe(store, ledger, STRATEGIST, baselines, node_ids=NODE_IDS)
    assert any(row.capsule_id == capsule.capsule_id for row in first.rows)


# --- ACTIVE derivation ignores tombstoned-ancestor capsules (decision M5.5a) ----------

def test_derive_state_ignores_tombstoned_ancestor_capsules():
    """A capsule holding a full mesh quorum of records still refuses to promote while any
    transitive ancestor is tombstoned and its own QUARANTINED meta has not landed yet."""
    store, ledger = Store(), ShadowLedger()
    parent = _capsule({"rate_limit_pps": 8000, "inspection_depth": 3})
    child = _capsule({"rate_limit_pps": 10000, "inspection_depth": 3},
                     derived_from=(parent.capsule_id,))
    grandchild = _capsule({"rate_limit_pps": 12000, "inspection_depth": 3},
                          derived_from=(child.capsule_id,))
    for cap in (parent, child, grandchild):
        store.add(cap)
    _quorum(ledger, grandchild.capsule_id, 200)
    assert derive_state(store, ledger, grandchild.capsule_id, NODE_IDS).state == LifecycleState.ACTIVE

    store.tombstone(parent.capsule_id, 5.0, "poisoned")
    derived = derive_state(store, ledger, grandchild.capsule_id, NODE_IDS)
    assert derived.state != LifecycleState.ACTIVE  # transitive: grandparent tombstone blocks
    # The tombstoned capsule itself can never promote either.
    _quorum(ledger, parent.capsule_id, 300)
    assert derive_state(store, ledger, parent.capsule_id, NODE_IDS).state != LifecycleState.ACTIVE


# --- the quarantine watermark: only fresh evidence re-promotes (decision M5.5b) --------

def test_quarantine_watermark_requires_fresh_cert_and_fresh_records():
    store, ledger = Store(), ShadowLedger()
    capsule = _capsule({"rate_limit_pps": 8000, "inspection_depth": 3})
    store.add(capsule)
    lifecycle = capsule.lifecycle.model_dump(mode="json")
    lifecycle["quorum_cert"] = {"sim_time": 5.0}
    store.set_meta(capsule.capsule_id, lifecycle, 5.0)
    _quorum(ledger, capsule.capsule_id, 400)  # records at sim_time=1.0
    assert derive_state(store, ledger, capsule.capsule_id, NODE_IDS).state == LifecycleState.ACTIVE

    lifecycle["state"] = LifecycleState.QUARANTINED.value
    lifecycle["quarantined_at"] = 10.0
    store.set_meta(capsule.capsule_id, lifecycle, 10.0)
    derived = derive_state(store, ledger, capsule.capsule_id, NODE_IDS)
    assert derived.state == LifecycleState.QUARANTINED
    assert derived.records == 0  # pre-quarantine records are filtered by the watermark

    # Fresh records alone are not enough: the quorum cert is still pre-quarantine.
    for node, base in (("agent:site-b", 500), ("agent:site-c", 510)):
        for i in range(3):
            ledger.add(sign_shadow_record(
                node, capsule.capsule_id, base + i, "ddos_syn_flood", {}, True, 0, sim_time=11.0
            ))
    assert derive_state(store, ledger, capsule.capsule_id, NODE_IDS).state != LifecycleState.ACTIVE

    # A fresh (re-jury) cert + the fresh records re-promote; the watermark stays in the snapshot.
    lifecycle["state"] = LifecycleState.CANDIDATE.value
    lifecycle["quorum_cert"] = {"sim_time": 12.0}
    store.set_meta(capsule.capsule_id, lifecycle, 12.0)
    derived = derive_state(store, ledger, capsule.capsule_id, NODE_IDS)
    assert derived.state == LifecycleState.ACTIVE
    assert derived.records == 6  # exactly the post-watermark records


# --- the reputation fold (decision M5.4) -----------------------------------------------

def test_reputation_fold_over_synthetic_history():
    store, ledger = Store(), ShadowLedger()
    promoted = _capsule({"rate_limit_pps": 8000, "inspection_depth": 3}, author="agent:site-a")
    revoked_1 = _capsule({"rate_limit_pps": 6000, "inspection_depth": 3}, author="agent:site-a")
    revoked_2 = _capsule({"rate_limit_pps": 4000, "inspection_depth": 3}, author="agent:site-a")
    for cap in (promoted, revoked_1, revoked_2):
        store.add(cap)
    _quorum(ledger, promoted.capsule_id, 600)
    lifecycle = revoked_1.lifecycle.model_dump(mode="json")
    lifecycle["quorum_cert"] = {
        "sim_time": 1.0,
        "votes": [
            {"juror": "agent:site-b", "verdict": "ACCEPT", "measured_delta": -40.0, "sig": "x"},
            {"juror": "agent:site-c", "verdict": "REJECT", "measured_delta": 0.0, "sig": "x"},
        ],
    }
    store.set_meta(revoked_1.capsule_id, lifecycle, 1.0)
    store.tombstone(revoked_1.capsule_id, 2.0, "poisoned")
    store.tombstone(revoked_2.capsule_id, 3.0, "poisoned")

    # 1.0 + 0.05·1 − 0.4·2 = 0.25
    assert reputation(store, "agent:site-a", ledger=ledger, node_ids=NODE_IDS) == 0.25
    # Without a ledger the promotions credit is 0 (conservative): 1.0 − 0.8 = 0.2
    assert reputation(store, "agent:site-a") == 0.2
    # Only ACCEPT votes on revoked capsules are slashed — jurors have skin in the game.
    assert reputation(store, "agent:site-b", ledger=ledger, node_ids=NODE_IDS) == 0.8
    assert reputation(store, "agent:site-c", ledger=ledger, node_ids=NODE_IDS) == 1.0
    # Floored at 0: revoke the last capsule too → 1.0 − 1.2 < 0.
    store.tombstone(promoted.capsule_id, 4.0, "poisoned")
    assert reputation(store, "agent:site-a", ledger=ledger, node_ids=NODE_IDS) == 0.0


# --- excise: transitive closure, and only capsules still in play are quarantined -------

def test_excise_quarantines_the_transitive_closure_but_skips_settled_states():
    store = Store()
    parent = _capsule({"rate_limit_pps": 8000, "inspection_depth": 3})
    child = _capsule({"rate_limit_pps": 10000, "inspection_depth": 3},
                     derived_from=(parent.capsule_id,))
    grandchild = _capsule({"rate_limit_pps": 12000, "inspection_depth": 3},
                          derived_from=(child.capsule_id,))
    rejected = _capsule({"rate_limit_pps": 2000, "inspection_depth": 3},
                        derived_from=(parent.capsule_id,))
    unrelated = _capsule({"rate_limit_pps": 6000, "inspection_depth": 3})
    for cap in (parent, child, grandchild, rejected, unrelated):
        store.add(cap)
    meta = rejected.lifecycle.model_dump(mode="json")
    meta["state"] = LifecycleState.REJECTED.value
    store.set_meta(rejected.capsule_id, meta, 1.0)

    assert descendants(store, parent.capsule_id) == sorted(
        [child.capsule_id, grandchild.capsule_id, rejected.capsule_id]
    )
    result = excise(store, parent.capsule_id, 20.0, "unit: poisoned")
    assert set(result.quarantined) == {child.capsule_id, grandchild.capsule_id}
    for cid in result.quarantined:
        lifecycle = store.lifecycle_of(cid)
        assert lifecycle["state"] == LifecycleState.QUARANTINED.value
        assert lifecycle["quarantined_at"] == 20.0
    # A rejected descendant already influences nothing — it is skipped, not resurrected.
    assert store.lifecycle_of(rejected.capsule_id)["state"] == LifecycleState.REJECTED.value
    # Unrelated capsules and the tombstoned history itself are untouched.
    assert not store.is_tombstoned(unrelated.capsule_id)
    assert parent.capsule_id in store.adds and store.get(parent.capsule_id) is None
