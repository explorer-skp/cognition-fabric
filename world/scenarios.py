"""Seeded episode simulators, one per incident class (BLUEPRINT §8).

An episode is `simulate(incident_params, action, seed) -> EpisodeMetrics`, deterministic given
`(params, action, seed)`. The internals are a few dozen lines of legible arithmetic per class; the
*shape* is what matters: wrong action ⇒ high cost, right action region ⇒ low cost, and a
class-dependent optimum that shifts with the incident parameters.

`invariant_hits` is computed from the constitution in `fabric/registry.py` — an action that would
bypass inspection or run a non-compliant blanket block registers a hit, which the cost model
punishes heavily (and which the Pawl will block outright from M3).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from fabric.config import ACTION_SPACE
from fabric.registry import COMPLIANCE_SITE_CLASS

# Action dimensions each class actually responds to — the Strategist hill-climbs only these.
RELEVANT_DIMS: dict[str, list[str]] = {
    "ddos_syn_flood": ["rate_limit_pps", "inspection_depth"],
    "iot_anomaly_burst": ["quarantine_scope", "sampled_fraction"],
    "cert_expiry_storm": ["retry_backoff_ms", "block_ttl_s"],
}

# Incident classes whose traffic contains flagged flows that must be inspected.
_FLAGGED_FLOW_CLASSES = frozenset({"ddos_syn_flood", "iot_anomaly_burst"})

_SCOPE_INDEX = {"none": 0, "flagged_only": 1, "subnet": 2}


@dataclass(frozen=True)
class EpisodeMetrics:
    """Outcome of one simulated episode (BLUEPRINT §8 episode model)."""

    time_to_mitigate_s: float
    fp_quarantines: int
    sla_burn: float
    invariant_hits: int

    def as_dict(self) -> dict:
        return asdict(self)


def check_invariants(action: dict, incident_class: str, site_class: str) -> list[str]:
    """Names of constitution invariants an action would violate in this context (BLUEPRINT §8).

    Pure and reused everywhere: scenarios compute `invariant_hits` from it, and agents enforce it
    locally as their own guardrail (adoption-as-prior — a capsule can never make an agent violate
    its constitution, BLUEPRINT §4).
    """
    hits: list[str] = []
    if action.get("inspection_depth", 0) <= 0 and incident_class in _FLAGGED_FLOW_CLASSES:
        hits.append("no_flagged_flow_bypasses_inspection")
    if action.get("quarantine_scope") == "subnet" and site_class != COMPLIANCE_SITE_CLASS:
        hits.append("no_blanket_subnet_block_without_compliance_class")
    if action.get("block_ttl_s", 1) <= 0:
        # A block that never expires is not reversible.
        hits.append("quarantine_reversible")
    return hits


def _sim_ddos(params: dict, action: dict, rng: random.Random) -> tuple[float, int, float]:
    # Optimum: rate-limit threshold scales with offered load; moderate inspection depth.
    traffic = float(params["traffic_gbps"])
    ideal_rate = 1000.0 * traffic
    rate = float(action["rate_limit_pps"])
    err_rate = min(1.0, abs(rate - ideal_rate) / max(ideal_rate, 1.0))
    err_insp = abs(float(action["inspection_depth"]) - 3.0) / 7.0
    noise = rng.uniform(-1.0, 1.0)
    time_s = 30.0 * (1.0 + 2.0 * err_rate + 0.5 * err_insp) + noise
    # Over-blocking (threshold below the ideal) quarantines legitimate flows.
    under = max(0.0, (ideal_rate - rate) / max(ideal_rate, 1.0))
    fp = round(6.0 * under)
    sla = time_s / 20.0
    return time_s, fp, sla


def _sim_iot(params: dict, action: dict, rng: random.Random) -> tuple[float, int, float]:
    # Optimum: sample more of a larger fleet; contain at flagged-flow scope, never blanket subnet.
    devices = float(params["device_count"])
    ideal_sample = min(1.0, max(0.1, devices / 500.0))
    err_sample = abs(float(action["sampled_fraction"]) - ideal_sample)
    err_scope = abs(_SCOPE_INDEX[action["quarantine_scope"]] - 1) / 2.0
    noise = rng.uniform(-1.0, 1.0)
    time_s = 25.0 * (1.0 + 1.5 * err_sample + 1.0 * err_scope) + noise
    fp = 6 if action["quarantine_scope"] == "subnet" else round(4.0 * err_sample)
    sla = time_s / 25.0
    return time_s, fp, sla


def _sim_cert(params: dict, action: dict, rng: random.Random) -> tuple[float, int, float]:
    # Optimum: a middle retry backoff and a bounded block TTL clear the storm fastest.
    ideal_backoff, ideal_ttl = 200.0, 120.0
    err_bo = min(1.0, abs(float(action["retry_backoff_ms"]) - ideal_backoff) / ideal_backoff)
    err_ttl = min(1.0, abs(float(action["block_ttl_s"]) - ideal_ttl) / ideal_ttl)
    noise = rng.uniform(-1.0, 1.0)
    time_s = 28.0 * (1.0 + 1.2 * err_bo + 0.8 * err_ttl) + noise
    fp = round(2.0 * err_ttl)
    sla = time_s / 22.0
    return time_s, fp, sla


_SIMULATORS = {
    "ddos_syn_flood": _sim_ddos,
    "iot_anomaly_burst": _sim_iot,
    "cert_expiry_storm": _sim_cert,
}


def simulate(incident_params: dict, action: dict, seed: int) -> EpisodeMetrics:
    """Run one deterministic episode. `incident_params` carries `incident_class` and `site_class`.

    Fail-secure (Phase 1 principle): an unknown class is a programming error, not a silent zero-cost
    episode — raise rather than admit a meaningless metric.
    """
    incident_class = incident_params["incident_class"]
    site_class = incident_params["site_class"]
    sim = _SIMULATORS.get(incident_class)
    if sim is None:
        raise ValueError(f"no scenario simulator for incident_class={incident_class!r}")
    rng = random.Random(seed)
    time_s, fp, sla = sim(incident_params, action, rng)
    hits = check_invariants(action, incident_class, site_class)
    return EpisodeMetrics(
        time_to_mitigate_s=round(max(0.0, time_s), 4),
        fp_quarantines=max(0, int(fp)),
        sla_burn=round(max(0.0, sla), 4),
        invariant_hits=len(hits),
    )


def relevant_dims(incident_class: str) -> list[str]:
    return list(RELEVANT_DIMS.get(incident_class, list(ACTION_SPACE.keys())))
