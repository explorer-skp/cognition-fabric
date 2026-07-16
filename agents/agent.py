"""Site agents and the baseline (fabric-OFF) task loop (BLUEPRINT §8, milestone M1).

An agent receives a TASK, solves it, measures the cost, and emits a SOLVE event. Even with the
fabric off, the agent enforces its own constitution locally: adoption-as-prior means a capsule (from
M4) can only ever be a starting point — it can never make an agent apply an action that violates an
invariant (BLUEPRINT §4). At M1 there is no fabric, so `prior` is always None and every task is
solved from a cold start — which is exactly why per-class costs stay high and flat over time.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agents.strategist import HeuristicStrategist, SolveResult, Strategist
from fabric.config import AGENTS, STORM_SIZE
from world.bus import Bus, Message
from world.cost import solve_cost
from world.scenarios import check_invariants
from world.simclock import SimClock
from world.taskgen import Task, generate
from ui.events import EventStream


@dataclass
class Agent:
    """One site agent. `fabric` is None at M1 (baseline); wired in from M4."""

    agent_id: str
    site_class: str
    strategist: Strategist
    events: EventStream
    reputation: float = 1.0
    fabric: object | None = None  # placeholder for the capsule store, added at M4

    def solve_task(self, task: Task) -> tuple[float, SolveResult]:
        # M1: fabric OFF → no prior. The adoption-as-prior hook lives here; it stays inert until M4.
        prior: dict | None = None
        result = self.strategist.solve(task, prior=prior)

        # Local constitution enforcement (fail-secure): never apply an action that violates an
        # invariant. The heuristic already avoids these (the cost model punishes them 25x), so this
        # is a guardrail, not an expected branch — assert it holds at M1.
        violations = check_invariants(result.action, task.incident_class, task.site_class)
        if violations:
            raise AssertionError(
                f"{self.agent_id} would apply an action violating {violations} on {task.task_id}"
            )

        cost = solve_cost(result.attempts, result.metrics)
        self.events.emit(
            "SOLVE",
            sim_time=task.arrival_sim,
            agent=self.agent_id,
            task_id=task.task_id,
            incident_class=task.incident_class,
            site_class=task.site_class,
            attempts=result.attempts,
            solve_cost=cost,
            invariant_hits=result.metrics.invariant_hits,
            reused=False,
        )
        return cost, result

    def on_task(self, message: Message) -> None:
        """Bus handler: process a TASK only if it is addressed to this agent."""
        if message.payload.get("assignee") != self.agent_id:
            return
        self.solve_task(message.payload["task"])


def run_baseline_storm(
    seed: int, n: int = STORM_SIZE, events: EventStream | None = None
) -> EventStream:
    """Drive `n` seeded tasks through the 5-agent mesh over the deterministic bus (fabric OFF).

    Tasks are assigned round-robin across agents; delivery is ordered by (arrival_sim, seq), so the
    whole storm is replayable byte-for-byte. Returns the EventStream it wrote to.
    """
    events = events or EventStream()
    clock = SimClock()
    bus = Bus(clock)
    agents = [Agent(aid, sc, HeuristicStrategist(), events) for aid, sc in AGENTS]

    # World's view first: emit the TASK event on delivery, then the assigned agent emits SOLVE — so
    # the single stream is monotonic in sim_time (TASK immediately followed by its SOLVE).
    def emit_task(message: Message) -> None:
        events.emit(
            "TASK",
            sim_time=message.sim_time,
            task_id=message.payload["task"].task_id,
            incident_class=message.payload["task"].incident_class,
            site_class=message.payload["task"].site_class,
            assignee=message.payload["assignee"],
        )

    bus.subscribe("TASK", emit_task)
    for agent in agents:
        bus.subscribe("TASK", agent.on_task)

    for i, task in enumerate(generate(seed, n)):
        assignee = AGENTS[i % len(AGENTS)][0]
        bus.publish(
            "TASK",
            Message("TASK", "world", task.arrival_sim, {"task": task, "assignee": assignee}),
            at=task.arrival_sim,
        )

    asyncio.run(bus.run_until_empty())
    return events
