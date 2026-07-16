"""M4 unit + property tests: deterministic arbitration (incl. the hash tie-break), GOSSIP_PUSH
signature verification, mesh-wide derived promotion (and its unreachability from one node), gossip
convergence as a CRDT property, and organic derived-capsule provenance (BLUEPRINT §5, §7, §10 M4)."""

from __future__ import annotations

import copy
import hashlib
import statistics

from agents.agent import FabricAgent
from agents.strategist import HeuristicStrategist
from fabric.arbitration import Applicable, applies, arbitrate
from fabric.capsule import (
    Context,
    Evidence,
    Claim,
    Lifecycle,
    LifecycleState,
    Payload,
    Provenance,
    build_capsule,
)
from fabric.config import REGISTRY_VERSION, SHADOW_MIN_NODES, SHADOW_QUORUM_N
from fabric.gossip import (
    ShadowLedger,
    apply_push,
    build_push,
    derive_state,
    digest,
    reconcile,
    sign_shadow_record,
    verify_push,
)
from fabric.lifecycle import submit
from fabric.store import Store
from world.taskgen import Task
from tests.test_dilemma_a import AGENT_IDS, author_measure, make_capsule

STRATEGIST = HeuristicStrategist()
NODE_IDS = set(AGENT_IDS)


def _ddos_capsule(rule: dict, dims: dict, delta_pct: float, seeds=range(6)):
    return make_capsule(
        incident_class="ddos_syn_flood",
        dims=dims,
        rule=rule,
        metric="solve_cost",
        seeds=list(seeds),
        delta_pct=delta_pct,
    )


def _task(incident_class: str, site: str, traffic: float) -> Task:
    return Task(
        task_id="t",
        incident_class=incident_class,
        site_class=site,
        params={
            "incident_class": incident_class,
            "site_class": site,
            "traffic_gbps": traffic,
            "device_count": 200,
        },
        arrival_sim=0.0,
        seed=1,
    )


# --- applies: context predicate --------------------------------------------------

def test_applies_matches_class_and_every_declared_dim():
    cap = _ddos_capsule(
        {"rate_limit_pps": 8000, "inspection_depth": 3},
        {"traffic_gbps": [4.0, 8.0], "site_class": ["branch", "campus"]},
        -40.0,
    )
    assert applies(cap, _task("ddos_syn_flood", "branch", 6.0))
    assert not applies(cap, _task("ddos_syn_flood", "branch", 10.0))  # traffic outside interval
    assert not applies(cap, _task("ddos_syn_flood", "dc", 6.0))  # site outside the set
    assert not applies(cap, _task("iot_anomaly_burst", "branch", 6.0))  # wrong class


# --- arbitrate: priority → confidence×effect → hash tie-break --------------------

def test_arbitrate_priority_class_dominates_confidence():
    """A COMPLIANCE-scoped context outranks an unscoped one lexicographically, even when the
    unscoped capsule has far higher confidence × |effect|."""
    branch_dims = {"traffic_gbps": [4.0, 8.0], "site_class": ["branch"]}
    dc_dims = {"traffic_gbps": [4.0, 8.0], "site_class": ["dc"]}
    compliance = _ddos_capsule({"rate_limit_pps": 8000, "inspection_depth": 3}, dc_dims, -30.0)
    unscoped = _ddos_capsule({"rate_limit_pps": 6000, "inspection_depth": 3}, branch_dims, -90.0)
    winner = arbitrate([Applicable(unscoped, 1.0), Applicable(compliance, 0.1)])
    assert winner.capsule.capsule_id == compliance.capsule_id


def test_arbitrate_confidence_effect_within_same_priority():
    dims = {"traffic_gbps": [4.0, 8.0], "site_class": ["branch"]}
    strong = _ddos_capsule({"rate_limit_pps": 8000, "inspection_depth": 3}, dims, -40.0)
    weak = _ddos_capsule({"rate_limit_pps": 6000, "inspection_depth": 3}, dims, -40.0)
    # Same |effect|, so confidence breaks it: 0.9 beats 0.3.
    assert arbitrate([Applicable(weak, 0.3), Applicable(strong, 0.9)]).capsule.capsule_id == strong.capsule_id


def test_arbitrate_hash_tie_break_is_deterministic_and_order_independent():
    """Equal priority and equal confidence × |effect| ⇒ the capsule whose id hashes smaller wins,
    regardless of input order."""
    dims = {"traffic_gbps": [4.0, 8.0], "site_class": ["branch"]}
    c1 = _ddos_capsule({"rate_limit_pps": 8000, "inspection_depth": 3}, dims, -40.0)
    c2 = _ddos_capsule({"rate_limit_pps": 6000, "inspection_depth": 3}, dims, -40.0)
    expected = min(
        (c1, c2), key=lambda c: int(hashlib.sha256(c.capsule_id.encode()).hexdigest(), 16)
    )
    apps = [Applicable(c1, 0.8), Applicable(c2, 0.8)]
    assert arbitrate(apps).capsule.capsule_id == expected.capsule_id
    assert arbitrate(list(reversed(apps))).capsule.capsule_id == expected.capsule_id


def test_arbitrate_empty_is_none():
    assert arbitrate([]) is None


# --- GOSSIP_PUSH: verify every signature before trusting anything ----------------

def _certified_capsule():
    dims = {"traffic_gbps": [6.0, 10.0], "site_class": ["branch", "campus", "dc"]}
    rule = {"rate_limit_pps": 8000, "inspection_depth": 3}
    seeds = list(range(1000, 1006))
    measured = statistics.median(
        author_measure("ddos_syn_flood", dims, rule, "solve_cost", s).delta_pct for s in seeds
    )
    cap = _ddos_capsule(rule, dims, round(measured, 1), seeds=seeds)
    store = Store()
    state, reason = submit(cap, store, AGENT_IDS, sim_time=10.0, strategist=STRATEGIST)
    assert state == LifecycleState.CANDIDATE, reason
    cert = store.lifecycle_of(cap.capsule_id)["quorum_cert"]
    return cap, cert


def test_verify_push_accepts_valid_and_rejects_tampering():
    cap, cert = _certified_capsule()
    push = build_push(cap, cert)
    ok, _reason = verify_push(push, NODE_IDS)
    assert ok

    tampered = copy.deepcopy(cert)
    tampered["votes"][0]["sig"] = "0" * 64
    ok, why = verify_push(build_push(cap, tampered), NODE_IDS)
    assert not ok and "juror signature" in why

    ok, why = verify_push(push, NODE_IDS - {cap.provenance.author})
    assert not ok and "not known to the mesh" in why


def test_apply_push_stores_candidate_never_active():
    cap, cert = _certified_capsule()
    peer = Store()
    apply_push(peer, build_push(cap, cert), sim_time=12.0)
    lifecycle = peer.lifecycle_of(cap.capsule_id)
    assert lifecycle["state"] == LifecycleState.CANDIDATE.value
    assert lifecycle["quorum_cert"]["jurors"] == cert["jurors"]


# --- derived promotion: mesh quorum, unreachable from one node -------------------

def _records(ledger, cap_id, node_seeds, win=True, invariant_hits=0):
    for node, seed in node_seeds:
        ledger.add(
            sign_shadow_record(
                node, cap_id, seed, "ddos_syn_flood", {}, win, invariant_hits, sim_time=1.0
            )
        )


def _seeded_store():
    cap = _ddos_capsule(
        {"rate_limit_pps": 8000, "inspection_depth": 3},
        {"traffic_gbps": [6.0, 10.0], "site_class": ["branch", "campus", "dc"]},
        -50.0,
    )
    store = Store()
    store.add(cap)
    return store, cap


def test_derive_state_promotes_at_mesh_quorum():
    store, cap = _seeded_store()
    ledger = ShadowLedger()
    _records(ledger, cap.capsule_id, [("agent:site-b", 100 + i) for i in range(3)])
    _records(ledger, cap.capsule_id, [("agent:site-c", 200 + i) for i in range(3)])
    derived = derive_state(store, ledger, cap.capsule_id, NODE_IDS)
    assert derived.state == LifecycleState.ACTIVE
    assert derived.records == SHADOW_QUORUM_N and derived.nodes == SHADOW_MIN_NODES
    assert derived.confidence == 1.0


def test_promotion_unreachable_from_a_single_node():
    """SHADOW_MIN_NODES guards against a lone (possibly rogue) node self-promoting: six wins from one
    node is not enough — promotion needs corroboration across the mesh."""
    store, cap = _seeded_store()
    ledger = ShadowLedger()
    _records(ledger, cap.capsule_id, [("agent:site-b", 300 + i) for i in range(SHADOW_QUORUM_N)])
    derived = derive_state(store, ledger, cap.capsule_id, NODE_IDS)
    assert derived.records == SHADOW_QUORUM_N and derived.nodes == 1
    assert derived.state != LifecycleState.ACTIVE


def test_promotion_needs_win_supermajority_and_zero_invariant_hits():
    store, cap = _seeded_store()
    # Six records from two nodes, but only four wins → below SHADOW_QUORUM_WIN.
    few_wins = ShadowLedger()
    _records(few_wins, cap.capsule_id, [("agent:site-b", 400 + i) for i in range(3)])
    _records(few_wins, cap.capsule_id, [("agent:site-c", 410 + i) for i in range(1)])
    _records(few_wins, cap.capsule_id, [("agent:site-c", 420 + i) for i in range(2)], win=False)
    assert derive_state(store, few_wins, cap.capsule_id, NODE_IDS).state != LifecycleState.ACTIVE

    # Six wins from two nodes, but one carries an invariant hit → zero-tolerance rejects.
    with_hit = ShadowLedger()
    _records(with_hit, cap.capsule_id, [("agent:site-b", 500 + i) for i in range(3)])
    _records(with_hit, cap.capsule_id, [("agent:site-c", 510 + i) for i in range(2)])
    _records(with_hit, cap.capsule_id, [("agent:site-c", 520)], invariant_hits=1)
    assert derive_state(store, with_hit, cap.capsule_id, NODE_IDS).state != LifecycleState.ACTIVE


def test_foreign_node_records_do_not_count():
    store, cap = _seeded_store()
    ledger = ShadowLedger()
    _records(ledger, cap.capsule_id, [("agent:site-b", 600 + i) for i in range(3)])
    _records(ledger, cap.capsule_id, [("agent:site-c", 610 + i) for i in range(3)])
    # A stranger not in the mesh cannot pad the quorum.
    known = {"agent:site-b"}
    assert derive_state(store, ledger, cap.capsule_id, known).nodes == 1
    assert derive_state(store, ledger, cap.capsule_id, known).state != LifecycleState.ACTIVE


# --- gossip convergence: CRDT property ------------------------------------------

def _divergent_states():
    """Two nodes with overlapping-but-different records: adds, a tombstone, a meta, shadow records."""
    c1 = _ddos_capsule({"rate_limit_pps": 8000, "inspection_depth": 3}, {"traffic_gbps": [6.0, 10.0], "site_class": ["branch"]}, -50.0)
    c2 = _ddos_capsule({"rate_limit_pps": 6000, "inspection_depth": 3}, {"traffic_gbps": [4.0, 8.0], "site_class": ["campus"]}, -45.0)
    c3 = _ddos_capsule({"rate_limit_pps": 4000, "inspection_depth": 3}, {"traffic_gbps": [2.0, 6.0], "site_class": ["dc"]}, -40.0)

    sa, la = Store(), ShadowLedger()
    sa.add(c1)
    sa.add(c2)
    meta = c1.lifecycle.model_dump(mode="json")
    meta["state"] = LifecycleState.CANDIDATE.value
    meta["quorum_cert"] = {"jurors": ["agent:site-b"], "votes": []}
    sa.set_meta(c1.capsule_id, meta, sim_time=5.0)
    sa.tombstone("dead" + "0" * 60, sim_time=3.0, reason="revoked")
    _records(la, c1.capsule_id, [("agent:site-b", 1), ("agent:site-c", 2)])

    sb, lb = Store(), ShadowLedger()
    sb.add(c2)
    sb.add(c3)
    _records(lb, c1.capsule_id, [("agent:site-c", 2)])  # overlaps with la
    _records(lb, c3.capsule_id, [("agent:site-d", 9)])
    return (sa, la), (sb, lb)


def test_gossip_reconcile_converges_to_equal_digests():
    (sa, la), (sb, lb) = _divergent_states()
    assert digest(sa, la) != digest(sb, lb)
    reconcile((sa, la), (sb, lb))
    assert digest(sa, la) == digest(sb, lb)
    assert sa == sb and la == lb


def test_gossip_reconcile_is_order_independent():
    forward = _divergent_states()
    reconcile(forward[0], forward[1])
    reverse = _divergent_states()
    reconcile(reverse[1], reverse[0])  # opposite direction, fresh copies
    assert digest(*forward[0]) == digest(*reverse[0])
    assert forward[0][0] == reverse[0][0] and forward[0][1] == reverse[0][1]


# --- organic descendants: derived capsules carry provenance ---------------------

def test_reuse_refinement_authors_a_derived_capsule_with_derived_from():
    """A near-optimal prior whose reuse-solve refinement discovers a strictly better rule spawns a
    derived capsule whose provenance points back at the prior (BLUEPRINT §5; M5 needs descendants)."""
    identities = list(AGENT_IDS)
    from ui.events import EventStream

    events = EventStream()
    agent = FabricAgent(
        agent_id="site-a",
        site_class="branch",
        strategist=HeuristicStrategist(),
        events=events,
        agent_ids=identities,
        node_ids=set(identities),
    )
    # Prior: one refinement step from the traffic-8 optimum (rate 8000), made ACTIVE by mesh records.
    prior = build_capsule(
        kind="mitigation_rule",
        registry_version=REGISTRY_VERSION,
        context=Context(
            incident_class="ddos_syn_flood",
            dims={"traffic_gbps": [7.0, 9.0], "site_class": ["branch", "campus", "dc"]},
        ),
        payload=Payload(rule={"rate_limit_pps": 6000, "inspection_depth": 3}),
        claim=Claim(
            metric="solve_cost", baseline_median=30.0, with_capsule_median=15.0,
            delta_pct=-50.0, n_episodes=4,
        ),
        evidence=Evidence(
            scenario_seeds=[1, 2, 3, 4],
            conformance_required=["no_flagged_flow_bypasses_inspection", "quarantine_reversible"],
            trace_digest="0" * 64,
        ),
        provenance=Provenance(author="agent:site-z", author_epoch=1, derived_from=[]),
        lifecycle=Lifecycle(state=LifecycleState.CANDIDATE, created_at_sim=0.0),
    )
    agent.store.add(prior)
    _records(agent.ledger, prior.capsule_id, [("agent:site-b", 700 + i) for i in range(3)])
    _records(agent.ledger, prior.capsule_id, [("agent:site-c", 710 + i) for i in range(3)])
    assert derive_state(agent.store, agent.ledger, prior.capsule_id, set(identities)).state == LifecycleState.ACTIVE

    for i in range(5):
        agent.handle_task(_task_hi(i), float(i))

    derived = [
        cap
        for cid in agent.store.live_ids()
        if (cap := agent.store.get(cid)) is not None and cap.provenance.derived_from
    ]
    assert len(derived) == 1
    assert derived[0].provenance.derived_from == [prior.capsule_id]
    assert derived[0].payload.rule["rate_limit_pps"] == 8000  # the refinement it discovered
    authored = [r for r in events.records() if r["type"] == "AUTHOR" and r["derived_from"]]
    assert authored and authored[0]["derived_from"] == [prior.capsule_id]


def _task_hi(i: int) -> Task:
    return Task(
        task_id=f"x{i}",
        incident_class="ddos_syn_flood",
        site_class="branch",
        params={
            "incident_class": "ddos_syn_flood",
            "site_class": "branch",
            "traffic_gbps": 8.0,
            "device_count": 200,
        },
        arrival_sim=float(i),
        seed=9000 + i,
    )
