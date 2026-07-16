"""Dilemma C — Consistency: storage is eventually consistent, meaning is scoped, decisions are
deterministic; a persistent overlap surviving a partition is an underspecified context, not a
conflict — heal converges every node on the identical arbitration winner, and Refine sharpens the
map instead of deleting a truth (BLUEPRINT §7, milestone M6).

Two islands each discover, validate, and mesh-promote their OWN genuinely-good capsule for the same
incident class through the real pipeline (real Pawl, real jury quorum, real shadow — no stuffed
wins) while a chaos-injected partition blocks anti-entropy between them. Heal reconciles every node
via the ordinary CRDT merge (`fabric.gossip.reconcile`) — no special-cased recovery. The two
capsules' declared contexts overlap; every node resolves the overlap identically via the same pure
`arbitrate()` every node already runs. Once that overlap has arbitrated `REFINE_THRESHOLD` times,
`refine_split` sharpens both contexts along the dimension where their evidence separates most, and
both refined capsules reach ACTIVE through the genuine pipeline — both contexts survive.
"""

from __future__ import annotations

import statistics

from chaos.injector import Partition, crash_node, partitioned, reconcile_within_partition
from fabric.arbitration import (
    Applicable,
    OverlapTracker,
    active_matches,
    arbitrate,
    record_overlap,
    refine_split,
)
from fabric.capsule import LifecycleState
from fabric.config import REFINE_THRESHOLD, SHADOW_MIN_NODES, SHADOW_QUORUM_N
from fabric.gossip import ShadowLedger, derive_state
from fabric.lifecycle import ShadowTracker, shadow_step, submit
from fabric.store import Store
from tests.test_dilemma_a import AGENT_IDS, STRATEGIST, author_measure, make_capsule
from world.taskgen import Task

ALL_SITES = ["branch", "campus", "dc"]
ISLAND_X = frozenset({"agent:site-a", "agent:site-b"})
ISLAND_Y = frozenset({"agent:site-c", "agent:site-d", "agent:site-e"})
PARTITION = Partition(islands=frozenset({ISLAND_X, ISLAND_Y}))

# Two genuinely-good, jury-passable rules whose declared context bands overlap on [5.0, 6.0] —
# prototype-verified (both pass 3/3 jury quorum honestly measured, see docs/PROGRESS.md S7).
X_DIMS = {"traffic_gbps": [1.0, 6.0], "site_class": ALL_SITES}
X_RULE = {"rate_limit_pps": 4000, "inspection_depth": 3}
Y_DIMS = {"traffic_gbps": [5.0, 12.0], "site_class": ALL_SITES}
Y_RULE = {"rate_limit_pps": 8000, "inspection_depth": 3}


def _capsule(dims: dict, rule: dict, seeds: list[int], author: str) -> tuple:
    episodes = [author_measure("ddos_syn_flood", dims, rule, "solve_cost", s) for s in seeds]
    median = statistics.median(e.delta_pct for e in episodes)
    cap = make_capsule(
        incident_class="ddos_syn_flood", dims=dims, rule=rule, metric="solve_cost",
        seeds=seeds, delta_pct=round(median, 1), author=author,
    )
    return cap, median


def _shadow_records(capsule, dims: dict, nodes: list[str], base_seed: int, sim_time: float,
                     per_node: int = 3) -> list:
    """Genuine shadow: `shadow_step` forks both branches through the one solve path (M5.6's "no
    stuffed wins" doctrine, held to the same standard here as the other dilemma tests). `per_node`
    evaluations per island member so `len(nodes) * per_node >= SHADOW_QUORUM_N` clears mesh quorum."""
    from fabric.jury import sample_episode
    from fabric.gossip import sign_shadow_record

    records = []
    for node in nodes:
        for i in range(per_node):
            task = sample_episode("ddos_syn_flood", dims, base_seed + hash_seed(node) + i * 31)
            tracker = shadow_step(capsule, task, STRATEGIST, ShadowTracker())
            records.append(sign_shadow_record(
                node, capsule.capsule_id, task.seed, task.incident_class, task.params,
                tracker.wins == 1, tracker.invariant_hits, sim_time,
            ))
    return records


def _fill_island_shadow(nodes: dict, island: frozenset[str], capsule, dims: dict, base_seed: float,
                         sim_time: float) -> None:
    """Every member of `island` independently already holds the same converged shadow evidence for
    `capsule` (as ordinary anti-entropy would produce over time) — the records are real
    (`_shadow_records`), just replicated directly into each island member's local ledger rather than
    earned through a separate reconcile pass, since the property under test is cross-island
    isolation, not within-island convergence timing."""
    records = _shadow_records(capsule, dims, sorted(island), base_seed, sim_time)
    for node in island:
        for record in records:
            nodes[node][1].add(record)


def _active(store: Store, ledger: ShadowLedger, capsule_id: str) -> bool:
    return derive_state(store, ledger, capsule_id, set(AGENT_IDS)).state == LifecycleState.ACTIVE


def _mesh(node_ids: frozenset[str]) -> dict[str, tuple[Store, ShadowLedger]]:
    return {node: (Store(), ShadowLedger()) for node in node_ids}


def _overlap_task(traffic: float, seed: int) -> Task:
    return Task(
        task_id=f"overlap-{seed}", incident_class="ddos_syn_flood", site_class="campus",
        params={"incident_class": "ddos_syn_flood", "site_class": "campus", "traffic_gbps": traffic,
                "device_count": 200},
        arrival_sim=0.0, seed=seed,
    )


def hash_seed(node: str) -> int:
    """Deterministic, process-independent per-node offset — never Python's builtin `hash()`
    (PYTHONHASHSEED-salted, would break byte-identical output)."""
    import hashlib

    return int(hashlib.sha256(node.encode("utf-8")).hexdigest(), 16) % 900


def _partitioned_mesh():
    """Each island discovers, validates, and mesh-promotes its own capsule for ddos_syn_flood while
    the partition blocks anti-entropy — both genuinely reach ACTIVE, each visible only on its own
    island, because the partition (a network fault, BLUEPRINT §12) never reaches into a store."""
    nodes = _mesh(ISLAND_X | ISLAND_Y)
    cap_x, _ = _capsule(X_DIMS, X_RULE, [21000 + i * 13 for i in range(6)], "agent:site-a")
    cap_y, _ = _capsule(Y_DIMS, Y_RULE, [22000 + i * 13 for i in range(6)], "agent:site-c")

    store_x, ledger_x = nodes["agent:site-a"]
    state, reason = submit(cap_x, store_x, AGENT_IDS, 10.0, strategist=STRATEGIST)
    assert state == LifecycleState.CANDIDATE, reason
    store_y, ledger_y = nodes["agent:site-c"]
    state, reason = submit(cap_y, store_y, AGENT_IDS, 10.5, strategist=STRATEGIST)
    assert state == LifecycleState.CANDIDATE, reason

    # Push CANDIDATE to same-island peers only (a partitioned author cannot reach the other island).
    for node in ISLAND_X:
        if node != "agent:site-a":
            nodes[node][0].add(cap_x)
            nodes[node][0].set_meta(cap_x.capsule_id, store_x.lifecycle_of(cap_x.capsule_id), 10.0)
    for node in ISLAND_Y:
        if node != "agent:site-c":
            nodes[node][0].add(cap_y)
            nodes[node][0].set_meta(cap_y.capsule_id, store_y.lifecycle_of(cap_y.capsule_id), 10.5)

    _fill_island_shadow(nodes, ISLAND_X, cap_x, X_DIMS, base_seed=100, sim_time=11.0)
    _fill_island_shadow(nodes, ISLAND_Y, cap_y, Y_DIMS, base_seed=200, sim_time=11.5)

    reconcile_within_partition(nodes, PARTITION)

    assert all(_active(*nodes[n], cap_x.capsule_id) for n in ISLAND_X)
    assert all(_active(*nodes[n], cap_y.capsule_id) for n in ISLAND_Y)
    assert not any(cap_y.capsule_id in nodes[n][0].adds for n in ISLAND_X)
    assert not any(cap_x.capsule_id in nodes[n][0].adds for n in ISLAND_Y)
    return nodes, cap_x, cap_y


# --- (a) partition produces two capsules for one class ------------------------------

def test_partition_produces_two_capsules_for_one_class():
    nodes, cap_x, cap_y = _partitioned_mesh()
    for node in ISLAND_X:
        assert _active(*nodes[node], cap_x.capsule_id)
    for node in ISLAND_Y:
        assert _active(*nodes[node], cap_y.capsule_id)
    assert not any(cap_y.capsule_id in nodes[n][0].adds for n in ISLAND_X)
    assert not any(cap_x.capsule_id in nodes[n][0].adds for n in ISLAND_Y)


# --- (b) heal: deterministic identical arbitration on every node ---------------------

def _healed_mesh():
    nodes, cap_x, cap_y = _partitioned_mesh()
    reconcile_within_partition(nodes, None)  # heal: partition=None is unconditional full reconcile
    return nodes, cap_x, cap_y


def test_heal_converges_every_node_and_arbitration_is_identical():
    nodes, cap_x, cap_y = _healed_mesh()
    for node in ISLAND_X | ISLAND_Y:
        store, ledger = nodes[node]
        assert _active(store, ledger, cap_x.capsule_id)
        assert _active(store, ledger, cap_y.capsule_id)

    task = _overlap_task(5.5, seed=999)
    winners = set()
    for node in sorted(ISLAND_X | ISLAND_Y):
        store, ledger = nodes[node]
        matches = active_matches(store, ledger, task, set(AGENT_IDS))
        assert {m.capsule.capsule_id for m in matches} == {cap_x.capsule_id, cap_y.capsule_id}
        winner = arbitrate(matches)
        winners.add(winner.capsule.capsule_id)
    assert len(winners) == 1, f"every node must pick the same winner, got {winners}"


# --- (c) persistent overlap triggers Refine; both contexts survive -------------------

def test_persistent_overlap_triggers_refine_and_both_contexts_survive():
    nodes, cap_x, cap_y = _healed_mesh()
    store, ledger = nodes["agent:site-a"]
    tracker = OverlapTracker()
    triggered = False
    for seed in (1001, 1002, 1003):
        task = _overlap_task(5.5, seed)
        matches = active_matches(store, ledger, task, set(AGENT_IDS))
        winner_app = arbitrate(matches)
        loser_app = next(m for m in matches if m.capsule.capsule_id != winner_app.capsule.capsule_id)
        tracker, triggered = record_overlap(tracker, winner_app, loser_app)
    assert triggered, f"REFINE_THRESHOLD={REFINE_THRESHOLD} overlaps must trigger Refine"

    result = refine_split(winner_app, loser_app)
    assert result.dimension == "traffic_gbps"
    assert result.winner_dims is not None and result.loser_dims is not None  # both contexts survive
    w_lo, w_hi = result.winner_dims["traffic_gbps"]
    l_lo, l_hi = result.loser_dims["traffic_gbps"]
    assert w_hi <= l_lo or l_hi <= w_lo, "refined bands must not re-overlap"
    assert (w_lo, w_hi) != (l_lo, l_hi)

    # Both refined capsules reach ACTIVE through the genuine pipeline — the map is sharpened, not
    # a truth deleted.
    winner_seeds = [23000 + i * 13 for i in range(6)]
    loser_seeds = [24000 + i * 13 for i in range(6)]
    w_rule = winner_app.capsule.payload.rule
    l_rule = loser_app.capsule.payload.rule
    refined_winner, _ = _capsule(result.winner_dims, w_rule, winner_seeds, winner_app.capsule.provenance.author)
    refined_loser, _ = _capsule(result.loser_dims, l_rule, loser_seeds, loser_app.capsule.provenance.author)

    for i, cap in enumerate((refined_winner, refined_loser)):
        state, reason = submit(cap, store, AGENT_IDS, 30.0, strategist=STRATEGIST)
        assert state == LifecycleState.CANDIDATE, reason
        for record in _shadow_records(cap, cap.context.dims, sorted(ISLAND_X | ISLAND_Y),
                                       base_seed=500 + i * 1000, sim_time=31.0):
            ledger.add(record)
        assert _active(store, ledger, cap.capsule_id), f"refined capsule must reach ACTIVE — {cap.context.dims}"


# --- units: chaos/injector.py pure functions ------------------------------------------

def test_partitioned_blocks_cross_island_only():
    assert partitioned("agent:site-a", "agent:site-c", PARTITION)
    assert not partitioned("agent:site-a", "agent:site-b", PARTITION)
    assert not partitioned("agent:site-a", "agent:site-b", None)


def test_crash_node_round_trips_the_store_intact():
    store = Store()
    cap, _ = _capsule(X_DIMS, X_RULE, [25000 + i * 13 for i in range(6)], "agent:site-a")
    store.add(cap)
    store.set_meta(cap.capsule_id, {"state": "CANDIDATE"}, 1.0)
    reloaded = crash_node(store)
    assert reloaded == store


def test_provisional_cert_demotion_below_and_above_majority():
    from fabric.lifecycle import provisional_cert_demotion

    n = 5  # mesh size; majority = ceil((5+1)/2) = 3
    assert provisional_cert_demotion({"partition_view": "agent:site-a|agent:site-b"}, n)
    assert not provisional_cert_demotion(
        {"partition_view": "agent:site-a|agent:site-b|agent:site-c"}, n
    )
    assert not provisional_cert_demotion(None, n)
    assert not provisional_cert_demotion({}, n)
