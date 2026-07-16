# Cognition Fabric — Phase 2 Blueprint

**Team Beacon · Code With Cisco 2026 · PS-1 Phase 2: The Continuous Mesh & The Ratchet Effect**

This document is the single source of truth for the Phase 2 prototype. It is written to be executed
milestone-by-milestone (§10). Names defined here (Capsule, Pawl, Jury, Excision, Sentinel,
Refine) are part of the live defence — do not rename them in code.

Companion docs: `docs/DEFENCE.md` (why every choice is defensible) and `docs/DEMO_RUNBOOK.md` (the
10–15 min show this code must deliver).

---

## 0. Traceability matrix — read this first

Every Phase 2 requirement maps to a named component and a visible demo moment. No loose ends.

| PS requirement                                                | Component                                                                                                                         | Demo moment                                                                        | Code home                               |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------- |
| 1. Dynamic flow of enterprise tasks under changing conditions | TaskGen (Poisson arrivals, drifting incident mix + parameter drift)                                                               | Incident ticker running throughout                                                 | `world/taskgen.py`                      |
| 2. Fabric layer capturing a localized breakthrough            | Capsule store: content-addressed, signed, CRDT OR-set replicated by gossip; per-node persistence                                  | Site-A authors capsule; visible in Fabric panel                                    | `fabric/store.py`, `fabric/gossip.py`   |
| 3. Accelerator propagating a _verified_ insight               | Validation pipeline (Pawl → Jury → shadow) + push-gossip on promotion; measured as "insight lead time"                            | Capsule goes CANDIDATE→ACTIVE, appears at all 5 sites in seconds                   | `fabric/jury.py`, `fabric/lifecycle.py` |
| 4. Autonomous Guardrail before acceptance                     | **The Pawl** — pre-admission policy engine (ratchet monotonicity, invariants, scope bounds, identity, rate)                       | Rogue capsule blocked live with reason string                                      | `fabric/pawl.py`                        |
| 5. Visible reuse / ratchet effect                             | Ratchet staircase metric (best-known cost per incident class, monotone non-increasing) + reuse events + agent restart-with-memory | Sites B–E solve repeat incidents at reuse cost; killed agent rejoins and reuses    | `ui/tui.py`, `agents/agent.py`          |
| Bonus: Chaos Injector                                         | Fault library: poison (blatant + subtle), partition, node-crash, gossip flap                                                      | Chaos segment of demo                                                              | `chaos/injector.py`                     |
| Dilemma A: innovation vs hallucination                        | Counterfactual replay + author-blind held-out + sortition Jury + quorum cert                                                      | Validation panel shows with/without deltas                                         | §5                                      |
| Dilemma B: drift & poisoning                                  | Layered immune system: Pawl, blast-radius scoping, shadow staging, Sentinel probes, provenance bisect, **Excision** (never reset) | Subtle poison caught post-hoc, surgically excised; capsule count drops 2, not to 0 | §6                                      |
| Dilemma C: consistency without split-brain                    | Three-layer consistency: CRDT storage / context-scoped meaning / deterministic pure-function decisions; **Refine** on overlap     | Partition-heal segment: two truths survive as two contexts                         | §7                                      |

---

## 1. Phase 1 primer — what this builds on (do not reinvent)

Phase 1 delivered the Cognition State Protocol (CSP): two agents with opposing goals reach a signed,
bounded **contract** with no coordinator. The pieces Phase 2 reuses verbatim:

- **Registry** of typed operational dimensions (`inspection_depth`, `added_latency_ms`,
  `sampled_fraction`, …), versioned, each dimension carrying a unit and a **conformance test**.
  Phase 2 adds incident-domain dimensions (§8) to the same registry structure.
- **Priority lattice**: `SAFETY > COMPLIANCE > SLO > EFFICIENCY`, lexicographic — no efficiency weight
  can buy out a safety constraint.
- **Invariants**: hard predicates no agreement (now: no capsule) may violate.
- **arbitrate()** — the pure deterministic conflict function (priority class → weighted midpoint →
  hash tie-break). Port it as `fabric/arbitration.py`. The same function that settled Phase 1
  negotiations settles Phase 2 fabric conflicts. This continuity is a headline defence point.
- **Signed agent identities, epochs, append-only hash-chained audit log, reputation** — the trust
  substrate for propagation.
- **Cognition capsule** — designed in Phase 1 as the Phase-2 seam: a signed, content-addressed
  artifact with an applicability predicate, provenance, confidence, TTL, revocation pointer.
  Phase 2 is that seam, implemented.

Phase 1 slogan: _contracts, not conversations._ Phase 2 slogan: _evidence, not claims._

---

## 2. Concepts and vocabulary

- **Capsule** — the unit of collective memory: a validated decision rule with its evidence, scope, and
  lifecycle. Never free text; always typed over registry dimensions.
- **Context** — an applicability predicate: `{incident_class, dim → interval/set}`. The unit of
  consistency and of blast radius.
- **Fabric** — the replicated capsule store: content-addressed DAG, OR-set add/tombstone semantics,
  gossip anti-entropy, per-node JSONL persistence.
- **Accelerator** — the path from local discovery to network-wide availability: Pawl → Jury →
  CANDIDATE (shadow) → ACTIVE → push-gossip. Measured as **insight lead time**.
- **The Pawl** — the autonomous guardrail. A ratchet without a pawl spins backward; ours is the pawl:
  it structurally prevents the fabric from ever ratcheting _toward_ less safety.
- **Jury** — k validators chosen by hash sortition, who re-execute the claim rather than read it.
- **Sentinel probes** — periodic replay of a pinned golden scenario suite against the current ACTIVE
  set; the fabric's regression tests. Memory has CI.
- **Excision** — revocation as surgery: tombstone the culprit, transitively quarantine its
  descendants, slash reputations. Never reset.
- **Refine** — conflict resolution by predicate splitting: a persistent conflict between two valid
  capsules is treated as an underspecified context, and the context is sharpened.
- **Ratchet staircase** — per incident class, best-known solve cost so far. Monotone non-increasing
  by construction. The staircase chart _is_ requirement 5, visualized.

---

## 3. The Capsule schema (exact — field names are part of the defence)

```json
{
  "capsule_id": "sha256 of canonical body (content-addressed)",
  "kind": "mitigation_rule",
  "registry_version": "3.2",
  "context": {
    "incident_class": "ddos_syn_flood",
    "dims": { "traffic_gbps": [1.0, 10.0], "site_class": ["branch"] }
  },
  "payload": {
    "rule": {
      "set": {
        "rate_limit_pps": 8000,
        "inspection_depth": 3,
        "quarantine_scope": "flagged_only"
      }
    }
  },
  "claim": {
    "metric": "solve_cost",
    "baseline_median": 74.0,
    "with_capsule_median": 22.0,
    "delta_pct": -70.3,
    "n_episodes": 6
  },
  "evidence": {
    "scenario_seeds": [90211, 90214, 90218, 90223, 90230, 90231],
    "conformance_required": [
      "no_flagged_flow_bypasses_inspection",
      "quarantine_reversible"
    ],
    "trace_digest": "sha256 of the author's episode traces"
  },
  "provenance": {
    "author": "agent:site-a",
    "author_epoch": 41,
    "derived_from": [],
    "born_of_contract": null
  },
  "lifecycle": {
    "state": "SUBMITTED",
    "quorum_cert": null,
    "confidence": 0.0,
    "created_at_sim": 132.5,
    "ttl_sim": 600.0
  },
  "sig": "author signature over canonical body"
}
```

Field rationale (one line each, keep in docstrings):

- `capsule_id` content-addressed → dedup for free, tamper-evident, gossip by digest.
- `context.dims` → intervals over registry dimensions only; wildcard contexts are rejected by the Pawl
  (blast-radius bound).
- `payload.rule` → a _typed action_, never code, never text. The Pawl can reason about it mechanically.
- `claim` → the falsifiable statement. A capsule without a falsifiable claim is rejected at schema.
- `evidence.scenario_seeds` → what makes the claim _replayable_ by strangers. Proof-carrying capsules.
- `provenance.derived_from` → the DAG edges that make Excision surgical and bisect possible.
- `lifecycle.quorum_cert` → `{jurors: [...], votes: [...], partition_view: "...", sim_time}` — signed.
- Signing in the prototype: HMAC with per-agent keys from a local keyring (stub for real PKI; same
  interface — say so honestly, see §13).

---

## 4. Capsule lifecycle state machine

```
DRAFT ──submit──▶ SUBMITTED ──Pawl fail──▶ REJECTED(reason)
                     │ Pawl pass
                     ▼
                   JURY ──quorum fail──▶ REJECTED(evidence)
                     │ quorum cert (2 of 3)
                     ▼
                CANDIDATE (shadow mode: evaluated, never applied)
                     │ mesh-shadow quorum met (derived locally)       │ shadow fail
                     ▼                                                ▼
                  ACTIVE ──superseded_by──▶ SUPERSEDED           REJECTED
                     │
                     ├─ TTL expiry ──▶ EXPIRED (still readable, not applied)
                     ├─ Sentinel/bisect verdict ──▶ REVOKED (tombstone, transitive quarantine of descendants)
                     └─ descendant of a REVOKED capsule ──▶ QUARANTINED ──re-jury without poisoned evidence──▶ CANDIDATE | REJECTED
```

Rules:

- Only ACTIVE capsules influence live decisions. CANDIDATE influences nothing (shadow only).
- Adoption is **as prior, never override**: an agent applying a capsule still enforces its own
  invariants locally. A capsule cannot make an agent violate its constitution. (Phase 1 §8 rule,
  now enforced in `agents/agent.py`.)
- REVOKED is a tombstone in the OR-set: it replicates like any record. Memory of the mistake is
  itself retained — auditors can see what was believed, when, and why it was excised.

---

## 5. Dilemma A — Innovation vs. Hallucination: the validation pipeline

**Design stance:** we never validate what an agent _says_; we validate what its capsule _does_ — twice,
with it and without it, on scenarios the author has never seen. A hallucination can survive a
conversation; it cannot survive execution.

Pipeline (all in `fabric/jury.py` + `fabric/pawl.py`, pure functions, unit-tested):

1. **Pawl static checks** (§6.1) — schema, signature, registry conformance, ratchet monotonicity,
   bounded context, rate/reputation. Cheap, autonomous, pre-everything.
2. **Jury sortition** — jurors = the k=3 agents with the lowest
   `sha256(agent_id ‖ capsule_id ‖ epoch)`, author excluded. Deterministic (anyone can verify the
   committee was correct), unpredictable before the capsule exists (the capsule's own hash seeds it),
   and un-chooseable (an author cannot arrange to judge itself).
3. **Counterfactual replay, author seeds** — for each seed in `evidence.scenario_seeds`, each juror
   runs the scenario twice from the same seed: baseline policy vs. capsule applied. The measured
   delta is causal by construction. Require: median improvement ≥ `claim.delta_pct × (1 − 0.25)`.
   _Kills: fabricated numbers._
4. **Author-blind held-out** — each juror generates `n=8` fresh scenarios from the context class's
   parameter space using its own seed stream (author never sees them). Require: median improvement
   ≥ `MIN_EFFECT = 15%` and improvement in ≥ 6/8 episodes.
   _Kills: cherry-picked/overfit claims — the classic convincing hallucination._
5. **Invariant & conformance run** — every replay episode is checked against all registry invariants
   and the capsule's `conformance_required` tests. One violation anywhere → reject.
   _Kills: true-but-unsafe optimizations._
6. **Quorum certificate** — each juror signs `{capsule_id, verdict, measured_delta, partition_view}`.
   2-of-3 ACCEPT → CANDIDATE. Certificates are stored in the capsule and replicated: the _proof of
   verification travels with the insight_.
7. **Mesh-wide shadow staging** — on quorum cert, the capsule push-gossips as CANDIDATE. Every node
   that receives a matching live task forks the seeded episode, runs both branches (a simulator;
   forking is free — say so), and appends a signed SHADOW_RECORD to its store; records replicate by
   anti-entropy. Promotion is **derived, never announced**: a pure function flips a capsule ACTIVE
   locally once the store holds ≥ SHADOW_QUORUM_N records from ≥ SHADOW_MIN_NODES distinct nodes with
   wins ≥ SHADOW_QUORUM_WIN and zero invariant hits — monotone, so no flapping, and convergent with
   the store. The jury samples the _declared_ context; shadow consumes the _live, drifting_ stream —
   the lab, then the field. _Kills: passes-the-lab-fails-the-field cases, cheaply and mesh-fast._

Hallucination taxonomy → which stage kills it (put this table in the defence slide):

| Failure mode               | Killed by                                                         |
| -------------------------- | ----------------------------------------------------------------- |
| Fabricated effect size     | Stage 3 (counterfactual replay of author's own seeds)             |
| Overfit to lucky cases     | Stage 4 (author-blind held-out)                                   |
| Real gain, violates policy | Stage 5 (invariants/conformance in every episode)                 |
| Real gain, wrong context   | Context predicate + Stage 4 sampling from the declared class only |
| Stale (world drifted)      | TTL + Sentinel probes (§6.4)                                      |
| Correlation, not causation | Same-seed with/without forking — delta is causal by construction  |

**Consensus choice, stated plainly:** we did _not_ use BFT consensus or a blockchain. Verification
here is not an ordering problem; it is a replay problem. We need "did k independent parties reproduce
the effect," not "what is the global order of transactions." Quorum-certified replay gives the first;
a ledger gives the second at the cost of liveness under partition. (Full argument: DEFENCE.md Q1.)

Thresholds live in `fabric/config.py` as named constants (`JURY_K=3`, `QUORUM=2`, `HELDOUT_N=8`,
`MIN_EFFECT=0.15`, `CLAIM_TOL=0.25`, `SHADOW_QUORUM_N=6`, `SHADOW_QUORUM_WIN=5`,
`SHADOW_MIN_NODES=2`) — judges will ask for them;
answer by opening one file.

---

## 6. Dilemma B — Drift & Poisoning: the layered immune system

**Design stance:** admission control is a border wall; a fabric also needs an immune system. We assume
some poison gets in and make its removal _surgical, not amnesiac_.

### 6.1 Border: the Pawl (pre-admission, autonomous)

Ordered checks, each returning `(pass, reason)` — the reason string is displayed live when blocking:

1. Schema + signature + registry version + author identity known.
2. **Ratchet monotonicity** — the pawl rule that names the system: a capsule may tighten
   SAFETY/COMPLIANCE-class bounds but may never loosen one (e.g., `inspection_depth` may go up in a
   COMPLIANCE context, never down below the invariant floor; no `allowlist`/`bypass` action exists in
   the SAFETY action vocabulary at all). Loosening a safety bound is not a capsule; it is an operator
   decision requiring a signed human token (`operator_override`, stubbed but present in the schema).
   _The ratchet only turns one way for safety — by construction, not by review._
3. Bounded context — no wildcard predicates; interval widths capped per dimension (blast radius).
4. Falsifiable claim present; `n_episodes ≥ 4`; seeds present.
5. Rate & reputation — submissions per agent per 100 sim-seconds = `floor(3 × reputation)`;
   reputation < 0.3 → auto-reject (isolation) until decay recovery.

### 6.2 Blast radius (structural)

Scoped contexts + adoption-as-prior + local invariant enforcement mean a poisoned ACTIVE capsule can
at worst degrade optimality inside one context; it can never flip an invariant anywhere.

### 6.3 Staging (temporal)

Shadow mode (§5.7) means even an admitted capsule influences nothing until a mesh-wide quorum of
signed shadow records exists — its first applications everywhere are measured, not trusted.

### 6.4 Post-hoc: Sentinel probes + bisect + Excision

- **Sentinel probes**: every `PROBE_PERIOD = 60` sim-seconds, replay a pinned suite of 12 golden
  scenarios (fixed seeds, spanning all incident classes) against the current ACTIVE set; compare all
  KPIs (solve cost, time-to-mitigate, false-positive quarantines, SLA burn) to recorded golden
  baselines. Any KPI regression > 10% → drift alarm. _Memory has CI._
- **Bisect**: order recently activated capsules by activation time; binary-search replay of the golden
  suite with half the suspects disabled per step → culprit in O(log n) replays. _We bisect memory the
  way engineers bisect code._
- **Excision**: emit signed `REVOKE{capsule_id, reason, probe_report}` → tombstone; compute the
  transitive closure of `derived_from` over the DAG → those descendants drop to QUARANTINED and
  re-enter Jury without the poisoned ancestor's evidence; slash reputation (author −0.4, each
  approving juror −0.2 — jurors have skin in the game). Everything else in the fabric is untouched.
  Demo shows capsule count going 12 → 10, **not 12 → 0**: collective memory is never reset.

### 6.5 Why the subtle-poison demo is honest (build it exactly like this)

The rogue agent submits two capsules:

- **Blatant**: payload contains `allowlist_subnet` in a SAFETY context → Pawl check 2 blocks it live,
  reason string on screen. (Border wall works.)
- **Subtle**: an aggressive rate-limit rule that _genuinely_ improves the claimed metric
  (`solve_cost`) on held-out scenarios — so it passes admission honestly — but degrades an
  off-claim KPI (false-positive quarantines) under traffic mixes the context sample under-represents.
  The Sentinel probe catches the KPI regression ≤ 60 sim-seconds later → bisect → Excision.
  Defence line: _admission validates the claim; Sentinels validate the system. That is why the fabric
  has an immune system and not just a border wall._

---

## 7. Dilemma C — Consistency: three layers, one sentence each

**Storage is eventually consistent. Meaning is scoped. Decisions are deterministic.**

1. **Storage — CRDT (AP)**: the store is an OR-set of content-addressed records (adds and tombstones
   both replicate; concurrent adds commute; anti-entropy = periodic digest exchange + pull of missing
   ids in `fabric/gossip.py`). Partitions never block writes; heal = set union. There is no storage
   conflict to resolve, by construction.
2. **Meaning — scoped by context**: two capsules with disjoint contexts are two truths, not a
   conflict. Most "conflicting fixes valid in different contexts" (the PS's exact phrase) are
   resolved by the data model before any protocol runs.
3. **Decisions — deterministic pure function**: when two ACTIVE capsules' contexts genuinely overlap
   for a live task, every agent resolves identically by calling Phase 1's `arbitrate()`:
   priority class lexicographically → confidence × effect-size weight → capsule-hash tie-break.
   Same inputs (replicated capsules) + pure function = same answer on every replica, no coordinator,
   no split-brain _behavior_ even when the store is momentarily divergent.
4. **Refine — persistent overlap is an underspecified context**: if the same overlap arbitrates
   repeatedly (≥ 3 tasks), the fabric emits `REFINE`: split the predicate along the dimension where
   the two capsules' evidence distributions separate most (their seed-episode parameter ranges are
   stored; pick the dim with disjoint or least-overlapping ranges; if none separates, the arbitration
   winner takes the whole overlap and the loser is SUPERSEDED in-overlap only). Conflicts are treated
   as signals that the context taxonomy is too coarse — the resolution sharpens the map instead of
   deleting a truth.
5. **Partition semantics**: quorum certs record `partition_view` (the sorted reachable-agent set at
   cert time). On heal, any capsule whose cert was formed with `|view| < ceil((N+1)/2)` demotes to
   CANDIDATE and re-juries across the full mesh. Minority-island knowledge is preserved but
   provisional — never silently authoritative.

**CAP stance for the defence:** AP for memory, because safety was moved out of the consistency layer
entirely — every agent enforces invariants locally, so temporary divergence degrades optimality,
never safety. _Slow, never unguarded_ (Phase 1's principle, kept).

Trade-off ledger (mirror in DEFENCE.md):

| Chose                     | Rejected                  | Gave up                               | Why acceptable                                                                              |
| ------------------------- | ------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------- |
| CRDT OR-set + gossip      | Ledger/total order        | Global transaction order              | Verification ≠ ordering; liveness under partition; audit kept via signatures + hash DAG     |
| Scoped consistency        | Global semantic locking   | Cross-context atomicity               | Capsules are advisory priors bounded by local invariants                                    |
| Deterministic arbitration | Quorum reads per decision | Freshness guarantees at decision time | Same pure function everywhere ⇒ no split-brain behavior; staleness bounded by gossip period |
| Refine-on-overlap         | Last-writer-wins          | Simplicity                            | LWW deletes a truth; Refine keeps both, sharpens the map                                    |

---

## 8. The simulation world (Cisco-flavored, deterministic)

**Setting:** five site agents in an enterprise mesh — `site-a … site-e` (mix of `branch`, `campus`,
`dc` site classes). Each receives incident tickets and must pick a mitigation from a typed playbook.
One agent (`site-e`) can be flipped rogue by the chaos injector.

**Incident classes** (each = parameter distribution + a seeded episode simulator in
`world/scenarios.py`):
`ddos_syn_flood`, `iot_anomaly_burst`, `cert_expiry_storm`, `lateral_movement_alert`,
`congestion_hotspot`, `phishing_wave`.

**Registry additions (v3.2)** — same structure as Phase 1 (unit + conformance test per dimension):
`rate_limit_pps`, `inspection_depth (0–7)`, `quarantine_scope {none, flagged_only, subnet}`,
`retry_backoff_ms`, `sampled_fraction`, `block_ttl_s`, plus scenario dims `traffic_gbps`,
`device_count`, `site_class`.
**Invariants (constitution):** `no_flagged_flow_bypasses_inspection`, `quarantine_reversible`,
`p99_latency_within_slo`, `no_blanket_subnet_block_without_compliance_class`.

**Episode model:** an episode is `simulate(incident_params, action, seed) → metrics`
(`time_to_mitigate_s`, `fp_quarantines`, `sla_burn`, `invariant_hits`). Deterministic given
`(params, action, seed)`. Keep the internals simple and legible — a few dozen lines of arithmetic per
class with noise from the seeded RNG; the _shape_ matters (wrong action ⇒ high cost; right action
region ⇒ low cost; class-dependent optimum that shifts with params).

**Solving without memory:** the agent's Strategist does bounded local search (hill-climb over the
quantized action space, ≤ 12 attempts, each attempt costs). This is the discovery cost.
**Solving with memory:** query fabric for ACTIVE capsules matching the task's context → apply as
prior (start point) → typically 0–2 refinement attempts. This is the reuse cost. The gap between the
two _is the ratchet_, and it is measured, not asserted.

**Strategist is an interface** (`agents/strategist.py`): `HeuristicStrategist` (default,
deterministic, demo-safe) and `LLMStrategist` (optional, behind `--strategist=llm`, stub acceptable).
Defence line: _models propose, the protocol disposes_ — the fabric is model-agnostic because nothing
in validation ever evaluates language, only replayed behavior.

**Cost model** (`world/cost.py`, constants pinned so demo numbers reproduce):
`solve_cost = 2.0·attempts + 0.05·time_to_mitigate_s + 5.0·fp_quarantines + 1.0·sla_burn`
(+ `25.0·invariant_hits`, which must remain zero in any healthy run). Interpretation for the business
story: attempts ≈ analyst-minutes of toil; the rest ≈ service impact.

**TaskGen:** Poisson arrivals (rate λ drifts over the run), incident-class mix drifts on a schedule,
parameters drift within classes ("changing conditions", requirement 1). Fully seeded.
**Sim clock:** logical time only (`world/simclock.py`); no wall-clock in logic; TUI may pace playback.

**Twin-lane A/B:** the run harness executes the _same seeded task stream_ twice in-process — Lane A
fabric ON, Lane B fabric OFF — so the cumulative-cost comparison chart is a controlled experiment,
not a vibe. (Cheap: same TaskGen seed, second agent set with fabric disabled.)

---

## 9. Components and repo layout

```
cognition-fabric/
├── docs/BLUEPRINT.md          # this file
├── docs/DEFENCE.md            # provided
├── docs/DEMO_RUNBOOK.md       # provided
├── fabric/
│   ├── registry.py            # dimensions, invariants, conformance tests (port + extend Phase 1)
│   ├── capsule.py             # schema (pydantic), canonicalization, content addressing, signing
│   ├── store.py               # OR-set store, persistence (JSONL per node under .state/<agent>/)
│   ├── gossip.py              # digest exchange + pull; push on promotion (the Accelerator's wire)
│   ├── pawl.py                # guardrail checks, ordered, reason strings
│   ├── jury.py                # sortition, counterfactual replay, held-out, quorum certs
│   ├── lifecycle.py           # state machine, shadow staging, promotion, TTL
│   ├── excision.py            # revoke, transitive quarantine, reputation slashing
│   ├── probes.py              # Sentinel golden suite, drift alarm, bisect
│   ├── arbitration.py         # Phase 1 arbitrate(), ported verbatim + overlap Refine
│   └── config.py              # every named threshold in this document
├── agents/
│   ├── agent.py               # task loop: query fabric → act → measure → maybe author capsule
│   ├── strategist.py          # Heuristic (default) + LLM stub behind interface
│   └── rogue.py               # poison authoring behaviors (blatant + subtle)
├── world/
│   ├── taskgen.py  scenarios.py  cost.py  simclock.py  bus.py   # bus = in-process, chaos-injectable
├── chaos/
│   └── injector.py            # faults: poison_blatant, poison_subtle, partition, node_crash, flap
├── ui/
│   ├── events.py              # single structured event stream (JSONL); everything else consumes it
│   └── tui.py                 # rich Live dashboard (panels in §11)
├── demo/
│   ├── demo_ratchet.py        # scripted Act 1–2 (RUNBOOK)
│   ├── demo_chaos.py          # scripted Act 3
│   └── demo_smoke.py          # 20-second end-to-end sanity run (CI gate)
└── tests/                     # pytest; includes tests/test_dilemma_{a,b,c}.py
```

**Transport honesty:** `world/bus.py` is an in-process async message bus with injectable partition
sets, delays, and drops. It is a _simulated network with real algorithms on top_ — the PS explicitly
allows simulation; §13 owns this out loud. No sockets; the demo must run offline.

---

## 10. Milestones (build in order; every milestone leaves `make demo-smoke` green)

Priorities: **[MUST]** = core requirements; **[SHOULD]** = defence strength; **[STRETCH]** = polish.

- **M0 [MUST] World.** simclock, bus, registry, scenarios for 3 incident classes, cost model,
  taskgen. _Accept:_ seeded run of 20 tasks prints identical episode metrics across two runs.
- **M1 [MUST] Agents baseline (fabric OFF).** Strategist hill-climb, agent task loop, event stream.
  _Accept:_ 5 agents process a storm; per-class solve costs are high and roughly flat over time.
- **M2 [MUST] Capsule + store + persistence.** Schema, signing, OR-set store, JSONL persistence,
  restart-reload. _Accept:_ kill an agent process mid-run, restart, its store reloads intact
  (unit test + manual).
- **M3 [MUST] Pawl + Jury + lifecycle.** Full §5 pipeline + §6.1 checks + shadow staging.
  _Accept:_ `tests/test_dilemma_a.py` — a fabricated-claim capsule and an overfit capsule are both
  rejected at the correct stage; an honest capsule reaches ACTIVE.
- **M4 [MUST] Gossip + reuse + ratchet metrics + twin-lane A/B.** Promotion push, digest anti-entropy,
  fabric-query-before-solve, ratchet staircase + insight-lead-time + cumulative A/B cost.
  _Accept:_ repeat incidents at other sites solve at reuse cost; staircase steps down; Lane A
  cumulative cost visibly below Lane B on the same seed. **At M4, requirements 1–5 all demonstrable.**
- **M5 [SHOULD] Sentinels + bisect + Excision.** §6.4 complete. _Accept:_ `tests/test_dilemma_b.py` —
  subtle poison passes admission, Sentinel flags it, bisect finds it, Excision removes it + its
  descendant; unrelated capsules and their reuse behavior untouched.
- **M6 [SHOULD] Chaos injector + partition semantics.** Faults incl. partition/heal with
  provisional-cert demotion and Refine on overlap. _Accept:_ `tests/test_dilemma_c.py` — partition
  produces two capsules for one class; heal produces deterministic identical arbitration on every
  node, then a Refine split; both contexts survive.
- **M7 [MUST] TUI + demo scripts.** §11 panels; `demo_ratchet.py`, `demo_chaos.py` reproduce the
  RUNBOOK beats on fixed seeds with stable timings. _Accept:_ full RUNBOOK dry-run ≤ 12 min.
- **M8 [STRETCH]** LLM strategist behind flag; asciinema recording of both demos as fallback;
  optional thin web view consuming `events.jsonl`.

---

## 11. Dashboard panels & headline metrics (rich TUI)

Panels: **Mesh** (agent id, site class, state, reputation, current task) · **Fabric** (capsule table:
id-short, class, context summary, state, confidence, author) · **Ratchet** (per-class staircase
sparklines of best-known cost — the money chart) · **Economics** (cumulative cost Lane A vs Lane B,
% saved, insight lead time) · **Event log** (color-coded: PAWL_BLOCK red, PROMOTED green,
EXCISION magenta, REFINE cyan, REUSE dim green).

Headline numbers the RUNBOOK narrates (targets, tune constants until the seeds produce roughly):
first-solve cost ≈ 25–35 units; reuse cost ≈ 4–8 units; storm of ~60 tasks with ~40% repeats →
Lane A total ≈ 40–50% below Lane B; insight lead time ≈ 3–6 sim-s; Excision removes exactly 2 of ~12
capsules.

---

## 12. Bus message set

`TASK` (world→agent) · `GOSSIP_DIGEST` / `GOSSIP_PULL` / `GOSSIP_PUSH` (store sync; PUSH also fired
eagerly on promotion — the Accelerator) · `JURY_REQ` / `JURY_VOTE` (with signed verdicts) ·
`REVOKE` (Excision broadcast) · `PROBE_REPORT` · `HEARTBEAT`. All messages carry `sender`, `sim_time`,
`sig`. The chaos injector operates on the bus: it never reaches into stores — faults are network- and
behavior-level only, which is the honest kind.

---

## 13. Honest scoping (say these before judges ask)

- Transport is simulated (in-process bus); algorithms above it (gossip, sortition, quorum certs,
  CRDT merge) are real and would ride any transport, including Phase 1's mTLS channels.
- Signing is HMAC-keyring, a stub with the same interface as real PKI; Phase 1 already specified the
  identity layer.
- Sortition is hash-based, not VRF-based; the upgrade is a drop-in at one function.
- Quorum-certified replay is not BFT; our adversary model is "few rogue authors/jurors," backstopped
  by Sentinels + Excision, not "arbitrary Byzantine majority" — stated as a scoping decision.
- Episode simulators are stylized; the sim-to-real seam is exactly the conformance tests + shadow
  mode (capsules would shadow on real traffic before ACTIVE in production).
- Economics are simulated; the controlled A/B _shape_ is the claim, not the absolute numbers.

## 14. Anti-goals

No blockchain libs. No real sockets. No LLM calls in the core path. No global mutable state. No
wall-clock in logic. No renaming of defence vocabulary. No feature not traceable to §0.
