"""Registry of typed operational dimensions + the constitution's invariants (BLUEPRINT §1, §8).

Ported structure from Phase 1: each dimension carries a unit and a conformance test; each
invariant is a hard predicate no capsule may violate. Registry version is pinned in config.

The dimensions and invariants here are *data the Pawl and Jury reason over* (from M3). At M0
they define the legal action/parameter space and let scenarios compute `invariant_hits`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fabric.config import REGISTRY_VERSION


@dataclass(frozen=True)
class Dimension:
    """A typed operational dimension. `conformance` returns True iff a value is well-formed."""

    name: str
    unit: str
    kind: str  # "interval" (numeric range) or "set" (categorical)
    domain: Any  # (lo, hi) for interval; tuple of allowed values for set
    conformance: Callable[[Any], bool]


def _interval(name: str, unit: str, lo: float, hi: float) -> Dimension:
    return Dimension(
        name=name,
        unit=unit,
        kind="interval",
        domain=(lo, hi),
        conformance=lambda v, lo=lo, hi=hi: isinstance(v, (int, float)) and lo <= v <= hi,
    )


def _set(name: str, unit: str, allowed: tuple) -> Dimension:
    return Dimension(
        name=name,
        unit=unit,
        kind="set",
        domain=allowed,
        conformance=lambda v, allowed=allowed: v in allowed,
    )


# --- Registry v3.2 dimensions (BLUEPRINT §8) ---------------------------------
# Action dimensions (what a mitigation sets) + scenario dimensions (what an incident presents).
DIMENSIONS: dict[str, Dimension] = {
    d.name: d
    for d in (
        # action dimensions
        _interval("rate_limit_pps", "packets/s", 0, 100_000),
        _interval("inspection_depth", "levels", 0, 7),
        _set("quarantine_scope", "enum", ("none", "flagged_only", "subnet")),
        _interval("retry_backoff_ms", "ms", 0, 10_000),
        _interval("sampled_fraction", "fraction", 0.0, 1.0),
        _interval("block_ttl_s", "s", 0, 86_400),
        # scenario dimensions
        _interval("traffic_gbps", "Gbps", 0.0, 100.0),
        _interval("device_count", "devices", 0, 100_000),
        _set("site_class", "enum", ("branch", "campus", "dc")),
    )
}

# --- Invariants / constitution (BLUEPRINT §8) --------------------------------
# Hard predicates no capsule (and no live decision) may violate. These are the names quoted in
# capsule.evidence.conformance_required and in Pawl reason strings — do not rename.
INVARIANTS: tuple[str, ...] = (
    "no_flagged_flow_bypasses_inspection",
    "quarantine_reversible",
    "p99_latency_within_slo",
    "no_blanket_subnet_block_without_compliance_class",
)

# The site class that carries a compliance mandate (allowed to run subnet-wide blocks).
# DECISION: "dc" (datacenter) is the compliance-classed site; branch/campus are not, so a
# blanket subnet block there trips `no_blanket_subnet_block_without_compliance_class`.
COMPLIANCE_SITE_CLASS = "dc"


def dimension(name: str) -> Dimension:
    return DIMENSIONS[name]


def conforms(name: str, value: Any) -> bool:
    """True iff `value` is a well-formed value for dimension `name`."""
    dim = DIMENSIONS.get(name)
    return bool(dim and dim.conformance(value))


def registry_version() -> str:
    return REGISTRY_VERSION
