"""The Pawl — pre-admission static checks, ordered, autonomous (BLUEPRINT §5.1, §6.1).

The pawl rule names the system: a capsule may tighten SAFETY/COMPLIANCE-class bounds but may never
loosen one — *the ratchet only turns one way for safety, by construction, not by review*. Every
check here is mechanical: the Pawl compares a capsule against registry data (dimension vocabulary,
protected bounds, class parameter space) and never interprets intent.

Pure function, no I/O (CLAUDE.md): `pawl_check(capsule, ctx)` takes data and returns data plus a
one-line, user-facing reason in the fixed format `"check_name: detail"` — the reason string is
displayed live when a capsule is blocked. Checks run strictly in §6.1 order and stop at the first
failure. An unexpected exception rejects with reason `internal_error` — fail-secure, never admit
(Phase 1 principle).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from fabric.capsule import Capsule, check_integrity
from fabric.config import (
    AGENTS,
    CLASS_PARAM_SPACE,
    CONTEXT_MAX_WIDTH_FRAC,
    MIN_N_EPISODES,
    RATE_PER_REPUTATION,
    RATE_WINDOW_S,
    REGISTRY_VERSION,
    REP_ISOLATION_FLOOR,
)
from fabric.registry import (
    ACTION_DIMENSIONS,
    PROTECTED_BOUNDS,
    conforms,
    context_priority_class,
)

# Metrics a falsifiable claim may declare: solve_cost plus the raw episode KPIs, all cost-like
# (lower is better) so "improvement" always means a negative delta.
CLAIM_METRICS: tuple[str, ...] = (
    "solve_cost",
    "time_to_mitigate_s",
    "fp_quarantines",
    "sla_burn",
)


def _known_authors() -> tuple[str, ...]:
    return tuple(f"agent:{agent_id}" for agent_id, _site in AGENTS)


@dataclass(frozen=True)
class PawlContext:
    """Node-local facts the Pawl needs beyond the capsule itself (check 5). Passed in so
    `pawl_check` stays pure; defaults are benign (a known author in good standing)."""

    known_authors: tuple[str, ...] = field(default_factory=_known_authors)
    reputation: float = 1.0
    submissions_in_window: int = 0


@dataclass(frozen=True)
class PawlResult:
    """Outcome of the ordered checks: `check` names the failing check ('' when all pass) and
    `reason` is the one-line user-facing string shown on a PAWL_BLOCK."""

    ok: bool
    check: str
    reason: str


def _fail(check: str, detail: str) -> PawlResult:
    return PawlResult(ok=False, check=check, reason=f"{check}: {detail}")


def _check_schema(capsule: Capsule, ctx: PawlContext) -> PawlResult | None:
    """§6.1 check 1 — schema + signature + registry version + author identity known."""
    if capsule.kind != "mitigation_rule":
        return _fail("schema", f"unknown capsule kind {capsule.kind!r}")
    if capsule.registry_version != REGISTRY_VERSION:
        return _fail(
            "schema",
            f"registry version {capsule.registry_version} does not match pinned {REGISTRY_VERSION}",
        )
    ok, why = check_integrity(capsule)
    if not ok:
        return _fail("schema", why)
    if capsule.provenance.author not in ctx.known_authors:
        return _fail("schema", f"author identity {capsule.provenance.author!r} not known to the mesh")
    return None


def _check_ratchet(capsule: Capsule) -> PawlResult | None:
    """§6.1 check 2 — ratchet monotonicity, mechanical (binding decision M3.3)."""
    rule = capsule.payload.rule
    for key in sorted(rule):
        if key not in ACTION_DIMENSIONS:
            return _fail(
                "ratchet monotonicity",
                f"unknown action dimension {key!r} — control-plane vocabulary is registry-only",
            )
        if not conforms(key, rule[key]):
            return _fail(
                "ratchet monotonicity",
                f"value {rule[key]!r} fails registry conformance for dimension {key!r}",
            )
    priority = context_priority_class(capsule.context.dims)
    for key in sorted(rule):
        prot = PROTECTED_BOUNDS.get(key)
        if prot is None or prot.priority_class != priority:
            continue
        value = float(rule[key])  # numeric by conformance above
        loosens = value < prot.bound if prot.direction == "floor" else value > prot.bound
        if loosens:
            return _fail(
                "ratchet monotonicity",
                f"capsule loosens {prot.priority_class} bound {key} {prot.bound:g}→{value:g}",
            )
    return None


def _check_bounded_context(capsule: Capsule) -> PawlResult | None:
    """§6.1 check 3 — no wildcard predicates; interval widths capped per dimension (blast radius)."""
    dims = capsule.context.dims
    space = CLASS_PARAM_SPACE.get(capsule.context.incident_class)
    if space is None:
        return _fail(
            "bounded context",
            f"unknown incident_class {capsule.context.incident_class!r} — no class parameter space",
        )
    if not dims:
        return _fail("bounded context", "empty dims is a wildcard predicate — declare a scope")
    for name in sorted(dims):
        if name not in space:
            return _fail(
                "bounded context",
                f"{name!r} is not a scenario dimension of class {capsule.context.incident_class!r}",
            )
        declared, domain = dims[name], space[name]
        if isinstance(domain, tuple) and all(isinstance(x, str) for x in domain):
            # Categorical dimension: declared must be a non-empty subset of the allowed values.
            if not isinstance(declared, (list, tuple)) or not declared:
                return _fail("bounded context", f"{name}: declare a non-empty list of values")
            bad = [v for v in declared if v not in domain]
            if bad:
                return _fail("bounded context", f"{name}: value {bad[0]!r} outside registry domain")
            continue
        # Interval dimension: [lo, hi] inside the class space, width capped (no wildcard intervals).
        if (
            not isinstance(declared, (list, tuple))
            or len(declared) != 2
            or not all(isinstance(v, (int, float)) for v in declared)
        ):
            return _fail("bounded context", f"{name}: declare an interval [lo, hi]")
        lo, hi = float(declared[0]), float(declared[1])
        dlo, dhi = float(domain[0]), float(domain[1])
        if lo > hi or lo < dlo or hi > dhi:
            return _fail(
                "bounded context",
                f"{name}: interval [{lo:g}, {hi:g}] outside class space [{dlo:g}, {dhi:g}]",
            )
        max_width = CONTEXT_MAX_WIDTH_FRAC * (dhi - dlo)
        if hi - lo > max_width:
            return _fail(
                "bounded context",
                f"{name}: width {hi - lo:g} exceeds cap {max_width:g} "
                f"({CONTEXT_MAX_WIDTH_FRAC:.0%} of class space) — wildcard-wide contexts are blocked",
            )
    return None


def _check_claim(capsule: Capsule) -> PawlResult | None:
    """§6.1 check 4 — falsifiable claim present; n_episodes ≥ 4; seeds present."""
    claim, evidence = capsule.claim, capsule.evidence
    if claim.metric not in CLAIM_METRICS:
        return _fail("falsifiable claim", f"unknown claim metric {claim.metric!r}")
    if claim.delta_pct >= 0:
        return _fail(
            "falsifiable claim",
            f"delta_pct {claim.delta_pct:g} claims no improvement — nothing to falsify",
        )
    if claim.n_episodes < MIN_N_EPISODES:
        return _fail(
            "falsifiable claim",
            f"n_episodes {claim.n_episodes} below minimum {MIN_N_EPISODES}",
        )
    if len(evidence.scenario_seeds) != claim.n_episodes:
        return _fail(
            "falsifiable claim",
            f"{len(evidence.scenario_seeds)} scenario seeds do not cover the claimed "
            f"{claim.n_episodes} episodes — the claim must be replayable",
        )
    return None


def _check_rate_reputation(capsule: Capsule, ctx: PawlContext) -> PawlResult | None:
    """§6.1 check 5 — rate & reputation: floor(3 × reputation) submissions per 100 sim-seconds;
    reputation below the isolation floor auto-rejects until decay recovery."""
    if ctx.reputation < REP_ISOLATION_FLOOR:
        return _fail(
            "rate/reputation",
            f"author reputation {ctx.reputation:.2f} below isolation floor "
            f"{REP_ISOLATION_FLOOR:.2f} — isolated until decay recovery",
        )
    allowance = math.floor(RATE_PER_REPUTATION * ctx.reputation)
    if ctx.submissions_in_window >= allowance:
        return _fail(
            "rate/reputation",
            f"{ctx.submissions_in_window} submissions in the last {RATE_WINDOW_S:g} sim-s reach "
            f"the allowance floor({RATE_PER_REPUTATION}×{ctx.reputation:.2f})={allowance}",
        )
    return None


def pawl_check(capsule: Capsule, ctx: PawlContext | None = None) -> PawlResult:
    """Run the five §6.1 checks in order; return the first failure, or an ok result.

    Ordering is part of the contract (unit-tested): a capsule failing several checks is reported
    against the earliest, so reason strings are stable demo material.
    """
    ctx = ctx or PawlContext()
    try:
        for check in (
            lambda: _check_schema(capsule, ctx),
            lambda: _check_ratchet(capsule),
            lambda: _check_bounded_context(capsule),
            lambda: _check_claim(capsule),
            lambda: _check_rate_reputation(capsule, ctx),
        ):
            failure = check()
            if failure is not None:
                return failure
        return PawlResult(ok=True, check="", reason="ok")
    except Exception as exc:  # fail-secure: never admit on an unexpected error (CLAUDE.md)
        return _fail("internal_error", f"unexpected {type(exc).__name__} during pawl check")
