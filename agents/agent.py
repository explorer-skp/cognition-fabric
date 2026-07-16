"""Site agents and the task loops (BLUEPRINT §8, milestones M1 + M4).

An agent receives a TASK, solves it, measures the cost, and emits a SOLVE event. Even with the
fabric off, the agent enforces its own constitution locally: adoption-as-prior means a capsule can
only ever be a starting point — it can never make an agent apply an action that violates an invariant
(BLUEPRINT §4).

* `Agent` + `run_baseline_storm` — the M1 baseline (fabric OFF). `prior` is always None, every task is
  a cold start, per-class costs stay high and flat. This is **Lane B** of the M4 twin-lane A/B and
  must never change (its event stream is the controlled experiment's control).

* `FabricAgent` + `run_fabric_storm` — the M4 fabric-ON path (**Lane A**): query the local store for
  an ACTIVE capsule matching the task (fabric-query-before-solve), reuse it as a prior when found,
  else discover and — once enough evidence accumulates — author a capsule that flows through Pawl +
  Jury, push-gossips as CANDIDATE, and is promoted *mesh-wide* by derived quorum over replicated
  shadow records (binding decision M4.2). `run_twin_lane` runs both lanes on one seeded stream.
"""

from __future__ import annotations

import asyncio
import hashlib
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from agents.strategist import HeuristicStrategist, SolveResult, Strategist
from fabric.arbitration import active_matches, applies, arbitrate
from fabric.capsule import (
    Claim,
    Context,
    Evidence,
    Lifecycle,
    LifecycleState,
    Payload,
    Provenance,
    build_capsule,
)
from fabric.config import (
    AGENTS,
    AUTHOR_MIN_EFFECT,
    AUTHOR_MIN_EPISODES,
    CLASS_PARAM_SPACE,
    DEFAULT_ACTION,
    GOSSIP_PERIOD,
    RATE_WINDOW_S,
    REGISTRY_VERSION,
    STORM_SIZE,
)
from fabric.gossip import (
    ShadowLedger,
    apply_push,
    build_push,
    derive_state,
    reconcile,
    sign_shadow_record,
    verify_push,
)
from fabric.lifecycle import ShadowTracker, shadow_step, submit
from fabric.pawl import PawlContext
from fabric.jury import replay, sample_episode
from fabric.store import Store
from world.bus import Bus, Message
from world.cost import solve_cost
from world.scenarios import check_invariants, relevant_dims, simulate
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
    seed: int,
    n: int = STORM_SIZE,
    events: EventStream | None = None,
    tasks: list[Task] | None = None,
) -> EventStream:
    """Drive `n` seeded tasks through the 5-agent mesh over the deterministic bus (fabric OFF).

    Tasks are assigned round-robin across agents; delivery is ordered by (arrival_sim, seq), so the
    whole storm is replayable byte-for-byte. Returns the EventStream it wrote to.

    `tasks` defaults to `generate(seed, n)` (the M1 behavior, byte-for-byte). It exists only so the
    M4 twin-lane can drive Lane B over the *same* injected stream as Lane A; with `tasks=None` the
    code path and output are identical to M1 — the baseline is still the controlled experiment's
    control.
    """
    events = events or EventStream()
    tasks = tasks if tasks is not None else generate(seed, n)
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

    for i, task in enumerate(tasks):
        assignee = AGENTS[i % len(AGENTS)][0]
        bus.publish(
            "TASK",
            Message("TASK", "world", task.arrival_sim, {"task": task, "assignee": assignee}),
            at=task.arrival_sim,
        )

    asyncio.run(bus.run_until_empty())
    return events


# =============================================================================
# M4 — the fabric-ON agent (Lane A): reuse, authoring, mesh-wide shadow, gossip.
# =============================================================================


def _impact(metrics) -> float:
    """Episode impact only (search effort excluded) — the signal for ranking discovered actions."""
    return solve_cost(0, metrics)


def _observed_dims(incident_class: str, tasks: list[Task]) -> dict:
    """Declared context from evidence: per-dim [min, max] over the class's numeric scenario dims plus
    the observed `site_class` set (binding decision M4.1 — never a wildcard)."""
    space = CLASS_PARAM_SPACE[incident_class]
    dims: dict = {}
    for name, domain in sorted(space.items()):
        values = [t.params[name] for t in tasks]
        if all(isinstance(x, str) for x in domain):
            dims[name] = sorted(set(values))
        else:
            lo, hi = min(values), max(values)
            dims[name] = [lo, hi]
    return dims


@dataclass
class FabricAgent:
    """A site agent running with the fabric ON (BLUEPRINT §8, milestone M4).

    Holds its own OR-set `store` and `ShadowLedger`, its per-class discovery memory, and references
    to its `peers` for eager promotion push. All state is node-local; nothing about ACTIVE is ever
    written to meta or gossiped — a capsule is ACTIVE exactly when this node *derives* it so from the
    replicated shadow records (binding decision M4.2).
    """

    agent_id: str
    site_class: str
    strategist: Strategist
    events: EventStream
    agent_ids: list[str]
    node_ids: set[str]
    reputation: float = 1.0
    epoch: int = 41
    peers: list["FabricAgent"] = field(default_factory=list)
    store: Store = field(default_factory=Store)
    ledger: ShadowLedger = field(default_factory=ShadowLedger)

    def __post_init__(self) -> None:
        self.identity = f"agent:{self.agent_id}"
        self._memory: dict[str, list[tuple[Task, SolveResult]]] = defaultdict(list)
        self._best: dict[str, tuple[dict, float]] = {}
        self._authored: set[str] = set()  # classes this node has attempted to author (base capsules)
        self._authored_derived: set[tuple[str, str]] = set()  # (class, prior_id) pairs
        self._derived_evidence: dict[tuple[str, str], list[Task]] = defaultdict(list)
        self._promoted_local: set[str] = set()  # capsule_ids already evented PROMOTED here
        self._submissions: list[float] = []  # sim-times of this node's submissions (rate window)

    # --- event helpers -------------------------------------------------------
    def _submit_emit(self, event_type: str, sim_time: float, **fields: object) -> None:
        """Emitter handed to `submit()` so PAWL_BLOCK / JURY_VERDICT carry this node's identity."""
        self.events.emit(event_type, sim_time, agent=self.identity, **fields)

    # --- the task loop -------------------------------------------------------
    def handle_task(self, task: Task, sim_time: float) -> None:
        """Fabric-query-before-solve: reuse an ACTIVE match as a prior, else discover; then shadow any
        local CANDIDATEs against this task and surface any newly-derived promotions."""
        matches = active_matches(self.store, self.ledger, task, self.node_ids)
        winner = arbitrate(matches)
        if winner is not None:
            self._reuse(task, winner, sim_time)
        else:
            self._discover(task, sim_time)
        self._shadow_candidates(task, sim_time)
        self._emit_promotions(sim_time)

    def _apply_and_cost(self, task: Task, result: SolveResult) -> float:
        """Local constitution enforcement (fail-secure, adoption-as-prior) + the realized cost."""
        violations = check_invariants(result.action, task.incident_class, task.site_class)
        if violations:
            raise AssertionError(
                f"{self.identity} would apply an action violating {violations} on {task.task_id}"
            )
        return solve_cost(result.attempts, result.metrics)

    def _discover(self, task: Task, sim_time: float) -> None:
        result = self.strategist.solve(task, prior=None)
        cost = self._apply_and_cost(task, result)
        self.events.emit(
            "SOLVE",
            sim_time=sim_time,
            agent=self.identity,
            task_id=task.task_id,
            incident_class=task.incident_class,
            site_class=task.site_class,
            attempts=result.attempts,
            solve_cost=cost,
            invariant_hits=result.metrics.invariant_hits,
            reused=False,
        )
        self._record_discovery(task, result)
        self._maybe_author(task.incident_class, sim_time)

    def _reuse(self, task: Task, winner, sim_time: float) -> None:
        prior_rule = dict(winner.capsule.payload.rule)
        result = self.strategist.solve(task, prior=prior_rule)
        cost = self._apply_and_cost(task, result)
        self.events.emit(
            "REUSE",
            sim_time=sim_time,
            agent=self.identity,
            task_id=task.task_id,
            incident_class=task.incident_class,
            site_class=task.site_class,
            attempts=result.attempts,
            solve_cost=cost,
            invariant_hits=result.metrics.invariant_hits,
            reused=True,
            capsule_id=winner.capsule.capsule_id,
        )
        self._maybe_author_derived(task, winner.capsule, result, sim_time)

    # --- discovery memory ----------------------------------------------------
    def _record_discovery(self, task: Task, result: SolveResult) -> None:
        cls = task.incident_class
        self._memory[cls].append((task, result))
        impact = _impact(result.metrics)
        best = self._best.get(cls)
        if best is None or impact < best[1]:
            self._best[cls] = (dict(result.action), impact)

    # --- authoring (binding decision M4.1) -----------------------------------
    def _evidence_seeds(self, cls: str, tag: str) -> list[int]:
        """A deterministic per-(node, class, epoch, tag) seed stream for the author's own claim
        replay — distinct across agents so authors never collide on evidence."""
        base = int(
            hashlib.sha256(f"{self.identity}:{cls}:{self.epoch}:{tag}".encode("utf-8")).hexdigest(),
            16,
        ) % 1_000_000_000
        return [base + i for i in range(AUTHOR_MIN_EPISODES)]

    def _maybe_author(self, cls: str, sim_time: float) -> None:
        if cls in self._authored or len(self._memory[cls]) < AUTHOR_MIN_EPISODES:
            return
        self._authored.add(cls)  # one base-authoring attempt per class per node (no churn)
        window = [t for t, _r in self._memory[cls][-AUTHOR_MIN_EPISODES:]]
        best_action = self._best[cls][0]
        rule = {d: best_action[d] for d in relevant_dims(cls)}
        dims = _observed_dims(cls, window)
        self._author(cls, rule, dims, self._evidence_seeds(cls, "base"), sim_time, derived_from=[])

    def _maybe_author_derived(self, task: Task, prior, result: SolveResult, sim_time: float) -> None:
        """Decision M4.1: if a reuse-solve's refinement beats its prior by ≥ AUTHOR_MIN_EFFECT,
        author a derived capsule (provenance.derived_from = [prior_id]) — M5 needs organic descendants."""
        cls = task.incident_class
        key = (cls, prior.capsule_id)
        if key in self._authored_derived:
            return
        # "Beats its prior" compares the refined action to the prior action on outcome quality
        # (episode impact, search effort excluded) — a derived capsule captures a *better rule*, not
        # a cheaper search. Same seed both sides, so the delta is causal.
        prior_rule = {**DEFAULT_ACTION, **prior.payload.rule}
        prior_impact = _impact(simulate(task.params, prior_rule, task.seed))
        refined_impact = _impact(result.metrics)
        if prior_impact <= 0 or (prior_impact - refined_impact) / prior_impact < AUTHOR_MIN_EFFECT:
            return
        self._derived_evidence[key].append(task)
        if len(self._derived_evidence[key]) < AUTHOR_MIN_EPISODES:
            return
        self._authored_derived.add(key)
        window = self._derived_evidence[key][-AUTHOR_MIN_EPISODES:]
        rule = {d: result.action[d] for d in relevant_dims(cls)}
        dims = _observed_dims(cls, window)
        self._author(
            cls, rule, dims, self._evidence_seeds(cls, f"derived:{prior.capsule_id}"), sim_time,
            derived_from=[prior.capsule_id],
        )

    def _author(
        self,
        cls: str,
        rule: dict,
        dims: dict,
        evidence_seeds: list[int],
        sim_time: float,
        *,
        derived_from: list[str],
    ) -> None:
        """Measure the claim by self-replay through the one solve path, and if the median improvement
        clears AUTHOR_MIN_EFFECT, build + submit the capsule and (on CANDIDATE) push-gossip it."""
        episodes = [
            replay(sample_episode(cls, dims, seed), rule, "solve_cost", self.strategist)
            for seed in evidence_seeds
        ]
        median_delta = statistics.median(e.delta_pct for e in episodes)
        if median_delta > -AUTHOR_MIN_EFFECT * 100.0:
            return  # improvement below the (stricter-than-jury) authoring bar
        baseline = 30.0  # illustrative absolute median; the falsifiable number is delta_pct
        capsule = build_capsule(
            kind="mitigation_rule",
            registry_version=REGISTRY_VERSION,
            context=Context(incident_class=cls, dims=dims),
            payload=Payload(rule=rule),
            claim=Claim(
                metric="solve_cost",
                baseline_median=baseline,
                with_capsule_median=round(baseline * (1 + median_delta / 100.0), 4),
                delta_pct=round(median_delta, 1),
                n_episodes=len(evidence_seeds),
            ),
            evidence=Evidence(
                scenario_seeds=list(evidence_seeds),
                conformance_required=[
                    "no_flagged_flow_bypasses_inspection",
                    "quarantine_reversible",
                ],
                trace_digest="0" * 64,
            ),
            provenance=Provenance(
                author=self.identity, author_epoch=self.epoch, derived_from=list(derived_from)
            ),
            lifecycle=Lifecycle(state=LifecycleState.DRAFT, created_at_sim=sim_time),
        )
        self.epoch += 1
        self.events.emit(
            "AUTHOR",
            sim_time=sim_time,
            agent=self.identity,
            capsule_id=capsule.capsule_id,
            incident_class=cls,
            delta_pct=round(median_delta, 1),
            derived_from=list(derived_from),
        )
        pawl_ctx = PawlContext(
            reputation=self.reputation,
            submissions_in_window=self._submissions_in_window(sim_time),
        )
        self._submissions.append(sim_time)
        state, _reason = submit(
            capsule,
            self.store,
            self.agent_ids,
            sim_time,
            pawl_ctx=pawl_ctx,
            strategist=self.strategist,
            emit=self._submit_emit,
        )
        if state == LifecycleState.CANDIDATE:
            cert = self.store.lifecycle_of(capsule.capsule_id)["quorum_cert"]
            push = build_push(capsule, cert)
            for peer in self.peers:
                peer.receive_push(push, sim_time)

    def _submissions_in_window(self, sim_time: float) -> int:
        return sum(1 for t in self._submissions if sim_time - t <= RATE_WINDOW_S)

    # --- mesh-wide shadow (binding decision M4.2) ----------------------------
    def _shadow_candidates(self, task: Task, sim_time: float) -> None:
        """Run M3's `shadow_step` for every local CANDIDATE this task matches, and append a signed
        SHADOW_RECORD to the ledger. The candidate influences nothing — this is evaluation only."""
        for cid in sorted(self.store.live_ids()):
            capsule = self.store.get(cid)
            if capsule is None:
                continue
            derived = derive_state(self.store, self.ledger, cid, self.node_ids)
            if derived.state != LifecycleState.CANDIDATE or not applies(capsule, task):
                continue
            tracker = shadow_step(capsule, task, self.strategist, ShadowTracker())
            record = sign_shadow_record(
                self.identity,
                cid,
                task.seed,
                task.incident_class,
                task.params,
                win=tracker.wins == 1,
                invariant_hits=tracker.invariant_hits,
                sim_time=sim_time,
            )
            self.ledger.add(record)

    def _emit_promotions(self, sim_time: float) -> None:
        """Emit PROMOTED once, locally, the first time this node derives a capsule ACTIVE — the
        observable marker of mesh-wide promotion (insight-lead-time's terminal event)."""
        for cid in sorted(self.store.live_ids()):
            if cid in self._promoted_local:
                continue
            capsule = self.store.get(cid)
            if capsule is None:
                continue
            derived = derive_state(self.store, self.ledger, cid, self.node_ids)
            if derived.state == LifecycleState.ACTIVE:
                self._promoted_local.add(cid)
                self.events.emit(
                    "PROMOTED",
                    sim_time=sim_time,
                    agent=self.identity,
                    capsule_id=cid,
                    confidence=derived.confidence,
                    incident_class=capsule.context.incident_class,
                )

    # --- gossip receive ------------------------------------------------------
    def receive_push(self, push: dict, sim_time: float) -> None:
        """Handle a GOSSIP_PUSH: verify every signature, then store CANDIDATE locally. Fail-secure —
        an unverifiable push is dropped, never admitted (gossiped state is never authority)."""
        ok, _reason = verify_push(push, self.node_ids)
        if not ok:
            return
        apply_push(self.store, push, sim_time)


def _all_pairs_reconcile(agents: list[FabricAgent]) -> None:
    """One anti-entropy round: reconcile every pair of nodes so records (capsules, tombstones, metas,
    shadow records) converge across the whole mesh (GOSSIP_DIGEST → GOSSIP_PULL)."""
    for i in range(len(agents)):
        for j in range(i + 1, len(agents)):
            reconcile((agents[i].store, agents[i].ledger), (agents[j].store, agents[j].ledger))


def run_fabric_storm(
    seed: int,
    n: int = STORM_SIZE,
    events: EventStream | None = None,
    tasks: list[Task] | None = None,
) -> EventStream:
    """Lane A: drive the seeded task stream through the fabric-ON mesh (BLUEPRINT §8, §2, M4).

    Round-robin assignment identical to the baseline; anti-entropy runs every GOSSIP_PERIOD sim-s.
    Deterministic by construction (seeded strategist, sortition, gossip over sorted ids).

    # DECISION: Lane A is a sequential in-process orchestrator — gossip (PUSH/DIGEST/PULL) is
    # delivered by direct verified calls rather than the async bus. Transport is simulated (§13);
    # the gossip *algorithms* (verify-then-store, derived promotion, anti-entropy) are real and
    # unit-tested, and would ride the bus in a networked deployment. Lane B keeps the bus (baseline).
    """
    events = events or EventStream()
    tasks = tasks if tasks is not None else generate(seed, n)
    identities = [f"agent:{aid}" for aid, _sc in AGENTS]
    node_ids = set(identities)
    agents = [
        FabricAgent(
            agent_id=aid,
            site_class=sc,
            strategist=HeuristicStrategist(),
            events=events,
            agent_ids=identities,
            node_ids=node_ids,
        )
        for aid, sc in AGENTS
    ]
    for agent in agents:
        agent.peers = [p for p in agents if p is not agent]

    last_gossip = 0.0
    for i, task in enumerate(tasks):
        while task.arrival_sim - last_gossip >= GOSSIP_PERIOD:
            last_gossip += GOSSIP_PERIOD
            _all_pairs_reconcile(agents)
            for agent in agents:
                agent._emit_promotions(last_gossip)
        assignee = agents[i % len(agents)]
        events.emit(
            "TASK",
            sim_time=task.arrival_sim,
            task_id=task.task_id,
            incident_class=task.incident_class,
            site_class=task.site_class,
            assignee=assignee.identity,
        )
        assignee.handle_task(task, task.arrival_sim)

    # Final anti-entropy so every node converges and any last promotion is derived + evented.
    final_time = tasks[-1].arrival_sim if tasks else 0.0
    _all_pairs_reconcile(agents)
    for agent in agents:
        agent._emit_promotions(final_time)
    return events


def run_twin_lane(
    seed: int, n: int = STORM_SIZE, tasks: list[Task] | None = None
) -> tuple[EventStream, EventStream]:
    """The twin-lane A/B controlled experiment (BLUEPRINT §8): the *same* seeded task stream through
    Lane A (fabric ON) and Lane B (fabric OFF ≡ the M1 baseline). Returns (lane_a, lane_b).

    Both lanes are driven over the identical `tasks` (default `generate(seed, n)`). With `tasks=None`,
    Lane B is byte-identical to a standalone `run_baseline_storm(seed, n)` — the controlled
    experiment's control lane *is* the M1 baseline, by construction.
    """
    tasks = tasks if tasks is not None else generate(seed, n)
    lane_a = run_fabric_storm(seed, n, events=EventStream(), tasks=tasks)
    lane_b = run_baseline_storm(seed, n, events=EventStream(), tasks=tasks)
    return lane_a, lane_b
