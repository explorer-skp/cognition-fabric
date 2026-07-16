"""demo-smoke — the ≤20s end-to-end CI gate (BLUEPRINT §9, milestone acceptance).

M1 form: a seeded 5-agent baseline storm (fabric OFF) plus the M0 world-determinism anchor. Because
TaskGen, the scenario simulators, the cost model, and the deterministic bus are all seeded, two runs
on the same seed produce byte-identical output and byte-identical `events.jsonl` — the determinism
guarantee the live demo depends on.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from agents.agent import run_baseline_storm
from fabric.config import DEFAULT_ACTION, STORM_SIZE
from ui.events import EventStream
from world.cost import solve_cost
from world.scenarios import simulate
from world.taskgen import generate

SMOKE_SEED = 424242
SMOKE_TASKS = 20
STORM_SEED = 424242


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
    events = run_baseline_storm(STORM_SEED, n=STORM_SIZE, events=EventStream("events.jsonl"))
    summary = summarize_storm(events)
    events.close()

    print(f"# demo-smoke (M1): 5-agent baseline storm (fabric OFF), seed={STORM_SEED}, tasks={STORM_SIZE}")
    for cls, stats in summary.items():
        print(
            f"{cls:<20} n={stats['n']:>2}  median_cost={stats['median_cost']:>7.3f}  "
            f"total_cost={stats['total_cost']:>8.3f}"
        )
    grand_total = round(sum(s["total_cost"] for s in summary.values()), 3)
    print(f"# grand total solve_cost = {grand_total}  (high & flat — no memory yet; ratchet arrives at M4)")


if __name__ == "__main__":
    main()
