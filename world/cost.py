"""The cost model (BLUEPRINT §8): one number that stands in for analyst toil + service impact.

    solve_cost = 2.0*attempts + 0.05*time_to_mitigate_s + 5.0*fp_quarantines
               + 1.0*sla_burn + 25.0*invariant_hits

`attempts` ≈ analyst-minutes of toil (the *discovery* cost the ratchet removes); the rest ≈ service
impact. `invariant_hits` must remain zero in any healthy run — its weight is punitive by design.
All weights are named constants in `fabric/config.py`, so demo numbers reproduce by construction.
"""

from __future__ import annotations

from fabric.config import (
    COST_W_ATTEMPT,
    COST_W_FP,
    COST_W_INVARIANT,
    COST_W_SLA,
    COST_W_TIME,
)
from world.scenarios import EpisodeMetrics


def solve_cost(attempts: int, metrics: EpisodeMetrics) -> float:
    """Total cost of solving a task: search effort (`attempts`) plus the applied episode's impact."""
    return round(
        COST_W_ATTEMPT * attempts
        + COST_W_TIME * metrics.time_to_mitigate_s
        + COST_W_FP * metrics.fp_quarantines
        + COST_W_SLA * metrics.sla_burn
        + COST_W_INVARIANT * metrics.invariant_hits,
        4,
    )
