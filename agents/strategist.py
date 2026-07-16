"""The Strategist interface + implementations (BLUEPRINT §8).

*Models propose, the protocol disposes*: the fabric is model-agnostic because nothing in validation
ever evaluates language, only replayed behavior. The default `HeuristicStrategist` is deterministic
and demo-safe; `LLMStrategist` exists behind the same interface but is a stub — the core path never
calls an LLM (CLAUDE.md).

Solving without memory (M1) is bounded local search: hill-climb over the quantized action space,
≤ MAX_ATTEMPTS attempts, each attempt a real (costed) episode. That is the *discovery* cost the
ratchet later removes by starting from a validated prior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fabric.config import ACTION_SPACE, DEFAULT_ACTION, MAX_ATTEMPTS
from world.cost import solve_cost
from world.scenarios import EpisodeMetrics, relevant_dims, simulate
from world.taskgen import Task


@dataclass(frozen=True)
class SolveResult:
    """Outcome of solving a task: the chosen action, the search effort, and the applied episode."""

    action: dict
    attempts: int
    metrics: EpisodeMetrics


def _nearest_index(space: list, value) -> int:
    """Index of `value` in `space`; for numeric spaces, the nearest quantized index if absent."""
    if value in space:
        return space.index(value)
    if all(isinstance(x, (int, float)) for x in space) and isinstance(value, (int, float)):
        return min(range(len(space)), key=lambda i: abs(space[i] - value))
    return 0


def _impact(metrics: EpisodeMetrics) -> float:
    """Episode-impact cost only (search effort excluded) — the signal the search minimizes."""
    return solve_cost(0, metrics)


class Strategist(Protocol):
    def solve(self, task: Task, prior: dict | None = None) -> SolveResult: ...


class HeuristicStrategist:
    """Deterministic coordinate-ascent hill-climb. Starts from a prior when given one (reuse), else
    from the safe default action (cold discovery)."""

    def solve(self, task: Task, prior: dict | None = None) -> SolveResult:
        dims = relevant_dims(task.incident_class)
        attempts = 0

        def evaluate(action: dict) -> EpisodeMetrics:
            nonlocal attempts
            # Distinct, reproducible seed per attempt so each candidate is evaluated deterministically.
            seed = task.seed * 100003 + attempts
            attempts += 1
            return simulate(task.params, action, seed)

        best_action = dict(prior) if prior else dict(DEFAULT_ACTION)
        best_impact = _impact(evaluate(best_action))

        improved = True
        while improved and attempts < MAX_ATTEMPTS:
            improved = False
            for dim in dims:
                space = ACTION_SPACE[dim]
                idx = _nearest_index(space, best_action[dim])
                for nidx in (idx - 1, idx + 1):
                    if 0 <= nidx < len(space) and attempts < MAX_ATTEMPTS:
                        candidate = dict(best_action)
                        candidate[dim] = space[nidx]
                        impact = _impact(evaluate(candidate))
                        if impact < best_impact:
                            best_impact, best_action, improved = impact, candidate, True

        # The applied episode: run the chosen action on the task's canonical seed. Search effort
        # (`attempts`) is toil; this is the outcome the fabric would actually ship.
        applied = simulate(task.params, best_action, task.seed)
        return SolveResult(action=best_action, attempts=attempts, metrics=applied)


class LLMStrategist:
    """Optional strategist behind `--strategist=llm`. Stub by design (CLAUDE.md anti-goal: no LLM in
    the core path). Same interface as HeuristicStrategist; a real implementation would only *propose*
    an action — the protocol still validates it by replay, never by reading language."""

    def solve(self, task: Task, prior: dict | None = None) -> SolveResult:
        raise NotImplementedError(
            "LLMStrategist is a stub: the core path never calls an LLM (CLAUDE.md). "
            "Run with the default HeuristicStrategist (--strategist=heuristic)."
        )
