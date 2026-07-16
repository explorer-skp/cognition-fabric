"""Arbitration — deterministic capsule selection for a live task (BLUEPRINT §7, decision M4.3).

*Storage is eventually consistent. Meaning is scoped. Decisions are deterministic.* When more than
one ACTIVE capsule applies to a task, every replica must choose the same one with no coordinator — so
selection is a pure function of the replicated capsules: **priority class lexicographically →
confidence × |claimed effect| → capsule-id hash tie-break**. Same inputs everywhere ⇒ same answer,
no split-brain behavior even while stores momentarily diverge.

`applies` and `arbitrate` are pure and author-independent (CLAUDE.md); `active_matches` reads a
node's local `(store, ledger)` and derives ACTIVE via `gossip.derive_state` (promotion is derived,
never stored — decision M4.2).

`refine_split` + `OverlapTracker` (milestone M6, BLUEPRINT §7.4): a persistent overlap — the same
two capsules arbitrated between on `REFINE_THRESHOLD` tasks — is treated as an underspecified
context, not a conflict to resolve by deletion. `refine_split` is pure (declared contexts in,
narrowed contexts out); `OverlapTracker` is the immutable-update counter that decides *when* to call
it, the same pattern as `fabric.lifecycle.ShadowTracker`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from fabric.capsule import Capsule, LifecycleState
from fabric.config import REFINE_THRESHOLD
from fabric.gossip import ShadowLedger, derive_state
from fabric.registry import context_priority_class
from fabric.store import Store
from world.taskgen import Task


def applies(capsule: Capsule, task: Task) -> bool:
    """True iff the task falls inside the capsule's declared context: class equal and every declared
    dimension contains the task's parameter (numeric interval `[lo, hi]` or categorical set — the
    same numeric-vs-set discrimination the Pawl uses for bounded contexts)."""
    if capsule.context.incident_class != task.incident_class:
        return False
    for name, declared in capsule.context.dims.items():
        value = task.params.get(name)
        if value is None:
            return False
        is_interval = (
            isinstance(declared, (list, tuple))
            and len(declared) == 2
            and all(isinstance(x, (int, float)) for x in declared)
        )
        if is_interval:
            if not (float(declared[0]) <= float(value) <= float(declared[1])):
                return False
        else:
            if value not in declared:
                return False
    return True


@dataclass(frozen=True)
class Applicable:
    """An ACTIVE capsule that matches a task, with the confidence its node derived for it."""

    capsule: Capsule
    confidence: float


def _id_hash(capsule_id: str) -> int:
    return int(hashlib.sha256(capsule_id.encode("utf-8")).hexdigest(), 16)


def arbitrate(applicables: list[Applicable]) -> Applicable | None:
    """Pick the winning capsule deterministically (decision M4.3): highest priority class
    lexicographically, then greatest `confidence × |claim.delta_pct|`, then the smaller capsule-id
    hash. Pure and author-independent — every replica returns the same winner. None if empty.

    # DECISION: priority class compared lexicographically per BLUEPRINT §7 — a COMPLIANCE-scoped
    # context (from `context_priority_class`) outranks an unscoped one (`""`), and the scheme
    # generalizes to any future label set by string order. Tie-break: the capsule whose id hashes
    # smaller wins (negate the hash so `max` selects it).
    """
    if not applicables:
        return None
    return max(
        applicables,
        key=lambda a: (
            context_priority_class(a.capsule.context.dims) or "",
            a.confidence * abs(a.capsule.claim.delta_pct),
            -_id_hash(a.capsule.capsule_id),
        ),
    )


def active_matches(
    store: Store, ledger: ShadowLedger, task: Task, node_ids: set[str] | None = None
) -> list[Applicable]:
    """Every capsule this node currently derives ACTIVE that applies to the task, with confidence.

    Reads local state only (fabric-query-before-solve): a capsule is ACTIVE iff its replicated shadow
    records clear the mesh quorum (`derive_state`), never because ACTIVE was gossiped as a fact.
    """
    matches: list[Applicable] = []
    for cid in sorted(store.live_ids()):
        capsule = store.get(cid)
        if capsule is None or not applies(capsule, task):
            continue
        derived = derive_state(store, ledger, cid, node_ids)
        if derived.state == LifecycleState.ACTIVE:
            matches.append(Applicable(capsule=capsule, confidence=derived.confidence))
    return matches


# --- Refine: persistent overlap is an underspecified context (BLUEPRINT §7.4, milestone M6) -----

@dataclass(frozen=True)
class OverlapTracker:
    """Counts how many times the same pair of capsules has been arbitrated between, keyed by
    `(winner_id, loser_id)` — the "same overlap arbitrates repeatedly (≥ REFINE_THRESHOLD tasks)"
    trigger. Immutable-update, mirroring `fabric.lifecycle.ShadowTracker`'s pattern: `record_overlap`
    returns a *new* tracker rather than mutating in place."""

    counts: dict[tuple[str, str], int] = field(default_factory=dict)


def record_overlap(
    tracker: OverlapTracker, winner: Applicable, loser: Applicable
) -> tuple[OverlapTracker, bool]:
    """Record one arbitration between `winner` and `loser`. Returns `(updated_tracker,
    should_refine)` — `should_refine` is True the tick the pair's count reaches REFINE_THRESHOLD
    (the caller's cue to call `refine_split`), then stays False on further calls for the same pair
    unless the caller resets the tracker after acting on it (no re-triggering on a stale count)."""
    key = (winner.capsule.capsule_id, loser.capsule.capsule_id)
    counts = dict(tracker.counts)
    counts[key] = counts.get(key, 0) + 1
    return OverlapTracker(counts=counts), counts[key] == REFINE_THRESHOLD


@dataclass(frozen=True)
class RefineResult:
    """The outcome of resolving a persistent overlap: either a split along the declared dimension
    where the two capsules' contexts separate most (BLUEPRINT §7.4 — "pick the dim with disjoint or
    least-overlapping ranges"), or, if no declared dimension separates them at all, the winner takes
    the whole overlap and the loser is wholly superseded."""

    dimension: str | None
    winner_dims: dict
    loser_dims: dict | None
    reason: str


def _numeric_interval(dims: dict, name: str) -> tuple[float, float] | None:
    value = dims.get(name)
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(
        isinstance(x, (int, float)) for x in value
    ):
        return float(value[0]), float(value[1])
    return None


def refine_split(winner: Applicable, loser: Applicable) -> RefineResult:
    """Resolve a persistent overlap between two ACTIVE capsules for the same class (BLUEPRINT §7.4,
    milestone M6). Pure: `winner`/`loser` are the caller's own prior `arbitrate()` result — this
    function never re-arbitrates, it only decides how to sharpen the map.

    Picks the numeric dimension shared by both declared contexts where the two intervals overlap
    the *least* (their "seed-episode parameter ranges" — the declared `context.dims` — are exactly
    the stored evidence range per capsule), and splits both capsules' interval on that dimension at
    the overlap's midpoint: the capsule whose original interval is centered lower keeps the lower
    sub-range. If every shared numeric dimension is identical (zero separation anywhere), nothing
    distinguishes the two contexts — the winner takes the whole overlap, the loser is superseded.
    """
    winner_dims, loser_dims = winner.capsule.context.dims, loser.capsule.context.dims
    shared = sorted(set(winner_dims) & set(loser_dims))
    best_dim: str | None = None
    best_overlap_frac = 1.0
    for name in shared:
        w_iv, l_iv = _numeric_interval(winner_dims, name), _numeric_interval(loser_dims, name)
        if w_iv is None or l_iv is None:
            continue
        overlap = max(0.0, min(w_iv[1], l_iv[1]) - max(w_iv[0], l_iv[0]))
        union = max(w_iv[1], l_iv[1]) - min(w_iv[0], l_iv[0])
        frac = overlap / union if union > 0 else 1.0
        if frac < best_overlap_frac:
            best_dim, best_overlap_frac = name, frac

    if best_dim is None or best_overlap_frac >= 1.0:
        return RefineResult(
            dimension=None, winner_dims=dict(winner_dims), loser_dims=None,
            reason="no declared dimension separates the two capsules — winner takes the whole "
                   "overlap, loser is superseded",
        )

    w_iv, l_iv = _numeric_interval(winner_dims, best_dim), _numeric_interval(loser_dims, best_dim)
    split_point = round((max(w_iv[0], l_iv[0]) + min(w_iv[1], l_iv[1])) / 2.0, 4)
    w_center, l_center = (w_iv[0] + w_iv[1]) / 2.0, (l_iv[0] + l_iv[1]) / 2.0
    new_winner_dims, new_loser_dims = dict(winner_dims), dict(loser_dims)
    if w_center <= l_center:
        new_winner_dims[best_dim] = [w_iv[0], split_point]
        new_loser_dims[best_dim] = [split_point, l_iv[1]]
    else:
        new_winner_dims[best_dim] = [split_point, w_iv[1]]
        new_loser_dims[best_dim] = [l_iv[0], split_point]
    return RefineResult(
        dimension=best_dim, winner_dims=new_winner_dims, loser_dims=new_loser_dims,
        reason=f"split along {best_dim!r} at {split_point} — prior overlap fraction {best_overlap_frac:.2f}",
    )
