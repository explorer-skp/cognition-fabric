"""demo-smoke — the ≤20s end-to-end CI gate (BLUEPRINT §9, milestone acceptance).

M4 form: the M0 world-determinism anchor plus a twin-lane A/B *repeat-incident storm* (Lane A fabric
ON, Lane B fabric OFF) over one seeded stream, with the compact ratchet metrics block (BLUEPRINT §11).
Because TaskGen, the scenario simulators, the cost model, sortition, and gossip (over sorted ids) are
all seeded, two runs produce byte-identical output — the determinism guarantee the live demo depends
on. The storm's class mix is *shaped* (a dense repeat of incidents) so the ratchet is visible in a
few seconds; absolute-band tuning is deferred to M7.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from agents.agent import run_baseline_storm, run_twin_lane
from fabric.config import DEFAULT_ACTION, STORM_SIZE
from ui.events import EventStream
from ui.metrics import summarize
from world.cost import solve_cost
from world.scenarios import simulate
from world.taskgen import Task, generate

SMOKE_SEED = 424242
SMOKE_TASKS = 20
STORM_SEED = 424242


# A shaped repeat-incident storm (BLUEPRINT §10 M4: economics deferred to M7; the mechanism is the
# claim). Phase 1 funnels the ddos incidents to two sites so they accumulate discovery evidence,
# author, and promote mesh-wide; phase 2 rains ddos on the whole mesh, so the other sites solve every
# repeat at *reuse* cost from validated memory they never authored. `traffic_gbps` cycles with period
# 3 (coprime with the 5-way round-robin) so each capsule's context is matched by tasks landing on
# multiple sites — the ≥ SHADOW_MIN_NODES that mesh promotion requires.
_SITES = ("branch", "campus", "dc")


def _ddos(i: int, site_class: str) -> Task:
    return Task(
        task_id=f"t{i:04d}",
        incident_class="ddos_syn_flood",
        site_class=site_class,
        params={
            "incident_class": "ddos_syn_flood",
            "site_class": site_class,
            "traffic_gbps": round(4.0 + (i % 3), 3),
            "device_count": 200,
        },
        arrival_sim=round(1.0 * i, 4),
        seed=1000 + i * 7,
    )


def _cert(i: int, site_class: str) -> Task:
    return Task(
        task_id=f"t{i:04d}",
        incident_class="cert_expiry_storm",
        site_class=site_class,
        params={
            "incident_class": "cert_expiry_storm",
            "site_class": site_class,
            "traffic_gbps": 2.0,
            "device_count": 100,
        },
        arrival_sim=round(1.0 * i, 4),
        seed=1000 + i * 7,
    )


def repeat_incident_storm(n: int = STORM_SIZE, funnel: int = 25) -> list[Task]:
    """Deterministic shaped storm: ddos funnelled to sites a,b for the first `funnel` tasks (the rest
    handled by c,d,e as cert), then ddos across the whole mesh — a dense repeat of incidents."""
    tasks: list[Task] = []
    for i in range(funnel):
        site = _SITES[i % 3]
        tasks.append(_ddos(i, site) if i % 5 in (0, 1) else _cert(i, site))
    for i in range(funnel, n):
        tasks.append(_ddos(i, _SITES[i % 3]))
    return tasks


def run_smoke(seed: int = SMOKE_SEED, n: int = SMOKE_TASKS) -> list[dict]:
    """M0 world-determinism anchor: simulate `n` seeded tasks with the default (memoryless) action."""
    records: list[dict] = []
    for task in generate(seed, n):
        metrics = simulate(task.params, DEFAULT_ACTION, task.seed)
        records.append(
            {
                "task_id": task.task_id,
                "incident_class": task.incident_class,
                "site_class": task.site_class,
                **metrics.as_dict(),
                "solve_cost": solve_cost(1, metrics),
            }
        )
    return records


def _format(record: dict) -> str:
    return (
        f"{record['task_id']}  {record['incident_class']:<20} {record['site_class']:<7} "
        f"ttm={record['time_to_mitigate_s']:>7.4f}  fp={record['fp_quarantines']:>2}  "
        f"sla={record['sla_burn']:>6.4f}  inv={record['invariant_hits']}  "
        f"cost={record['solve_cost']:>7.4f}"
    )


def summarize_storm(events: EventStream) -> dict[str, dict]:
    """Per-class summary of a baseline storm: task count, median solve cost, total cost."""
    by_class: dict[str, list[float]] = defaultdict(list)
    for record in events.of_type("SOLVE"):
        by_class[record["incident_class"]].append(record["solve_cost"])
    return {
        cls: {
            "n": len(costs),
            "median_cost": round(median(costs), 3),
            "total_cost": round(sum(costs), 3),
        }
        for cls, costs in sorted(by_class.items())
    }


def main() -> None:
    tasks = repeat_incident_storm(STORM_SIZE)
    lane_a = EventStream("events.jsonl")
    from agents.agent import run_fabric_storm

    run_fabric_storm(STORM_SEED, len(tasks), events=lane_a, tasks=tasks)
    lane_b = run_baseline_storm(STORM_SEED, len(tasks), events=EventStream(), tasks=tasks)
    lane_a.close()
    summary = summarize(lane_a.records(), lane_b.records())

    print(
        f"# demo-smoke (M4): twin-lane repeat-incident storm, seed={STORM_SEED}, tasks={len(tasks)} "
        f"(Lane A fabric ON · Lane B fabric OFF)"
    )
    rvd = summary["reuse_vs_discovery"]
    for cls in sorted(k for k in rvd if k != "overall"):
        b = rvd[cls]
        disc = f"{b['discovery_median']:.2f}" if b["discovery_median"] is not None else "  -  "
        reuse = f"{b['reuse_median']:.2f}" if b["reuse_median"] is not None else "  -  "
        ratio = f"{b['ratio']:.2f}" if "ratio" in b else " - "
        stairs = summary["staircase"].get(cls, [])
        step = f"{stairs[0]:.1f}→{stairs[-1]:.1f}" if stairs else "-"
        print(
            f"{cls:<20} discovery_median={disc:>7}  reuse_median={reuse:>7}  "
            f"ratio={ratio:>5}  staircase={step}"
        )
    lead = summary["median_lead_time"]
    print(
        f"# ratchet: authored={summary['authored']}  promoted(mesh)={summary['promotions']}  "
        f"non-author reuse sites={len(summary['non_author_reuse_sites'])}  "
        f"median insight lead={lead if lead is not None else '-'} sim-s"
    )
    print(
        f"# economics: Lane A cumulative={summary['lane_a_cumulative']:.1f}  "
        f"Lane B cumulative={summary['lane_b_cumulative']:.1f}  "
        f"saved={summary['pct_saved']:.1f}%  (memory ratchets cost down — absolute band tuned in M7)"
    )


if __name__ == "__main__":
    main()
