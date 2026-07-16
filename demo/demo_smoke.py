"""demo-smoke — the ≤20s end-to-end CI gate (BLUEPRINT §9, milestone acceptance).

M0 form: a seeded run of 20 tasks that prints each episode's metrics and cost. Because TaskGen,
the scenario simulators, and the cost model are all deterministic, two runs on the same seed print
byte-identical output — the determinism guarantee the live demo depends on.
"""

from __future__ import annotations

from fabric.config import DEFAULT_ACTION
from world.cost import solve_cost
from world.scenarios import simulate
from world.taskgen import generate

SMOKE_SEED = 424242
SMOKE_TASKS = 20


def run_smoke(seed: int = SMOKE_SEED, n: int = SMOKE_TASKS) -> list[dict]:
    """Simulate `n` seeded tasks with the default (memoryless) action; return metric records."""
    records: list[dict] = []
    for task in generate(seed, n):
        metrics = simulate(task.params, DEFAULT_ACTION, task.seed)
        record = {
            "task_id": task.task_id,
            "incident_class": task.incident_class,
            "site_class": task.site_class,
            **metrics.as_dict(),
            "solve_cost": solve_cost(1, metrics),
        }
        records.append(record)
    return records


def _format(record: dict) -> str:
    return (
        f"{record['task_id']}  {record['incident_class']:<20} {record['site_class']:<7} "
        f"ttm={record['time_to_mitigate_s']:>7.4f}  fp={record['fp_quarantines']:>2}  "
        f"sla={record['sla_burn']:>6.4f}  inv={record['invariant_hits']}  "
        f"cost={record['solve_cost']:>7.4f}"
    )


def main() -> None:
    records = run_smoke()
    print(f"# demo-smoke (M0): seed={SMOKE_SEED}, tasks={SMOKE_TASKS}")
    for record in records:
        print(_format(record))
    total = round(sum(r["solve_cost"] for r in records), 4)
    print(f"# total solve_cost = {total}")


if __name__ == "__main__":
    main()
