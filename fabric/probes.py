"""Sentinel probes + bisect: memory has CI (BLUEPRINT §6.4, milestone M5).

Admission validates a capsule's *claim*; Sentinels validate the *system*. Every `PROBE_PERIOD`
sim-seconds each node replays a pinned golden suite against its own derived-ACTIVE view — through
the exact `active_matches` → `arbitrate` → `solve(prior)` path live reuse takes — and compares the
harm KPIs one-sidedly against clean no-capsule baselines (binding decision M5.1): an alarm fires iff
`fp_quarantines` or `sla_burn` exceeds baseline × (1 + PROBE_TOL) on any scenario, or any invariant
is hit anywhere. `solve_cost` may move freely — the fabric exists to move it.

`bisect_culprit` then finds the poisoned capsule the way engineers find a bad commit: suspects are
the derived-ACTIVE capsules ordered by quorum-cert sim-time, halved per step over golden-suite
replays (binding decision M5.3) — one culprit per pass; the caller loops excise → re-probe until
clean.

Everything here is pure data-in/data-out (CLAUDE.md); events go through injected emitters.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.strategist import HeuristicStrategist, Strategist
from fabric.arbitration import active_matches, arbitrate
from fabric.capsule import LifecycleState
from fabric.config import PROBE_PERIOD, PROBE_TOL
from fabric.gossip import ShadowLedger, derive_state
from fabric.lifecycle import Emitter, _noop_emit
from fabric.store import Store
from world.scenarios import EpisodeMetrics
from world.taskgen import Task

# The harm KPIs a probe alarms on (binding decision M5.1). Never solve_cost.
HARM_KPIS: tuple[str, ...] = ("fp_quarantines", "sla_burn")

# DECISION: the golden suite is pinned scenario *data* and lives beside the code that replays it
# (locality, like the per-class shape coefficients in world/scenarios.py); the judge-facing
# thresholds (PROBE_PERIOD, PROBE_TOL) stay in fabric/config.py. 12 scenarios span all three
# incident classes and all three site classes; every parameter sits on the quantized action grid's
# optima so an honest capsule's refined action matches the clean baseline — no false alarms by
# construction, drift alarms mean harm.
GOLDEN_SUITE: tuple[tuple[str, dict, int], ...] = (
    ("ddos_syn_flood", {"site_class": "branch", "traffic_gbps": 4.0}, 5000),
    ("ddos_syn_flood", {"site_class": "campus", "traffic_gbps": 6.0}, 5097),
    ("ddos_syn_flood", {"site_class": "branch", "traffic_gbps": 7.0}, 5194),
    ("ddos_syn_flood", {"site_class": "campus", "traffic_gbps": 8.0}, 5291),
    ("ddos_syn_flood", {"site_class": "campus", "traffic_gbps": 10.0}, 5388),
    ("iot_anomaly_burst", {"site_class": "branch", "device_count": 50}, 5485),
    ("iot_anomaly_burst", {"site_class": "campus", "device_count": 125}, 5582),
    ("iot_anomaly_burst", {"site_class": "dc", "device_count": 250}, 5679),
    ("iot_anomaly_burst", {"site_class": "campus", "device_count": 500}, 5776),
    ("cert_expiry_storm", {"site_class": "branch"}, 5873),
    ("cert_expiry_storm", {"site_class": "campus"}, 5970),
    ("cert_expiry_storm", {"site_class": "dc"}, 6067),
)


def golden_task(index: int) -> Task:
    """The pinned Task for one golden-suite entry — byte-deterministic for any node, any run."""
    incident_class, params, seed = GOLDEN_SUITE[index]
    return Task(
        task_id=f"golden-{index:02d}-{incident_class}",
        incident_class=incident_class,
        site_class=params["site_class"],
        params={"incident_class": incident_class, **params},
        arrival_sim=0.0,
        seed=seed,
    )


def clean_baselines(strategist: Strategist) -> dict[str, EpisodeMetrics]:
    """Each golden scenario solved with NO capsule prior (binding decision M5.1) — the recorded
    golden baselines. Pure and deterministic: computed once, identical on every node."""
    baselines: dict[str, EpisodeMetrics] = {}
    for index in range(len(GOLDEN_SUITE)):
        task = golden_task(index)
        baselines[task.task_id] = strategist.solve(task, prior=None).metrics
    return baselines


# --- The probe (one sweep of the golden suite) -----------------------------------

@dataclass(frozen=True)
class ProbeRow:
    """One golden scenario's replay: which capsule (if any) arbitration applied, and the KPIs."""

    task_id: str
    incident_class: str
    capsule_id: str | None
    metrics: EpisodeMetrics
    baseline: EpisodeMetrics


@dataclass(frozen=True)
class Alarm:
    """One KPI regression: the scenario, the KPI, the numbers, and the user-facing reason line."""

    task_id: str
    kpi: str
    measured: float
    allowed: float
    capsule_id: str | None
    reason: str


@dataclass(frozen=True)
class ProbeReport:
    """One probe sweep: every golden row plus the alarms (empty ⇒ the memory is clean)."""

    rows: tuple[ProbeRow, ...]
    alarms: tuple[Alarm, ...]

    @property
    def clean(self) -> bool:
        return not self.alarms


def probe(
    store: Store,
    ledger: ShadowLedger,
    strategist: Strategist,
    baselines: dict[str, EpisodeMetrics],
    *,
    node_ids: set[str] | None = None,
    disabled: frozenset[str] | set[str] = frozenset(),
) -> ProbeReport:
    """Replay the golden suite against this node's current derived-ACTIVE view (minus `disabled`,
    bisect's lever) through the same solve(prior)/arbitrate path live reuse takes, and check the
    harm KPIs one-sidedly against the clean baselines (binding decision M5.1)."""
    rows: list[ProbeRow] = []
    alarms: list[Alarm] = []
    for index in range(len(GOLDEN_SUITE)):
        task = golden_task(index)
        matches = [
            m for m in active_matches(store, ledger, task, node_ids)
            if m.capsule.capsule_id not in disabled
        ]
        winner = arbitrate(matches)
        prior = dict(winner.capsule.payload.rule) if winner is not None else None
        result = strategist.solve(task, prior=prior)
        baseline = baselines[task.task_id]
        capsule_id = winner.capsule.capsule_id if winner is not None else None
        under = f"capsule {capsule_id[:12]}" if capsule_id else "no capsule"
        rows.append(
            ProbeRow(
                task_id=task.task_id,
                incident_class=task.incident_class,
                capsule_id=capsule_id,
                metrics=result.metrics,
                baseline=baseline,
            )
        )
        for kpi in HARM_KPIS:
            measured = float(getattr(result.metrics, kpi))
            allowed = float(getattr(baseline, kpi)) * (1.0 + PROBE_TOL)
            if measured > allowed:
                alarms.append(
                    Alarm(
                        task_id=task.task_id,
                        kpi=kpi,
                        measured=measured,
                        allowed=round(allowed, 4),
                        capsule_id=capsule_id,
                        reason=(
                            f"{kpi} {measured:g} > baseline {getattr(baseline, kpi):g} × "
                            f"(1+{PROBE_TOL:g}) on {task.task_id} under {under}"
                        ),
                    )
                )
        if result.metrics.invariant_hits > 0:
            alarms.append(
                Alarm(
                    task_id=task.task_id,
                    kpi="invariant_hits",
                    measured=float(result.metrics.invariant_hits),
                    allowed=0.0,
                    capsule_id=capsule_id,
                    reason=(
                        f"invariant hit ({result.metrics.invariant_hits}) on {task.task_id} "
                        f"under {under} — zero tolerance"
                    ),
                )
            )
    return ProbeReport(rows=tuple(rows), alarms=tuple(alarms))


# --- The Sentinel (per-node scheduler, decision M5.2) -----------------------------

class Sentinel:
    """One node's Sentinel: probes its OWN local `(store, ledger)` view every PROBE_PERIOD sim-s.

    Golden baselines are computed once at construction (deterministic — identical on every node).
    # DECISION: harness-first, like M3's shadow staging — tests (and M6's chaos loop) drive
    # `tick()`; wiring ticks into the live agent loop is demo pacing work and `agents/` is outside
    # M5's scope lock.
    """

    def __init__(
        self,
        node_id: str,
        store: Store,
        ledger: ShadowLedger,
        *,
        strategist: Strategist | None = None,
        node_ids: set[str] | None = None,
    ) -> None:
        self.node_id = node_id
        self.store = store
        self.ledger = ledger
        self.strategist = strategist or HeuristicStrategist()
        self.node_ids = node_ids
        self.baselines = clean_baselines(self.strategist)
        self.last_probe: float | None = None

    def due(self, sim_time: float) -> bool:
        return self.last_probe is None or sim_time - self.last_probe >= PROBE_PERIOD

    def tick(self, sim_time: float, emit: Emitter = _noop_emit) -> ProbeReport | None:
        """Probe if a probe period has elapsed; emit PROBE and one DRIFT_ALARM per KPI regression
        (the alarm names the KPI — that is the demo's headline line). None when not due."""
        if not self.due(sim_time):
            return None
        self.last_probe = sim_time
        report = probe(
            self.store, self.ledger, self.strategist, self.baselines, node_ids=self.node_ids
        )
        emit(
            "PROBE",
            sim_time,
            node=self.node_id,
            scenarios=len(report.rows),
            alarms=len(report.alarms),
            clean=report.clean,
        )
        for alarm in report.alarms:
            emit(
                "DRIFT_ALARM",
                sim_time,
                node=self.node_id,
                kpi=alarm.kpi,
                task_id=alarm.task_id,
                capsule_id=alarm.capsule_id,
                measured=alarm.measured,
                allowed=alarm.allowed,
                reason=alarm.reason,
            )
        return report


# --- Bisect (decision M5.3) -------------------------------------------------------

@dataclass(frozen=True)
class BisectStep:
    """One halving step: which suspects were enabled in isolation, whether the probe alarmed, and
    the window the culprit was narrowed to."""

    step: int
    enabled: tuple[str, ...]
    alarmed: bool
    window: tuple[str, ...]
    reason: str


def suspects(
    store: Store, ledger: ShadowLedger, node_ids: set[str] | None = None
) -> list[str]:
    """Bisect's suspect list: this node's derived-ACTIVE capsules ordered by quorum-cert sim-time
    (binding decision M5.3), ties broken by capsule id — oldest activation first."""
    ordered: list[tuple[float, str]] = []
    for cid in sorted(store.live_ids()):
        if derive_state(store, ledger, cid, node_ids).state != LifecycleState.ACTIVE:
            continue
        cert = (store.lifecycle_of(cid) or {}).get("quorum_cert") or {}
        ordered.append((float(cert.get("sim_time", 0.0)), cid))
    return [cid for _t, cid in sorted(ordered)]


def bisect_culprit(
    store: Store,
    ledger: ShadowLedger,
    strategist: Strategist,
    baselines: dict[str, EpisodeMetrics],
    suspect_ids: list[str],
    *,
    node_ids: set[str] | None = None,
    sim_time: float = 0.0,
    emit: Emitter = _noop_emit,
) -> tuple[str | None, list[BisectStep]]:
    """Standard halving over golden-suite replays: each step replays the suite with ONLY half the
    window enabled (every other suspect disabled). An alarm proves a culprit sits in that half; a
    clean probe sends the search to the other half. O(log n) probes to one culprit per pass
    (binding decision M5.3) — the caller loops excise → re-probe until clean.

    # DECISION: the halves are probed in isolation (disable window-complement, not the half) —
    # arbitration can let one ACTIVE capsule mask another on shared golden scenarios, and disabling
    # only the tested half would let a masked culprit alarm from outside it and derail the search.
    # In-isolation probing keeps the invariant "the window always contains a culprit" regardless of
    # masking; a capsule whose harm never manifests through live arbitration is, by construction,
    # not drift the Sentinel can see.

    Returns (culprit, steps); culprit is None if the suspects probe clean with nothing disabled."""
    window = list(suspect_ids)
    if not window or probe(
        store, ledger, strategist, baselines, node_ids=node_ids, disabled=frozenset()
    ).clean:
        return None, []
    all_ids = frozenset(suspect_ids)
    steps: list[BisectStep] = []
    step = 0
    while len(window) > 1:
        step += 1
        half = window[: len(window) // 2]
        report = probe(
            store, ledger, strategist, baselines, node_ids=node_ids,
            disabled=all_ids - set(half),
        )
        if report.clean:
            window = window[len(window) // 2 :]  # this half is innocent in isolation
            verdict = "clean with only this half enabled — culprit in the remainder"
        else:
            window = half  # an alarm can only come from an enabled suspect
            verdict = "alarms with only this half enabled — culprit inside it"
        bstep = BisectStep(
            step=step,
            enabled=tuple(half),
            alarmed=not report.clean,
            window=tuple(window),
            reason=f"bisect step {step}: {verdict}; window narrowed to {len(window)}",
        )
        steps.append(bstep)
        emit(
            "BISECT",
            sim_time,
            step=step,
            enabled=[cid[:12] for cid in bstep.enabled],
            alarmed=bstep.alarmed,
            window=[cid[:12] for cid in bstep.window],
            reason=bstep.reason,
        )
    return window[0], steps
