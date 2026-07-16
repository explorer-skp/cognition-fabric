"""demo-chaos — scripted Act 3 of the RUNBOOK (BLUEPRINT §9, §11, milestone M7).

The immune system, live: a rogue site (`site-e`) submits a blatant poison (blocked at the border,
in red, with the reason string) and a subtle poison — an aggressive rate-limit rule that genuinely
improves its claimed metric on held-out scenarios and reaches ACTIVE through the real pipeline. A
Sentinel probe catches its off-claim KPI regression within one probe period; bisect finds the exact
culprit; Excision tombstones it and quarantines its one organic descendant — twelve capsules to ten,
never to zero.

Continues into partition/heal/Refine and minority-cert demotion (BLUEPRINT §6.2, §7.4-7.5, milestone
M6): a chaos-injected partition splits the mesh into two islands, each of which discovers and
mesh-promotes its own genuinely-good capsule for the same congestion class through the real
pipeline; heal reconciles every node via the ordinary CRDT merge and every node resolves the
resulting overlap identically; persistent overlap triggers Refine, sharpening both capsules' scopes
along the dimension where their evidence separates most; the minority island's cert demotes on heal
and re-earns ACTIVE, the majority island's does not. Same mechanism `tests/test_dilemma_c.py` proves.

Default output is plain, deterministic text (same discipline as `demo_smoke.py`/`demo_ratchet.py`).
`--tui` drives `ui.tui.Dashboard` live; `--pace=live` inserts RUNBOOK narration beats.
"""

from __future__ import annotations

import argparse
import hashlib
import statistics
import time

from agents.strategist import HeuristicStrategist
from agents.agent import AGENTS, FabricAgent
from chaos.injector import Partition, reconcile_within_partition
from fabric.arbitration import (
    OverlapTracker,
    active_matches,
    arbitrate,
    record_overlap,
    refine_split,
)
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
from fabric.config import REGISTRY_VERSION, REP_ISOLATION_FLOOR
from fabric.excision import excise, reputation
from fabric.gossip import ShadowLedger, derive_state, sign_shadow_record
from fabric.jury import replay, sample_episode
from fabric.lifecycle import (
    ShadowTracker,
    demote_provisional,
    provisional_cert_demotion,
    shadow_step,
    submit,
)
from fabric.pawl import pawl_check
from fabric.probes import Sentinel, bisect_culprit, suspects
from fabric.store import Store
from ui.events import EventStream
from ui.tui import Dashboard, DashboardState, build_fabric_rows, build_mesh_rows
from world.taskgen import Task

CHAOS_SEED = 909090
ROGUE = "agent:site-e"
ALL_SITES = ["branch", "campus", "dc"]
AGENT_IDS = [f"agent:{aid}" for aid, _sc in AGENTS]
NODE_IDS = set(AGENT_IDS)
STRATEGIST = HeuristicStrategist()

# DECISION: the subtle poison is the exact recipe validated in tests/test_dilemma_b.py — an
# aggressive rate-limit rule anchored one refinement-basin below the traffic optimum, so the
# 3-attempt reuse budget can't escape it on golden scenarios. No world/scenarios.py edit, no
# threshold edit (binding decision M5.6): the honest claim (attempts savings) is what gets it in.
POISON_RULE = {"rate_limit_pps": 4000, "inspection_depth": 3}
POISON_DIMS = {"traffic_gbps": [4.0, 9.0], "site_class": ALL_SITES}

# Ten honest capsules across all three incident classes, each genuinely near-optimal for its band
# (BLUEPRINT §6.5: the border wall works on real claims too).
#
# DECISION: the two ddos bands are deliberately kept OUTSIDE the poison's [4.0, 9.0] golden
# footprint (traffic 4/6/7/8 — fabric/probes.py's GOLDEN_SUITE). An honest capsule covering the
# poison's regression window would win arbitration there and *mask* the harm from the Sentinel
# (the same masking behavior bisect's in-isolation probing exists to survive, fabric/probes.py) —
# this build's fabric is honest, so if a stronger capsule already serves that window, the poison
# genuinely does no visible harm there and there is nothing to detect. The demo keeps the poison's
# regression window uncontested, matching RUNBOOK Act 3's "watch this one get in" framing.
_HONEST_SPECS = [
    ("ddos_syn_flood", {"traffic_gbps": [1.0, 3.0], "site_class": ALL_SITES},
     {"rate_limit_pps": 2000, "inspection_depth": 3}, "agent:site-a"),
    ("ddos_syn_flood", {"traffic_gbps": [10.0, 12.0], "site_class": ALL_SITES},
     {"rate_limit_pps": 10000, "inspection_depth": 3}, "agent:site-d"),
    ("iot_anomaly_burst", {"device_count": [10, 100], "site_class": ALL_SITES},
     {"quarantine_scope": "flagged_only", "sampled_fraction": 0.1}, "agent:site-a"),
    ("iot_anomaly_burst", {"device_count": [100, 150], "site_class": ALL_SITES},
     {"quarantine_scope": "flagged_only", "sampled_fraction": 0.25}, "agent:site-b"),
    ("iot_anomaly_burst", {"device_count": [150, 300], "site_class": ALL_SITES},
     {"quarantine_scope": "flagged_only", "sampled_fraction": 0.5}, "agent:site-b"),
    ("iot_anomaly_burst", {"device_count": [300, 400], "site_class": ALL_SITES},
     {"quarantine_scope": "flagged_only", "sampled_fraction": 0.5}, "agent:site-c"),
    ("iot_anomaly_burst", {"device_count": [400, 700], "site_class": ALL_SITES},
     {"quarantine_scope": "flagged_only", "sampled_fraction": 1.0}, "agent:site-c"),
    ("cert_expiry_storm", {"site_class": ["branch"]},
     {"retry_backoff_ms": 200, "block_ttl_s": 120}, "agent:site-d"),
    ("cert_expiry_storm", {"site_class": ["campus"]},
     {"retry_backoff_ms": 200, "block_ttl_s": 120}, "agent:site-a"),
    ("cert_expiry_storm", {"site_class": ["dc"]},
     {"retry_backoff_ms": 200, "block_ttl_s": 120}, "agent:site-c"),
]

# Partition/heal/Refine (RUNBOOK Act 3, 8:45-10:15): two islands, each with its own genuinely-good,
# jury-passable congestion-class rule whose declared band overlaps the other's on [5.0, 6.0] —
# prototype-verified the same way as tests/test_dilemma_c.py (both pass 3/3 jury quorum honestly
# measured). Island X is the minority side (2 of 5 nodes): its cert demotes on heal; island Y (3 of
# 5) is the majority side and stays authoritative.
ISLAND_X = frozenset({"agent:site-a", "agent:site-b"})
ISLAND_Y = frozenset({"agent:site-c", "agent:site-d", "agent:site-e"})
PARTITION = Partition(islands=frozenset({ISLAND_X, ISLAND_Y}))
X_DIMS = {"traffic_gbps": [1.0, 6.0], "site_class": ALL_SITES}
X_RULE = {"rate_limit_pps": 4000, "inspection_depth": 3}
Y_DIMS = {"traffic_gbps": [5.0, 12.0], "site_class": ALL_SITES}
Y_RULE = {"rate_limit_pps": 8000, "inspection_depth": 3}

_BEAT_SECONDS = 3.0


def _det_int(*parts: str) -> int:
    """A deterministic, process-independent integer from string parts — never Python's builtin
    `hash()`, which is salted per-process (PYTHONHASHSEED) and would silently break the byte-
    identical-output guarantee this project's demos depend on (same pattern as
    `agents/agent.py`'s `_evidence_seeds`)."""
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return int(digest, 16)


def _measured_capsule(incident_class: str, dims: dict, rule: dict, seeds: list[int], author: str) -> Capsule:
    """Measure the claim exactly the way a juror will replay it (single solve path, decision M3.1),
    then build the capsule — a real author never invents a number."""
    episodes = [replay(sample_episode(incident_class, dims, s), rule, "solve_cost", STRATEGIST) for s in seeds]
    median = statistics.median(e.delta_pct for e in episodes)
    return build_capsule(
        kind="mitigation_rule", registry_version=REGISTRY_VERSION,
        context=Context(incident_class=incident_class, dims=dims), payload=Payload(rule=dict(rule)),
        claim=Claim(metric="solve_cost", baseline_median=30.0,
                    with_capsule_median=round(30.0 * (1 + median / 100), 4),
                    delta_pct=round(median, 1), n_episodes=len(seeds)),
        evidence=Evidence(scenario_seeds=list(seeds),
                           conformance_required=["no_flagged_flow_bypasses_inspection", "quarantine_reversible"],
                           trace_digest="0" * 64),
        provenance=Provenance(author=author, author_epoch=1, derived_from=[]),
        lifecycle=Lifecycle(state=LifecycleState.DRAFT, created_at_sim=0.0),
    )


def _mesh_shadow(store: Store, ledger: ShadowLedger, capsule: Capsule, dims: dict, base_seed: int,
                  sim_time: float) -> None:
    """Real two-node mesh shadow — `shadow_step` forks both branches through the one solve path;
    no stuffed wins (decision M5.6: no bypasses)."""
    for node in ("agent:site-b", "agent:site-c"):
        for i in range(3):
            task = sample_episode(
                capsule.context.incident_class, dims,
                base_seed + _det_int(node, capsule.capsule_id) % 97 + i * 31,
            )
            tracker = shadow_step(capsule, task, STRATEGIST, ShadowTracker())
            ledger.add(sign_shadow_record(
                node, capsule.capsule_id, task.seed, task.incident_class, task.params,
                tracker.wins == 1, tracker.invariant_hits, sim_time,
            ))


def _active(store: Store, ledger: ShadowLedger, capsule_id: str) -> bool:
    return derive_state(store, ledger, capsule_id, NODE_IDS).state == LifecycleState.ACTIVE


def _fill_island_shadow(mesh: dict, island: frozenset, capsule: Capsule, dims: dict,
                         base_seed: int, sim_time: float, per_node: int = 3) -> None:
    """Real shadow (`shadow_step`, no stuffed wins) for every member of `island`, replicated into
    each member's own local ledger — as ordinary anti-entropy would already have produced within an
    island that has been reconciling among itself (same pattern as `tests/test_dilemma_c.py`)."""
    records = []
    for node in sorted(island):
        for i in range(per_node):
            task = sample_episode(
                capsule.context.incident_class, dims, base_seed + _det_int(node) % 900 + i * 31,
            )
            tracker = shadow_step(capsule, task, STRATEGIST, ShadowTracker())
            records.append(sign_shadow_record(
                node, capsule.capsule_id, task.seed, task.incident_class, task.params,
                tracker.wins == 1, tracker.invariant_hits, sim_time,
            ))
    for node in island:
        for record in records:
            mesh[node][1].add(record)


def _overlap_task(traffic: float, seed: int) -> Task:
    return Task(
        task_id=f"overlap-{seed}", incident_class="ddos_syn_flood", site_class="campus",
        params={"incident_class": "ddos_syn_flood", "site_class": "campus", "traffic_gbps": traffic,
                "device_count": 200},
        arrival_sim=0.0, seed=seed,
    )


def _beat(pace: str, label: str) -> None:
    print(f"  … {label}")
    if pace == "live":
        time.sleep(_BEAT_SECONDS)


def build_prewarmed_fabric(events: EventStream) -> tuple[Store, ShadowLedger, Capsule, Capsule]:
    """The fresh seeded world with a pre-warmed fabric (RUNBOOK Act 3): ten honest capsules plus the
    subtle poison, each through the genuine pipeline — real Pawl, real jury quorum, real two-node
    shadow. Returns (store, ledger, poison, descendant)."""
    store, ledger = Store(), ShadowLedger()
    tick = 10.0
    for incident_class, dims, rule, author in _HONEST_SPECS:
        seed_key = _det_int(incident_class, author, str(sorted(rule.items()))) % 5000
        seeds = [1000 + seed_key + i * 13 for i in range(6)]
        cap = _measured_capsule(incident_class, dims, rule, seeds, author)
        state, reason = submit(cap, store, AGENT_IDS, tick, strategist=STRATEGIST, emit=events.emit)
        assert state == LifecycleState.CANDIDATE, reason
        _mesh_shadow(store, ledger, cap, dims, base_seed=8000 + tick, sim_time=tick + 0.5)
        assert _active(store, ledger, cap.capsule_id)
        tick += 1.0

    poison_seeds = [11000 + i * 13 for i in range(6)]
    poison = _measured_capsule("ddos_syn_flood", POISON_DIMS, POISON_RULE, poison_seeds, ROGUE)
    state, reason = submit(poison, store, AGENT_IDS, tick, strategist=STRATEGIST, emit=events.emit)
    assert state == LifecycleState.CANDIDATE, reason
    _mesh_shadow(store, ledger, poison, POISON_DIMS, base_seed=9000, sim_time=tick + 0.5)
    assert _active(store, ledger, poison.capsule_id)
    tick += 1.0

    # The organic derived descendant: a live FabricAgent reuses the poison and refines a strictly
    # better rule from it (the same recipe tests/test_m4_gossip_reuse.py proves in isolation).
    agent = FabricAgent(
        agent_id="site-a", site_class="branch", strategist=HeuristicStrategist(), events=events,
        agent_ids=AGENT_IDS, node_ids=NODE_IDS, store=store, ledger=ledger,
    )

    # DECISION: traffic=6.0 sits inside the poison's [4.0, 9.0] band but outside every honest
    # capsule's band (nearest honest bands are [2.5,4.5] and [7.0,9.5]) — so this task is
    # uncontested and arbitration hands it to the poison, the precondition for a *derived-from-the-
    # poison* descendant rather than a refinement of an honest capsule.
    for i in range(6):
        task = Task(
            task_id=f"chaos-desc-{i}", incident_class="ddos_syn_flood", site_class="branch",
            params={"incident_class": "ddos_syn_flood", "site_class": "branch", "traffic_gbps": 6.0,
                    "device_count": 200},
            arrival_sim=tick + i, seed=90000 + i,
        )
        agent.handle_task(task, tick + i)
    derived = [c for cid in store.live_ids() if (c := store.get(cid)) is not None
               and c.provenance.derived_from == [poison.capsule_id]]
    assert len(derived) == 1, f"expected exactly one organic descendant, got {len(derived)}"
    descendant = derived[0]
    _mesh_shadow(store, ledger, descendant, descendant.context.dims, base_seed=9500, sim_time=tick + 8.0)
    assert _active(store, ledger, descendant.capsule_id)
    return store, ledger, poison, descendant


def build_partition_scenario(
    events: EventStream, sim_time: float
) -> tuple[dict[str, tuple[Store, ShadowLedger]], Capsule, Capsule]:
    """RUNBOOK Act 3, 8:45: chaos splits the mesh into two islands. Each island discovers,
    validates, and mesh-promotes its own genuinely-good capsule for the same congestion class
    through the real pipeline (real Pawl, real jury quorum, real shadow) while the partition blocks
    anti-entropy between them — the fault never reaches into a store (BLUEPRINT §12). Each cert's
    `partition_view` is the island's own reachable set (not the full mesh), which is what makes the
    later minority-cert demotion beat real rather than synthetic."""
    mesh = {aid: (Store(), ShadowLedger()) for aid in AGENT_IDS}
    x_seeds = [31000 + i * 13 for i in range(6)]
    y_seeds = [32000 + i * 13 for i in range(6)]
    cap_x = _measured_capsule("ddos_syn_flood", X_DIMS, X_RULE, x_seeds, "agent:site-a")
    cap_y = _measured_capsule("ddos_syn_flood", Y_DIMS, Y_RULE, y_seeds, "agent:site-c")

    store_x, _ = mesh["agent:site-a"]
    state, reason = submit(cap_x, store_x, AGENT_IDS, sim_time, strategist=STRATEGIST,
                            partition_view="|".join(sorted(ISLAND_X)), emit=events.emit)
    assert state == LifecycleState.CANDIDATE, reason
    store_y, _ = mesh["agent:site-c"]
    state, reason = submit(cap_y, store_y, AGENT_IDS, sim_time + 0.5, strategist=STRATEGIST,
                            partition_view="|".join(sorted(ISLAND_Y)), emit=events.emit)
    assert state == LifecycleState.CANDIDATE, reason

    # CANDIDATE reaches same-island peers only — a partitioned author cannot push across the split.
    for node in ISLAND_X - {"agent:site-a"}:
        mesh[node][0].add(cap_x)
        mesh[node][0].set_meta(cap_x.capsule_id, store_x.lifecycle_of(cap_x.capsule_id), sim_time)
    for node in ISLAND_Y - {"agent:site-c"}:
        mesh[node][0].add(cap_y)
        mesh[node][0].set_meta(cap_y.capsule_id, store_y.lifecycle_of(cap_y.capsule_id), sim_time + 0.5)

    _fill_island_shadow(mesh, ISLAND_X, cap_x, X_DIMS, base_seed=6100, sim_time=sim_time + 1.0)
    _fill_island_shadow(mesh, ISLAND_Y, cap_y, Y_DIMS, base_seed=6200, sim_time=sim_time + 1.5)

    reconcile_within_partition(mesh, PARTITION)
    assert all(_active(*mesh[n], cap_x.capsule_id) for n in ISLAND_X)
    assert all(_active(*mesh[n], cap_y.capsule_id) for n in ISLAND_Y)
    assert not any(cap_y.capsule_id in mesh[n][0].adds for n in ISLAND_X)
    assert not any(cap_x.capsule_id in mesh[n][0].adds for n in ISLAND_Y)
    return mesh, cap_x, cap_y


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="demo-chaos: RUNBOOK Act 3")
    parser.add_argument("--pace", choices=("fast", "live"), default="fast")
    parser.add_argument("--tui", action="store_true")
    parser.add_argument("--theme", choices=("dark", "high-contrast"), default="dark")
    args = parser.parse_args(argv)

    events = EventStream()
    dashboard = Dashboard(theme=args.theme) if args.tui else None
    if dashboard is not None:
        dashboard.__enter__()

    def narrate(sim_time: float, text: str) -> None:
        print(f"[{sim_time:>7.2f}] {text}")
        if dashboard is not None:
            records = events.records()
            dashboard.update(DashboardState(
                sim_time=sim_time, mesh=build_mesh_rows(records), fabric=build_fabric_rows(records),
                event_log=tuple(records[-12:]), theme=args.theme, narration=text,
            ))
        if args.pace == "live":
            time.sleep(_BEAT_SECONDS)

    try:
        print("# Act 3 — chaos (fresh seeded world, pre-warmed fabric, site-e flagged rogue)")
        store, ledger, poison, descendant = build_prewarmed_fabric(events)
        suspects_before = suspects(store, ledger, NODE_IDS)
        narrate(20.0, f"Fabric pre-warmed: {len(suspects_before)} capsules ACTIVE.")
        _beat(args.pace, "pre-warm complete")

        print("\n## Blatant poison")
        blatant = build_capsule(
            kind="mitigation_rule", registry_version=REGISTRY_VERSION,
            context=Context(incident_class="ddos_syn_flood",
                              dims={"traffic_gbps": [6.0, 10.0], "site_class": ALL_SITES}),
            payload=Payload(rule={"allowlist_subnet": "10.0.0.0/8"}),
            claim=Claim(metric="solve_cost", baseline_median=30.0, with_capsule_median=15.0,
                        delta_pct=-50.0, n_episodes=6),
            evidence=Evidence(scenario_seeds=list(range(4000, 4006)), conformance_required=[],
                               trace_digest="0" * 64),
            provenance=Provenance(author=ROGUE, author_epoch=1, derived_from=[]),
            lifecycle=Lifecycle(state=LifecycleState.DRAFT, created_at_sim=21.0),
        )
        pawl_result = pawl_check(blatant)
        assert not pawl_result.ok
        events.emit("PAWL_BLOCK", 21.0, capsule_id=blatant.capsule_id, author=ROGUE, reason=pawl_result.reason)
        narrate(21.0, f"PAWL_BLOCK: {pawl_result.reason}")
        narrate(21.0, "A ratchet without a pawl spins backward. The guardrail can autonomously get "
                       "stricter, and can only get looser with a signed human decision.")
        _beat(args.pace, "blatant poison blocked")

        print("\n## Subtle poison")
        narrate(22.0, "Watch this one get in. It genuinely improves its claimed metric on scenarios "
                       "it has never seen — admission is doing its job and it is not enough.")
        narrate(22.5, f"poison capsule {poison.capsule_id[:10]} and its descendant "
                       f"{descendant.capsule_id[:10]} are both ACTIVE.")
        _beat(args.pace, "subtle poison confirmed live")

        print("\n## Sentinel probe — memory's CI")
        sentinel = Sentinel("mesh", store, ledger, strategist=STRATEGIST, node_ids=NODE_IDS)
        report = sentinel.tick(24.0, emit=events.emit)
        assert report is not None and not report.clean
        for alarm in report.alarms[:3]:
            narrate(24.0, f"DRIFT_ALARM: {alarm.reason}")
        _beat(args.pace, "drift alarm raised")

        print("\n## Bisect")
        culprit, steps = bisect_culprit(store, ledger, STRATEGIST, sentinel.baselines,
                                         suspects(store, ledger, NODE_IDS), node_ids=NODE_IDS,
                                         sim_time=25.0, emit=events.emit)
        for step in steps:
            narrate(25.0, step.reason)
        assert culprit == poison.capsule_id, f"bisect should find the poison, found {culprit}"
        narrate(25.0, f"culprit found in {len(steps)} probes (log₂ of {len(suspects_before)} suspects).")
        _beat(args.pace, "bisect converged")

        print("\n## Excision")
        result = excise(store, culprit, 26.0,
                         reason=f"sentinel drift: {report.alarms[0].kpi} regression on the golden suite",
                         probe_alarms=tuple(a.reason for a in report.alarms), emit=events.emit)
        suspects_after = suspects(store, ledger, NODE_IDS)
        narrate(26.0, f"REVOKE: {culprit[:10]} tombstoned — {result.reason}")
        for qcid in result.quarantined:
            narrate(26.0, f"QUARANTINE: {qcid[:10]} — descendant of revoked {culprit[:10]}, re-jury required.")
        narrate(
            26.0,
            f"{len(suspects_before)} capsules to {len(suspects_after)}. Not to zero. "
            "Surgical excision, not amnesia.",
        )
        rep_after = reputation(store, ROGUE, ledger=ledger, node_ids=NODE_IDS)
        narrate(26.5, f"reputation({ROGUE}) = {rep_after:.2f} "
                       f"(isolation floor {REP_ISOLATION_FLOOR:.2f}) — jurors who signed the "
                       "revoked capsule's cert are slashed too.")
        _beat(args.pace, "excision complete")

        print("\n## Partition (BLUEPRINT §6.2, §7.5, milestone M6)")
        narrate(
            28.0,
            "Chaos splits the mesh: {site-a, site-b} | {site-c, site-d, site-e}. Both islands keep "
            "working; each learns a different fix for the same congestion class — valid for their "
            "local parameter regimes.",
        )
        mesh, cap_x, cap_y = build_partition_scenario(events, 28.5)
        events.emit("PARTITION", 28.5, islands=[sorted(ISLAND_X), sorted(ISLAND_Y)])
        narrate(
            29.5,
            f"Island X: {cap_x.capsule_id[:10]} ACTIVE locally. Island Y: {cap_y.capsule_id[:10]} "
            "ACTIVE locally. Neither is visible on the other island — both sides are right, for "
            "their contexts.",
        )
        _beat(args.pace, "partition confirmed")

        print("\n## Heal")
        reconcile_within_partition(mesh, None)  # heal: partition=None is unconditional full reconcile
        events.emit("HEAL", 30.0, islands_merged=[sorted(ISLAND_X), sorted(ISLAND_Y)])
        overlap_task = _overlap_task(5.5, seed=7001)
        arbitration_lines = []
        winners = set()
        for node in ("agent:site-a", "agent:site-e"):
            matches = active_matches(*mesh[node], overlap_task, NODE_IDS)
            winner = arbitrate(matches)
            winners.add(winner.capsule.capsule_id)
            arbitration_lines.append(f"{node} decides: {winner.capsule.capsule_id[:10]}")
        assert len(winners) == 1, f"every node must pick the same winner, got {winners}"
        narrate(
            30.0,
            "Heal: stores union (CRDT — nothing to merge by construction); overlap detected; every "
            "node runs the same pure arbitrate() —  " + "  |  ".join(arbitration_lines) + "  — identical.",
        )
        _beat(args.pace, "heal converged")

        print("\n## Refine")
        tracker = OverlapTracker()
        triggered = False
        winner_app = loser_app = None
        for seed in (7101, 7102, 7103):
            task = _overlap_task(5.5, seed)
            matches = active_matches(*mesh["agent:site-a"], task, NODE_IDS)
            winner_app = arbitrate(matches)
            loser_app = next(m for m in matches if m.capsule.capsule_id != winner_app.capsule.capsule_id)
            tracker, triggered = record_overlap(tracker, winner_app, loser_app)
        assert triggered
        refine_result = refine_split(winner_app, loser_app)
        events.emit(
            "REFINE", 31.0, dimension=refine_result.dimension,
            winner_capsule=winner_app.capsule.capsule_id, loser_capsule=loser_app.capsule.capsule_id,
            reason=refine_result.reason,
        )
        narrate(31.0, f"REFINE: same overlap arbitrated 3 times — {refine_result.reason}.")

        refined_store, refined_ledger = mesh["agent:site-a"]
        refined = []
        for i, (app, dims) in enumerate(
            ((winner_app, refine_result.winner_dims), (loser_app, refine_result.loser_dims))
        ):
            cap = _measured_capsule(
                "ddos_syn_flood", dims, app.capsule.payload.rule,
                [33000 + i * 1000 + j * 13 for j in range(6)], app.capsule.provenance.author,
            )
            state, reason = submit(cap, refined_store, AGENT_IDS, 31.5, strategist=STRATEGIST, emit=events.emit)
            assert state == LifecycleState.CANDIDATE, reason
            _fill_island_shadow({n: mesh[n] for n in ISLAND_X | ISLAND_Y}, ISLAND_X | ISLAND_Y, cap, dims,
                                 base_seed=6300 + i * 500, sim_time=31.75)
            assert _active(refined_store, refined_ledger, cap.capsule_id)
            refined.append(cap)
        narrate(
            32.0,
            f"Both capsules survive, scoped along {refine_result.dimension!r}: "
            f"{refined[0].context.dims[refine_result.dimension]} vs "
            f"{refined[1].context.dims[refine_result.dimension]}. Storage is eventual, meaning is "
            "scoped, decisions are deterministic — a conflict is an underspecified context, not a "
            "truth to delete.",
        )
        _beat(args.pace, "refine complete")

        print("\n## Minority-island cert demotion")
        mesh_size = len(AGENT_IDS)
        cert_x = mesh["agent:site-a"][0].lifecycle_of(cap_x.capsule_id)["quorum_cert"]
        cert_y = mesh["agent:site-c"][0].lifecycle_of(cap_y.capsule_id)["quorum_cert"]
        demotes_x = provisional_cert_demotion(cert_x, mesh_size)
        demotes_y = provisional_cert_demotion(cert_y, mesh_size)
        assert demotes_x and not demotes_y
        demote_provisional(mesh["agent:site-a"][0], cap_x, 32.5, emit=events.emit)
        narrate(
            32.5,
            f"{cap_x.capsule_id[:10]}'s cert saw only {sorted(ISLAND_X)}'s {len(ISLAND_X)} nodes at cert "
            f"time — below the mesh majority — demoted to QUARANTINED pending re-jury. "
            f"{cap_y.capsule_id[:10]}'s cert saw {len(ISLAND_Y)} nodes, a majority — stays ACTIVE, "
            "never silently authoritative on minority-island knowledge either way.",
        )
        _beat(args.pace, "Act 3 complete")
    finally:
        if dashboard is not None:
            dashboard.__exit__(None, None, None)

    print("\n# Card")
    print(f"pre-warmed capsules: {len(suspects_before)}  after excision: {len(suspects_after)}  "
          f"(removed exactly {len(suspects_before) - len(suspects_after)})")
    print(f"bisect probes: {len(steps)}  reputation after excision: {rep_after:.2f}")
    print(f"store retains {len(store.adds)} adds incl. the tombstoned poison — never-reset assertion.")


if __name__ == "__main__":
    main()
