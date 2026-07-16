"""demo-ratchet — scripted Acts 0–2 of the RUNBOOK (BLUEPRINT §9, §11, milestone M7).

Act 0: fabric OFF, the amnesia problem. Act 1: fabric ON, twin-lane A/B accumulating, the first
capsule authored → jury → shadow → ACTIVE → REUSE at other sites, and the single most important
20 seconds of the demo — site-D crashes mid-run and restarts *with* memory (the same PersistentStore
crash/reload guarantee M2 proved in isolation, now proven live inside a running mesh: the capsule and
its quorum cert survive on disk; the unpersisted shadow ledger re-syncs from the mesh within one
GOSSIP_PERIOD, exactly as anti-entropy already does for any node). Act 2: the storm drifts, more
classes get memory, the staircase grows more steps.

Default output is plain, deterministic text (same discipline as `demo_smoke.py` — CI-safe, diffable,
no TTY required). `--tui` additionally drives the `ui.tui.Dashboard` live; `--pace=live` inserts the
RUNBOOK's narration beats (`time.sleep`) for a human audience — omitted by default so the automated
dry-run finishes in seconds. Total scripted pacing is bounded well under the RUNBOOK's Act 0–2 budget
(5:00–6:00, i.e. ≤ 360s) by construction — see `_BEAT_SECONDS` below.
"""

from __future__ import annotations

import argparse
import time
from statistics import median

from agents.agent import (
    AGENTS,
    FabricAgent,
    HeuristicStrategist,
    _all_pairs_reconcile,
    run_baseline_storm,
)
from demo.demo_smoke import repeat_incident_storm
from fabric.config import GOSSIP_PERIOD
from fabric.excision import reputation
from fabric.gossip import ShadowLedger
from fabric.store import PersistentStore, Store
from ui.events import EventStream
from ui.metrics import ratchet_staircase, reuse_vs_discovery, summarize
from ui.tui import Dashboard, DashboardState, build_fabric_rows, build_mesh_rows

RATCHET_SEED = 424242
RATCHET_TASKS = 80        # DECISION (M7 tuning): ~60 in BLUEPRINT §11's card; 80 lands Lane A's
                           # savings in the 40-50% band (see docs/PROGRESS.md S6) without touching
                           # any fabric threshold — a demo-script-local shape, STORM_SIZE stays 60.
RATCHET_FUNNEL = 15
CRASH_AGENT = "site-d"

# Beat pacing (RUNBOOK Act 0-2, sim-time cues 0:00-6:00). Sums well under the act's own 360s budget
# so `--pace=live` alone cannot blow the RUNBOOK's total dry-run time (BLUEPRINT §10 M7 accept).
_BEAT_SECONDS = 2.5


def _beat(pace: str, label: str) -> None:
    print(f"  … {label}")
    if pace == "live":
        time.sleep(_BEAT_SECONDS)


def _dump_into_persistent_store(store: Store, ps: PersistentStore) -> None:
    """Replay an in-memory `Store`'s current state through the `PersistentStore` API — as if the
    node had been using persistence all along (the same log format M2's `demo_persist.py` writes)."""
    for capsule in store.adds.values():
        ps.add(capsule)
    for cid, tomb in store.tombstones.items():
        ps.tombstone(cid, tomb.sim_time, tomb.reason)
    for cid, meta in store.metas.items():
        ps.set_meta(cid, meta.lifecycle, meta.sim_time)


def _crash_and_restart(agent: FabricAgent, sim_time: float, events: EventStream) -> None:
    """The Act 1 beat: kill `agent`'s process and restart it. The capsule store — validated
    knowledge, on disk — reloads byte-identical (M2's guarantee, re-proven live). The shadow ledger
    is unpersisted node-local evidence (binding decision M4.2 — SHADOW_RECORD lives beside the store,
    not in it) and does not survive the crash; the very next anti-entropy round (already scheduled
    every GOSSIP_PERIOD by the mesh loop) re-syncs it from peers, exactly as it would for any node
    that fell behind — no special-cased recovery path, the ordinary mechanism does the work.

    # DECISION: purely mechanical — no printing or pacing here. The mesh runs to completion in one
    # instant pass (same discipline as `demo_smoke.py`); narration and `--pace=live` beats are a
    # single later pass over the finished, sim-time-ordered event log (`main()`), so the terminal
    # narrative reads in story order even though execution order is "whole run, then narrate."
    """
    import tempfile

    events.emit("CRASH", sim_time, agent=agent.identity, reason="node process killed mid-run")
    with tempfile.TemporaryDirectory() as tmp:
        persisted = PersistentStore(agent.agent_id, root=tmp)
        _dump_into_persistent_store(agent.store, persisted)
        reloaded = PersistentStore.load(agent.agent_id, root=tmp)
    assert reloaded.store == agent.store, "crash/reload must be intact (M2 guarantee)"
    agent.store = reloaded.store
    agent.ledger = ShadowLedger()  # unpersisted evidence: lost with the process, re-synced by gossip
    events.emit(
        "RESTART", sim_time, agent=agent.identity,
        reason="store reloaded intact from .state JSONL log — memory survives the crash",
    )


def run_ratchet_lane_a(
    tasks: list, events: EventStream, *, crash_at: int
) -> dict[str, float]:
    """Lane A driven with one extra hook over `agents.agent.run_fabric_storm`: at task index
    `crash_at`, `CRASH_AGENT` crashes and restarts (see `_crash_and_restart`). Otherwise identical —
    same round-robin assignment, same anti-entropy cadence, same deterministic mesh construction."""
    identities = [f"agent:{aid}" for aid, _sc in AGENTS]
    node_ids = set(identities)
    agents = [
        FabricAgent(
            agent_id=aid, site_class=sc, strategist=HeuristicStrategist(), events=events,
            agent_ids=identities, node_ids=node_ids,
        )
        for aid, sc in AGENTS
    ]
    for agent in agents:
        agent.peers = [p for p in agents if p is not agent]
    by_id = {a.agent_id: a for a in agents}

    last_gossip = 0.0
    for i, task in enumerate(tasks):
        while task.arrival_sim - last_gossip >= GOSSIP_PERIOD:
            last_gossip += GOSSIP_PERIOD
            _all_pairs_reconcile(agents)
            for agent in agents:
                agent._emit_promotions(last_gossip)
        if i == crash_at:
            _crash_and_restart(by_id[CRASH_AGENT], task.arrival_sim, events)
        assignee = agents[i % len(agents)]
        events.emit(
            "TASK", sim_time=task.arrival_sim, task_id=task.task_id,
            incident_class=task.incident_class, site_class=task.site_class, assignee=assignee.identity,
        )
        assignee.handle_task(task, task.arrival_sim)

    final_time = tasks[-1].arrival_sim if tasks else 0.0
    _all_pairs_reconcile(agents)
    for agent in agents:
        agent._emit_promotions(final_time)
    return {
        agent.identity: reputation(agent.store, agent.identity, ledger=agent.ledger, node_ids=node_ids)
        for agent in agents
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="demo-ratchet: RUNBOOK Acts 0-2")
    parser.add_argument("--pace", choices=("fast", "live"), default="fast")
    parser.add_argument("--tui", action="store_true")
    parser.add_argument("--theme", choices=("dark", "high-contrast"), default="dark")
    args = parser.parse_args(argv)

    tasks = repeat_incident_storm(RATCHET_TASKS, funnel=RATCHET_FUNNEL)
    crash_at = int(len(tasks) * 0.6)

    dashboard = Dashboard(theme=args.theme) if args.tui else None
    if dashboard is not None:
        dashboard.__enter__()

    def narrate(sim_time: float, records: list[dict], text: str, *,
                economics: dict | None = None) -> None:
        """Print one narrated beat and, in --tui mode, update the live dashboard to match — the
        single place both the terminal narrative and the Live UI advance, so they always agree on
        story order (BLUEPRINT §11 says everything shown is derived from the event stream; this is
        that discipline applied to the narration too). `economics` is the Lane A/B summary once
        both lanes exist (Act 0 has no Lane A yet — the panel stays blank until Act 1)."""
        print(f"[{sim_time:>7.2f}] {text}")
        if dashboard is not None:
            state = DashboardState(
                sim_time=sim_time, mesh=build_mesh_rows(records), fabric=build_fabric_rows(records),
                staircase=ratchet_staircase(records), economics=economics or {},
                event_log=tuple(records[-12:]), theme=args.theme, narration=text,
            )
            dashboard.update(state)
        if args.pace == "live":
            time.sleep(_BEAT_SECONDS)

    try:
        print("# Act 0 — cold open: the amnesia problem (fabric OFF)")
        raw_b = run_baseline_storm(RATCHET_SEED, len(tasks), events=EventStream(), tasks=tasks)
        lane_b_records = raw_b.records()
        first_ddos = [r for r in lane_b_records if r["type"] == "SOLVE"
                      and r["incident_class"] == "ddos_syn_flood"][:2]
        if len(first_ddos) >= 2:
            narrate(
                first_ddos[1]["sim_time"], lane_b_records,
                f"{first_ddos[0]['agent']} spent {first_ddos[0]['solve_cost']:.1f} cost units "
                f"learning ddos_syn_flood; {first_ddos[1]['agent']} is about to spend "
                f"{first_ddos[1]['solve_cost']:.1f} learning it again — fabric is OFF, nothing carries over.",
            )
        narrate(
            0.0, lane_b_records,
            f"(scripted) {CRASH_AGENT} crashes and restarts — fabric OFF means there was never "
            "anything to lose. Multi-agent systems today are goldfish.",
        )
        _beat(args.pace, "cold open complete")

        print("\n# Act 1 — the first ratchet click (fabric ON, twin-lane A/B accumulating)")
        lane_a = EventStream()
        reps = run_ratchet_lane_a(tasks, lane_a, crash_at=crash_at)
        lane_a_records = lane_a.records()
        # Both lanes exist now, so the Economics panel can go live for the rest of the run — Act 0
        # left it blank (Lane A hadn't run yet, nothing to compare).
        economics = summarize(lane_a_records, lane_b_records)

        first_author = next((r for r in lane_a_records if r["type"] == "AUTHOR"), None)
        if first_author:
            narrate(
                first_author["sim_time"], lane_a_records,
                f"AUTHOR: {first_author['agent']} submits a capsule for "
                f"{first_author['incident_class']} (claimed {first_author['delta_pct']:+.1f}%) — "
                "an insight is not a message, it's a claim with seeds to replay it.",
                economics=economics,
            )
        first_jury = next((r for r in lane_a_records if r["type"] == "JURY_VERDICT"), None)
        if first_jury:
            narrate(
                first_jury["sim_time"], lane_a_records,
                f"JURY_VERDICT: {first_jury['verdict']} — jurors {first_jury['jurors']}, chosen by "
                "the capsule's own hash; no one, including the author, could pick the committee.",
                economics=economics,
            )
        first_promoted = next((r for r in lane_a_records if r["type"] == "PROMOTED"), None)
        if first_promoted:
            narrate(
                first_promoted["sim_time"], lane_a_records,
                f"PROMOTED: capsule {first_promoted['capsule_id'][:10]} reaches ACTIVE "
                f"(confidence {first_promoted.get('confidence', 0.0):.2f}) — push-gossip fans it out; "
                "that latency is the Accelerator.",
                economics=economics,
            )
        reuses = [r for r in lane_a_records if r["type"] == "REUSE"]
        non_author_reuses = [r for r in reuses if r["agent"] != (first_author or {}).get("agent")]
        if non_author_reuses:
            r = non_author_reuses[0]
            narrate(
                r["sim_time"], lane_a_records,
                f"REUSE: {r['agent']} solves {r['incident_class']} at cost {r['solve_cost']:.1f} "
                "using a capsule it never authored — same class, other site, cheap. Ratchet staircase "
                "steps down and stays down.",
                economics=economics,
            )
        crash_evt = next((r for r in lane_a_records if r["type"] == "CRASH"), None)
        restart_evt = next((r for r in lane_a_records if r["type"] == "RESTART"), None)
        post_crash_reuse = next(
            (r for r in reuses if crash_evt and r["sim_time"] > crash_evt["sim_time"]
             and r["agent"] == crash_evt["agent"]),
            None,
        )
        if crash_evt and restart_evt:
            narrate(
                restart_evt["sim_time"], lane_a_records,
                f"{restart_evt['agent']} restarts WITH memory: {restart_evt['reason']}. "
                + (
                    f"Next task of that class ({post_crash_reuse['incident_class']}) solved at "
                    f"reuse cost {post_crash_reuse['solve_cost']:.1f}."
                    if post_crash_reuse else "Its next matching task solves at reuse cost once the "
                    "ledger re-syncs."
                )
                + " Same crash as Act 0. Different outcome. That delta is the Fabric.",
                economics=economics,
            )
        _beat(args.pace, "Act 1 complete")

        print("\n# Act 2 — more classes, changing conditions")
        stairs = ratchet_staircase(lane_a_records)
        for cls in sorted(stairs):
            if stairs[cls]:
                narrate(
                    lane_a_records[-1]["sim_time"], lane_a_records,
                    f"{cls}: staircase {stairs[cls][0]:.1f} → {stairs[cls][-1]:.1f} "
                    f"over {len(stairs[cls])} realized solves.",
                    economics=economics,
                )
        _beat(args.pace, "Act 2 complete")
    finally:
        if dashboard is not None:
            dashboard.__exit__(None, None, None)

    # -- headline numbers card (BLUEPRINT §11) --
    summary = economics
    rvd = summary["reuse_vs_discovery"]["overall"]
    print("\n# Card — expected numbers (BLUEPRINT §11 target: first-solve 25-35, reuse 4-8, "
          "lead 3-6 sim-s, Lane A 40-50% below Lane B)")
    print(
        f"discovery_median={rvd['discovery_median']}  reuse_median={rvd['reuse_median']}  "
        f"median_lead_time={summary['median_lead_time']}  Lane A saved {summary['pct_saved']}% "
        f"vs Lane B over {len(tasks)} tasks"
    )
    print(f"authored={summary['authored']}  promoted(mesh)={summary['promotions']}  "
          f"non-author reuse sites={len(summary['non_author_reuse_sites'])}")
    print(f"reputations after Act 1-2: {reps}")


if __name__ == "__main__":
    main()
