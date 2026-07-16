"""TaskGen — the dynamic flow of enterprise incidents (BLUEPRINT §8, requirement 1).

Fully seeded: Poisson arrivals whose rate λ drifts over the run, an incident-class mix that drifts
on a schedule, and in-class parameters that drift ("changing conditions"). One `random.Random`
stream drives generation; each task carries its own per-episode `seed` so the episode simulator has
an independent, reproducible stream (BLUEPRINT determinism rule: one stream per concern).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from fabric.config import (
    INCIDENT_CLASSES,
    SITE_CLASSES,
    TASKGEN_LAMBDA_BASE,
    TASKGEN_LAMBDA_DRIFT,
    TASKGEN_PARAM_DRIFT,
)


@dataclass(frozen=True)
class Task:
    """One incident ticket. `params` carries `incident_class`, `site_class`, and numeric dims."""

    task_id: str
    incident_class: str
    site_class: str
    params: dict = field(default_factory=dict)
    arrival_sim: float = 0.0
    seed: int = 0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _class_mix_weights(progress: float) -> list[float]:
    """Drift the class mix: earlier classes dominate early, later classes dominate late."""
    k = len(INCIDENT_CLASSES)
    start_w = [k - i for i in range(k)]      # favors the first classes
    end_w = [i + 1 for i in range(k)]        # favors the last classes
    return [(1.0 - progress) * s + progress * e for s, e in zip(start_w, end_w)]


def _pick_class(progress: float, rng) -> str:
    weights = _class_mix_weights(progress)
    total = sum(weights)
    r = rng.random() * total
    upto = 0.0
    for cls, w in zip(INCIDENT_CLASSES, weights):
        upto += w
        if r <= upto:
            return cls
    return INCIDENT_CLASSES[-1]


def _sample_params(incident_class: str, site_class: str, progress: float, rng) -> dict:
    # In-class parameter drift: multiply nominal ranges by a slow drift factor in [0.8, 1.2].
    drift = 1.0 + TASKGEN_PARAM_DRIFT * (progress - 0.5) * 2.0
    traffic = _clamp(rng.uniform(1.0, 10.0) * drift, 1.0, 12.0)
    device = int(_clamp(rng.uniform(50.0, 500.0) * drift, 10.0, 800.0))
    return {
        "incident_class": incident_class,
        "site_class": site_class,
        "traffic_gbps": round(traffic, 3),
        "device_count": device,
    }


def generate(seed: int, n: int) -> list[Task]:
    """Produce `n` deterministic tasks from `seed`. Same (seed, n) → identical task stream."""
    import random

    rng = random.Random(seed)
    tasks: list[Task] = []
    t = 0.0
    for i in range(n):
        progress = i / max(n - 1, 1)
        lam = TASKGEN_LAMBDA_BASE + TASKGEN_LAMBDA_DRIFT * math.sin(2.0 * math.pi * progress)
        t += rng.expovariate(lam)
        incident_class = _pick_class(progress, rng)
        site_class = rng.choice(SITE_CLASSES)
        params = _sample_params(incident_class, site_class, progress, rng)
        episode_seed = rng.randrange(1, 2_000_000_000)
        tasks.append(
            Task(
                task_id=f"t{i:04d}",
                incident_class=incident_class,
                site_class=site_class,
                params=params,
                arrival_sim=round(t, 4),
                seed=episode_seed,
            )
        )
    return tasks
