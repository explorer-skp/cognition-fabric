"""The Jury — sortition, counterfactual replay, author-blind held-out, quorum certs (BLUEPRINT §5).

We never validate what an agent *says*; we validate what its capsule *does* — twice, with it and
without it, on scenarios the author has never seen. Both branches go through the one solve path
(`HeuristicStrategist.solve`, binding decision M3.1): "with capsule" is `solve(prior=rule)`,
"without" is `solve(prior=None)`, same seed — the measured delta is causal by construction.

Author-blindness (binding decision M3.2): each juror's held-out RNG is seeded from
`HMAC(juror_key, capsule_id)` using the juror's private key from `fabric/keyring.py`, and draws
HELDOUT_N parameter samples uniformly from the intersection of the capsule's declared context dims
and the class parameter space. Blindness rests on juror-private key material; the dev keyring
derives keys deterministically from identities (the documented stub seam, BLUEPRINT §13) — the
*mechanism* is the claim, and swapping in real PKI changes nothing here.

Everything is a pure function over data (CLAUDE.md): `select_jury`, `sample_episode`, the three
stage checks, and `validate_capsule` take data and return data plus one-line reason strings in the
fixed `"stage: detail"` format. An unexpected exception rejects with reason `internal_error` —
fail-secure, never admit.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import random
import statistics
from dataclasses import dataclass

from agents.strategist import HeuristicStrategist, SolveResult, Strategist
from fabric import keyring
from fabric.capsule import Capsule
from fabric.config import (
    CLAIM_TOL,
    CLASS_PARAM_SPACE,
    HELDOUT_N,
    HELDOUT_WIN,
    JURY_K,
    MIN_EFFECT,
    QUORUM,
)
from fabric.config import DEFAULT_ACTION
from fabric.registry import INVARIANTS
from world.cost import solve_cost
from world.scenarios import check_invariants
from world.taskgen import Task


# --- Sortition (§5.2) ---------------------------------------------------------

def select_jury(agent_ids: list[str], capsule_id: str, epoch: int, author: str) -> list[str]:
    """The k=JURY_K agents with the lowest `sha256(agent_id ‖ capsule_id ‖ epoch)`, author excluded.

    Deterministic (anyone can verify the committee), unpredictable before the capsule exists (its
    own content hash seeds the draw), and un-chooseable (the author never judges itself).
    # DECISION: '‖' is concatenation with ':' separators — unambiguous for these id shapes.
    """
    pool = [a for a in agent_ids if a != author]
    if len(pool) < JURY_K:
        raise ValueError(f"jury pool of {len(pool)} cannot seat {JURY_K} jurors")

    def draw(agent_id: str) -> str:
        return hashlib.sha256(f"{agent_id}:{capsule_id}:{epoch}".encode("utf-8")).hexdigest()

    return sorted(pool, key=draw)[:JURY_K]


# --- Episode sampling (§5.3, §5.4) ---------------------------------------------

def sample_episode(incident_class: str, dims: dict, seed: int) -> Task:
    """One deterministic replay episode from a seed: parameters drawn uniformly from the
    intersection of the declared context `dims` and the class parameter space.

    Shared by counterfactual replay (author's `evidence.scenario_seeds`) and held-out (juror-drawn
    seeds) — the same seed regenerates the same episode for any stranger, which is what makes
    claims replayable and cherry-picked seeds beatable by fresh ones.
    """
    space = CLASS_PARAM_SPACE[incident_class]
    rng = random.Random(seed)
    params: dict = {"incident_class": incident_class}
    for name in sorted(space):
        domain, declared = space[name], dims.get(name)
        if all(isinstance(x, str) for x in domain):
            allowed = sorted(set(declared) if declared else domain)
            params[name] = rng.choice(allowed)
        else:
            lo, hi = (float(declared[0]), float(declared[1])) if declared else (
                float(domain[0]),
                float(domain[1]),
            )
            value = rng.uniform(lo, hi)
            params[name] = int(value) if name == "device_count" else round(value, 3)
    episode_seed = rng.randrange(1, 2_000_000_000)
    return Task(
        task_id=f"replay-{incident_class}-{seed}",
        incident_class=incident_class,
        site_class=params["site_class"],
        params=params,
        arrival_sim=0.0,
        seed=episode_seed,
    )


# --- Measurement (decision M3.1: one solve path) --------------------------------

@dataclass(frozen=True)
class ReplayEpisode:
    """One with/without replay: the causal delta on the claim metric plus the with-capsule branch
    (whose episode metrics stage 5 scans for invariant hits)."""

    task: Task
    delta_pct: float
    with_result: SolveResult


def metric_value(result: SolveResult, metric: str) -> float:
    """The claim-metric reading of one solve: `solve_cost` folds in search toil; the raw episode
    KPIs read straight off the applied episode. All are cost-like — lower is better."""
    if metric == "solve_cost":
        return solve_cost(result.attempts, result.metrics)
    return float(getattr(result.metrics, metric))


def replay(task: Task, rule: dict, metric: str, strategist: Strategist) -> ReplayEpisode:
    """Run the episode twice from the same seed — baseline vs. capsule-as-prior — and measure the
    percentage delta on the claim metric. Same seed, same solve path: the delta is causal."""
    without = strategist.solve(task, prior=None)
    with_capsule = strategist.solve(task, prior=dict(rule))
    v0, v1 = metric_value(without, metric), metric_value(with_capsule, metric)
    # DECISION: a non-positive baseline reading means no improvement is demonstrable on this
    # episode — score it 0% (never a division blow-up, never a free pass).
    delta_pct = 0.0 if v0 <= 0 else (v1 - v0) / v0 * 100.0
    return ReplayEpisode(task=task, delta_pct=delta_pct, with_result=with_capsule)


# --- Pipeline stages 3–5 (§5) ---------------------------------------------------

def counterfactual_replay(
    capsule: Capsule, strategist: Strategist
) -> tuple[bool, str, list[ReplayEpisode]]:
    """Stage 3 — replay the author's own seeds; the claimed effect must reproduce within
    CLAIM_TOL. Kills: fabricated numbers."""
    episodes = [
        replay(
            sample_episode(capsule.context.incident_class, capsule.context.dims, seed),
            capsule.payload.rule,
            capsule.claim.metric,
            strategist,
        )
        for seed in capsule.evidence.scenario_seeds
    ]
    measured = statistics.median(e.delta_pct for e in episodes)
    required = capsule.claim.delta_pct * (1.0 - CLAIM_TOL)
    if measured > required:
        return (
            False,
            f"counterfactual replay: claimed {capsule.claim.delta_pct:+.1f}% but author-seed "
            f"median is {measured:+.1f}% (must reach {required:+.1f}% within tolerance)",
            episodes,
        )
    return True, f"counterfactual replay: author-seed median {measured:+.1f}% reproduces the claim", episodes


def heldout_replay(
    capsule: Capsule, juror_id: str, strategist: Strategist
) -> tuple[bool, str, list[ReplayEpisode], float]:
    """Stage 4 — author-blind held-out: HELDOUT_N fresh episodes from the juror's private seed
    stream (HMAC(juror_key, capsule_id), decision M3.2). Kills: cherry-picked/overfit claims."""
    digest = _hmac.new(
        keyring.key_for(juror_id), capsule.capsule_id.encode("utf-8"), hashlib.sha256
    ).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    episodes = [
        replay(
            sample_episode(
                capsule.context.incident_class,
                capsule.context.dims,
                rng.randrange(1, 2_000_000_000),
            ),
            capsule.payload.rule,
            capsule.claim.metric,
            strategist,
        )
        for _ in range(HELDOUT_N)
    ]
    measured = statistics.median(e.delta_pct for e in episodes)
    wins = sum(1 for e in episodes if e.delta_pct < 0)
    required = -MIN_EFFECT * 100.0
    if measured > required or wins < HELDOUT_WIN:
        return (
            False,
            f"author-blind held-out: median {measured:+.1f}% with improvement in "
            f"{wins}/{HELDOUT_N} episodes (need median ≤ {required:+.1f}% and ≥ {HELDOUT_WIN} wins)",
            episodes,
            measured,
        )
    return (
        True,
        f"author-blind held-out: median {measured:+.1f}%, improvement in {wins}/{HELDOUT_N} episodes",
        episodes,
        measured,
    )


def invariant_conformance(capsule: Capsule, episodes: list[ReplayEpisode]) -> tuple[bool, str]:
    """Stage 5 — every replayed with-capsule episode is checked against all registry invariants and
    the capsule's `conformance_required` tests; one violation anywhere rejects.
    Kills: true-but-unsafe optimizations."""
    for name in capsule.evidence.conformance_required:
        if name not in INVARIANTS:
            return False, f"invariant/conformance: unknown conformance test {name!r} — not in the constitution"
    # DECISION: the *declared* rule is the contract — check it (merged over the safe DEFAULT_ACTION,
    # exactly the action the solve path starts from) against every episode's context. Refinement may
    # happen to patch an unsafe rule live, but a capsule whose payload as written violates the
    # constitution anywhere in its declared context is unsafe knowledge and dies here.
    rule_action = {**DEFAULT_ACTION, **capsule.payload.rule}
    for episode in episodes:
        violated = check_invariants(
            rule_action, episode.task.incident_class, episode.task.site_class
        )
        if violated:
            return (
                False,
                f"invariant/conformance: rule as declared violates {violated[0]!r} at "
                f"site_class {episode.task.site_class!r} (episode {episode.task.task_id})",
            )
        hits = episode.with_result.metrics.invariant_hits
        if hits > 0:
            return (
                False,
                f"invariant/conformance: episode {episode.task.task_id} registers {hits} "
                f"invariant hit(s) under the capsule rule — one violation anywhere rejects",
            )
    return True, "invariant/conformance: zero invariant hits across all replayed episodes"


# --- Verdicts and quorum certificates (§5.6, decision M3.4) ----------------------

@dataclass(frozen=True)
class JurorVerdict:
    """One juror's signed verdict: the signature covers exactly
    `{capsule_id, verdict, measured_delta, partition_view}` (binding decision M3.4)."""

    juror: str
    verdict: str  # "ACCEPT" | "REJECT"
    measured_delta: float
    partition_view: str
    sig: str
    reason: str

    def signed_payload(self, capsule_id: str) -> bytes:
        return vote_payload(capsule_id, self.verdict, self.measured_delta, self.partition_view)


def vote_payload(capsule_id: str, verdict: str, measured_delta: float, partition_view: str) -> bytes:
    """Canonical signed bytes of one vote — the verification interface: anyone holding the quorum
    cert can recompute this payload and check each juror's signature against it."""
    body = {
        "capsule_id": capsule_id,
        "verdict": verdict,
        "measured_delta": measured_delta,
        "partition_view": partition_view,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def juror_verdict(
    capsule: Capsule, juror_id: str, agent_ids: list[str], strategist: Strategist,
    partition_view: str | None = None,
) -> JurorVerdict:
    """One juror's full pass over stages 3–5. `measured_delta` is the juror's held-out median (its
    own independent measurement). `partition_view` is the juror's actual connectivity view (binding
    decision M3.4, filled in at M6): the sorted `|`-joined reachable-agent set at cert time. Defaults
    to the sorted full agent set when the caller has no partition (unchanged M3-M5 behavior)."""
    partition_view = partition_view if partition_view is not None else "|".join(sorted(agent_ids))
    measured_delta = 0.0
    ok, reason, cf_episodes = counterfactual_replay(capsule, strategist)
    episodes = cf_episodes
    if ok:
        ok, reason, ho_episodes, measured_delta = heldout_replay(capsule, juror_id, strategist)
        episodes = cf_episodes + ho_episodes
    if ok:
        ok, reason = invariant_conformance(capsule, episodes)
    verdict = "ACCEPT" if ok else "REJECT"
    measured_delta = round(measured_delta, 4)
    sig = keyring.sign(
        juror_id, vote_payload(capsule.capsule_id, verdict, measured_delta, partition_view)
    )
    return JurorVerdict(
        juror=juror_id,
        verdict=verdict,
        measured_delta=measured_delta,
        partition_view=partition_view,
        sig=sig,
        reason=reason,
    )


@dataclass(frozen=True)
class JuryOutcome:
    """The jury's decision: `quorum_cert` is present iff ≥ QUORUM of JURY_K jurors accepted. The
    cert is lifecycle metadata (stored via the M2 store API) — never in the hashed body."""

    accepted: bool
    jurors: list[str]
    verdicts: list[JurorVerdict]
    quorum_cert: dict | None
    reason: str


def validate_capsule(
    capsule: Capsule,
    agent_ids: list[str],
    strategist: Strategist | None = None,
    sim_time: float = 0.0,
    partition_view: str | None = None,
) -> JuryOutcome:
    """The full jury pass: sortition, per-juror stages 3–5, quorum certificate (§5.2–§5.6).

    `partition_view` (BLUEPRINT §7.5, milestone M6): the reachable-agent view at cert time, if the
    jury is convening during a partition — carried into every juror's vote and the cert. `None`
    (the default) means no partition — the full mesh, unchanged M3-M5 behavior.
    """
    try:
        strategist = strategist or HeuristicStrategist()
        jurors = select_jury(
            agent_ids, capsule.capsule_id, capsule.provenance.author_epoch, capsule.provenance.author
        )
        verdicts = [juror_verdict(capsule, j, agent_ids, strategist, partition_view) for j in jurors]
        accepts = sum(1 for v in verdicts if v.verdict == "ACCEPT")
        if accepts >= QUORUM:
            cert = {
                "jurors": jurors,
                "votes": [
                    {
                        "juror": v.juror,
                        "verdict": v.verdict,
                        "measured_delta": v.measured_delta,
                        "sig": v.sig,
                    }
                    for v in verdicts
                ],
                "partition_view": verdicts[0].partition_view,
                "sim_time": round(float(sim_time), 4),
            }
            return JuryOutcome(
                accepted=True,
                jurors=jurors,
                verdicts=verdicts,
                quorum_cert=cert,
                reason=f"jury: quorum {accepts}/{JURY_K} accept",
            )
        first_reject = next(v for v in verdicts if v.verdict == "REJECT")
        return JuryOutcome(
            accepted=False,
            jurors=jurors,
            verdicts=verdicts,
            quorum_cert=None,
            reason=f"jury quorum {accepts}/{JURY_K}: {first_reject.reason}",
        )
    except Exception as exc:  # fail-secure: never admit on an unexpected error (CLAUDE.md)
        return JuryOutcome(
            accepted=False,
            jurors=[],
            verdicts=[],
            quorum_cert=None,
            reason=f"internal_error: unexpected {type(exc).__name__} during jury validation",
        )
