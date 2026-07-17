# JUDGE_PREP — Cognition Fabric, explained from first principles

**Private prep document. Not part of the submission. Read top to bottom once, then drill §13.**

How to use: §1–2 give you the problem and the vocabulary. §3–7 are the system, in the order the
problem statement asks for it. §8 is every fork in the road with full reasoning — this is where
judge questions live. §9 maps every mechanism to a famous real technology (including Cisco's own).
§10 is every number. §11 is what to claim as creative. §12 is your on-stage numbers card,
including the two numbers that miss their target band and exactly what to say. §13 is the Q&A
drill. §14 is what never to claim.

---

## 1. The problem statement, decoded

Phase 2 ("The Continuous Mesh & The Ratchet Effect") asks: a mesh of autonomous agents handles a
continuous flow of enterprise tasks. One agent has a localized breakthrough. Build:

1. **A dynamic flow of tasks under changing conditions** — the world must drift, not repeat.
2. **A fabric layer** that captures the breakthrough — shared memory (the PS suggests "ledger,
   cache, or equivalent").
3. **An accelerator** that propagates the insight to all agents — but only after verification.
4. **An autonomous guardrail** that vets insights *before* acceptance, without a human.
5. **Visible reuse** — the "ratchet effect": once the fleet learns something, performance clicks
   forward and doesn't slide back.

Plus a bonus: a **chaos injector** (deliberate fault injection). Plus three "dilemmas" the design
must answer:

- **A. Innovation vs. Hallucination** — how do you accept genuinely new insights while rejecting
  confident nonsense?
- **B. Drift & Poisoning** — what if bad knowledge gets in (maliciously or by the world changing),
  **without resetting collective memory**? (That phrase is verbatim from the PS — our demo answers
  it literally: capsule count goes 12 → 10, never to 0.)
- **C. Consistency at scale** — agents discover **conflicting fixes, both valid in different
  contexts** (also verbatim); how does the mesh stay consistent without split-brain?

Our one-paragraph answer, memorize it:

> Phase 1 gave agents a shared typed language and signed contracts with no coordinator —
> *contracts, not conversations*. Phase 2 gives the mesh a memory with the same discipline —
> *evidence, not claims*. An insight is a **capsule**: a typed decision rule carrying a falsifiable
> claim, the seeds to replay it, its scope, and its provenance. Before it enters collective memory
> it must survive **execution** — counterfactual replay by a randomly-drawn jury on scenarios its
> author never saw — and pass the **Pawl**, the guardrail that makes the ratchet mechanical: the
> fabric can autonomously get stricter, and can only get looser with a signed human decision. Once
> admitted, memory is defended in depth — shadow staging, Sentinel probes, provenance bisect, and
> surgical **Excision**. Consistency is layered: storage is eventually consistent, meaning is
> scoped, decisions are deterministic.

---

## 2. Vocabulary you must own

Each term: plain meaning first, then how we use it. Drop these naturally; never use one you can't
define on the spot.

| Term | Plain meaning | In this project |
|---|---|---|
| **Capsule** | A sealed unit of knowledge | The unit of collective memory: a typed decision rule + falsifiable claim + replay seeds + scope + provenance + signature. Never free text. |
| **Falsifiable claim** | A statement precise enough that an experiment could prove it wrong (Popper's term from philosophy of science) | Every capsule states "metric X improves by Y% over baseline, here are the N seeds" — anyone can re-run it. |
| **Content-addressed** | An object's ID *is* the hash of its content (how git names commits) | `capsule_id = sha256(canonical body)` → tamper-evident, deduplicated, and two nodes agree on IDs without talking. |
| **Provenance** | Where something came from, as a traceable chain | `derived_from` edges form a DAG (directed acyclic graph); this is what makes bisect and surgical excision possible. |
| **The Pawl** | On a real ratchet wrench, the pawl is the little catch that lets the gear turn one way only | Our pre-admission guardrail. Headline rule: capsules may *tighten* safety/compliance bounds, never loosen them. "A ratchet without a pawl spins backward." |
| **Sortition** | Selecting officials by lottery (ancient Athens governed this way) | Jurors = the 3 agents with the lowest `sha256(agent_id ‖ capsule_id ‖ epoch)`, author excluded. Unpredictable before the capsule exists, verifiable by anyone after. |
| **Counterfactual replay** | Re-running the same event twice — once with the change, once without — so the difference is *caused* by the change | Same seed, baseline policy vs. capsule applied. The delta is causal by construction, not correlational. |
| **Held-out** | Data the author never saw (the train/test split from machine learning) | Each juror generates 8 fresh scenarios from the declared context's parameter space with its own seed stream. Kills cherry-picking. |
| **Quorum certificate** | A signed statement that k-of-n independent parties agreed | 2-of-3 jurors sign `{capsule_id, verdict, measured_delta, partition_view}`. The cert travels with the capsule: proof of verification propagates with the insight. |
| **Shadow mode / shadow staging** | Running a change in parallel so it's measured but affects nothing (how banks test new fraud models) | A CANDIDATE capsule is forked-and-compared on live tasks across the mesh; it influences no real decision until promotion. |
| **CRDT** | Conflict-free Replicated Data Type — a data structure where concurrent updates merge automatically, in any order, to the same result | Our store is an **OR-set** (observed-remove set) of capsules and records; merge = union; partitions never block; heal is trivial. |
| **Anti-entropy / gossip** | Nodes periodically compare summaries and pull what they're missing (Amazon Dynamo popularized this) | Periodic digest exchange + pull of missing IDs; plus an eager push on promotion (the Accelerator's wire). |
| **Tombstone** | A record that marks "this item was deleted" and replicates like any other record | REVOKE is a tombstone — the mistake itself stays in memory, auditable forever. |
| **Sentinel probes** | Scheduled watchdog re-tests | Every 60 sim-seconds, replay a pinned "golden suite" of 12 scenarios against current ACTIVE capsules and compare **all** KPIs to recorded baselines. "Memory has CI." |
| **Bisect** | Binary search over history to find which change broke things (`git bisect`) | Binary search over recently-activated capsules, replaying the golden suite with halves disabled → culprit in O(log n) probes. |
| **Excision** | Surgical removal | Tombstone the culprit, transitively quarantine its descendants for re-validation, slash reputations. Everything else untouched. |
| **Refine** | Sharpening a predicate by splitting it | A persistent conflict between two valid capsules = an *underspecified context*; split along the dimension where their evidence separates. Both truths survive, scoped. |
| **Arbitrate()** | Our Phase-1 pure conflict-resolution function | priority class → confidence-weighted → hash tie-break. Pure + same replicated inputs = identical decision on every node, no coordinator. |
| **CAP theorem** | A distributed store under a network **P**artition must choose between **C**onsistency (everyone sees the same data) and **A**vailability (everyone can keep working) | We choose AP for memory — and can afford it because safety was moved out of the consistency layer entirely (invariants are enforced locally). |
| **Monotone / CALM** | A condition that, once true, stays true. The CALM theorem (Consistency As Logical Monotonicity) says monotone logic needs **no coordination** to stay consistent | Promotion is a monotone threshold over accumulating signed records — that's *why* it needs no announcement, can't flap, and converges everywhere. |
| **Determinism** | Same inputs → byte-identical outputs, every run | All randomness flows through seeded generators; no wall-clock in logic. Both demos replay byte-for-byte. "Even our chaos is replayable." |
| **Idempotent / commutative** | Applying twice = applying once / order doesn't matter | The mathematical properties of OR-set merge that make gossip order irrelevant and convergence guaranteed. |
| **Ratchet staircase** | Our money chart | Per incident class, best-known solve cost so far — monotone non-increasing by construction. Requirement 5, visualized. |
| **Insight lead time** | — | Sim-seconds from local discovery to fleet-wide availability. The Accelerator, measured. |

---

## 3. The world we built (so validation has something real to validate)

You cannot demonstrate "insight verification" against a fake world — the insight must be *earned*,
so the validation is *meaningful*. First-principles chain:

- **Five site agents** (`site-a`…`site-e`, mix of branch/campus/dc classes — Cisco's own site
  taxonomy). Why five, not two? Phase 1's problem was bilateral. Phase 2's claims — propagation,
  quorum with the author excluded, partitions leaving a viable majority — need N ≥ 5: the smallest
  mesh where a 3-jury excludes the author with room, and a 2|3 partition still has a majority side.
- **Incident classes** (`ddos_syn_flood`, `iot_anomaly_burst`, `cert_expiry_storm`): each is a
  parameter distribution + a small seeded episode simulator. An **episode** =
  `simulate(incident_params, action, seed) → metrics` (time-to-mitigate, false-positive
  quarantines, SLA burn, invariant hits). Deterministic given (params, action, seed).
- **Typed action space** from the registry: `rate_limit_pps`, `inspection_depth`,
  `quarantine_scope`, `retry_backoff_ms`, `sampled_fraction`, `block_ttl_s`. Actions are data, not
  code — this is what makes them mechanically checkable.
- **Cost model**: `solve_cost = 3.0·attempts + 0.075·time_to_mitigate + 7.5·fp_quarantines +
  1.5·sla_burn + 37.5·invariant_hits`. Business reading: attempts ≈ analyst-minutes of toil, the
  rest ≈ service impact. Invariant hits are priced so high a healthy run must have zero.
- **Solving without memory** (discovery): bounded hill-climb over the quantized action space,
  ≤ 12 attempts, each attempt costs. **Solving with memory** (reuse): query fabric → apply the
  matching ACTIVE capsule as a *prior* (a starting point, never an override) → at most 2 refinement
  attempts. The gap between those two costs **is the ratchet, measured, not asserted**.
- **TaskGen** (requirement 1): Poisson arrivals with a drifting rate, incident-class mix drifting
  on a schedule, in-class parameters drifting within bounds. Fully seeded.
- **Twin-lane A/B**: the same seeded task stream is run twice in-process — Lane A fabric ON, Lane B
  fabric OFF. The economics chart is therefore a **controlled experiment** (only one variable
  differs), not a vibe.
- **Determinism discipline**: every random draw comes from an explicitly-passed seeded
  `random.Random` (one stream per concern); logic reads time only from a simulated clock. There is
  a test asserting byte-identical output across runs. This is how FoundationDB and TigerBeetle test
  distributed systems — *deterministic simulation testing* — and it means our live demo cannot
  behave differently on stage than in rehearsal.

Honesty rider (say before asked): episode simulators are stylized; transport is an in-process bus.
**Simulated network, real algorithms** — the PS explicitly allows simulation, and every algorithm
above the bus (gossip, sortition, certs, CRDT merge, bisect) would ride any real transport,
including Phase 1's mTLS channels.

---

## 4. The five requirements, mechanism by mechanism

### Req 1 — Dynamic task flow: TaskGen
Covered above. On screen: the incident ticker runs throughout, class mix visibly shifts. One
sentence: "the world drifts on three axes — arrival rate, class mix, in-class parameters — all
seeded."

### Req 2 — The fabric: capsule + store

The capsule schema (field names are part of the defence — a judge can ask for any of them):
`capsule_id` (content-addressed) · `context` (incident class + per-dimension intervals — the
applicability predicate, the unit of both consistency and blast radius) · `payload.rule` (a typed
action, never code, never prose) · `claim` (metric, baseline median, with-capsule median, delta %,
n episodes) · `evidence` (scenario seeds — what makes the claim replayable by strangers;
conformance tests required; trace digest) · `provenance` (author, epoch, `derived_from` DAG edges)
· `lifecycle` (state, quorum cert, confidence, TTL) · `sig`.

The store: an **OR-set CRDT** of signed, content-addressed records (capsule adds, tombstones,
shadow records, lifecycle metadata), replicated by gossip anti-entropy, persisted per node as an
append-only JSONL log under `.state/<agent>/`. Kill a node mid-run, restart it: the store reloads
intact and re-syncs by ordinary anti-entropy — no special recovery path. (Shown live in Act 1.)

### Req 3 — The accelerator: the validation pipeline + push gossip

Local discovery → author a capsule → **Pawl** static checks → **Jury** (sortition, counterfactual
replay, held-out, invariants) → 2-of-3 **quorum cert** → push-gossip as CANDIDATE → mesh-wide
**shadow staging** → promotion **derived** locally from replicated records → ACTIVE everywhere.
Measured as **insight lead time**. The key inversion to say out loud: *the proof of verification
travels with the insight* — a node receiving a capsule receives its evidence, its cert, and its
provenance; trust is transported, not assumed.

### Req 4 — The autonomous guardrail: the Pawl

Ordered checks, each returning `(pass, reason)` — the reason string is what judges see on screen:

1. Schema + signature + registry version + known author identity.
2. **Ratchet monotonicity** — the rule that names the system. A capsule may *tighten* a
   SAFETY/COMPLIANCE bound (inspection depth up), never loosen one. Loosening is not a capsule; it
   is an operator decision requiring a signed human token. There is *no* `allowlist`/`bypass` verb
   in the SAFETY action vocabulary at all — the attack isn't caught by review, it's unrepresentable.
3. Bounded context — no wildcards; interval width capped per dimension (blast radius cap).
4. Falsifiable claim present, ≥ 4 episodes, seeds present.
5. Rate & reputation — submissions per window scale with reputation; below 0.3 → auto-isolation.

### Req 5 — Visible reuse: the ratchet

Three simultaneous proofs on screen: the **staircase** (best-known cost per class, monotone
non-increasing, steps down on each promotion), **REUSE events** (site-C solves at cost ~13 using a
capsule site-A authored), and the **twin-lane economics** (Lane A cumulative cost pulls 40.5% below
Lane B on the identical seeded storm). Plus the emotional beat: site-D crashes in Act 0 (fabric
off) and loses everything; crashes again in Act 1 (fabric on) and *restarts with memory*. "Same
crash. Different outcome. That delta is the Fabric."

### Bonus — chaos injector

`chaos/injector.py`: partition (blocks anti-entropy between islands), heal, node crash
(store round-trip through persistence). Poison faults (blatant + subtle) are authored through the
rogue agent path. All chaos is seeded and replayable — "even our chaos is deterministic."

---

## 5. Dilemma A — Innovation vs. Hallucination

**The claim, verbatim:** *"We never validate what an agent says; we validate what its capsule does
— twice, with and without it, on scenarios the author has never seen. A hallucination can survive
a conversation; it cannot survive execution."*

First-principles derivation. A hallucination is a *confident claim with no underlying reality*. So
don't evaluate confidence (gameable), don't evaluate plausibility (LLM-judge = hallucination
checking hallucination), evaluate **reproducibility** — the same move science makes: peer review
by replication, not by reading the abstract. That's only possible because capsules are typed and
carry seeds: the claim is an *experiment description*, so anyone can re-run it.

The seven-stage pipeline, and what each stage uniquely kills:

| Stage | Mechanism | Kills |
|---|---|---|
| 1. Pawl | static checks | malformed / unsigned / unsafe-by-vocabulary |
| 2. Sortition | jurors = 3 lowest `sha256(agent ‖ capsule_id ‖ epoch)`, author excluded | a chosen or predictable committee — the committee can't exist before the capsule's own hash does |
| 3. Counterfactual replay | author's own seeds, same seed with/without capsule; require median ≥ claim × (1−0.25) | **fabricated effect sizes** — the delta is causal by construction |
| 4. Author-blind held-out | each juror samples 8 fresh scenarios from the *declared* context's parameter space; require ≥15% median and ≥6/8 wins | **cherry-picked / overfit claims** — the classic convincing hallucination |
| 5. Invariants + conformance | every replay episode checked against all invariants | **true-but-unsafe optimizations** (a real gain that violates policy) |
| 6. Quorum cert | 2-of-3 signed verdicts, stored in the capsule | unverified propagation — proof travels with the insight |
| 7. Mesh-wide shadow | live-task fork-and-compare across nodes; promotion **derived** from ≥6 signed records from ≥2 distinct nodes with ≥5 wins and 0 invariant hits | **passes-the-lab-fails-the-field**; also: a lying promoter, because there is no promoter |

Stage 7 is our proudest design point, explain it slowly if asked: promotion is **derived, never
announced**. No node ever says "this capsule is now ACTIVE." Instead each node applies a pure
function to its local replicated record set; when the threshold is met, ACTIVE becomes true
*locally*. The condition is **monotone** — records only accumulate — so once true it stays true (no
flapping), and since the records replicate, every node converges to the same verdict. This is the
CALM theorem in action: monotone conditions need no coordination. Even ACTIVE is not trusted
state; it's a threshold fact each node re-derives. Contrast: the jury sampled the *declared*
context (the lab); shadow consumes the *live, drifting* task stream (the field).

Known limit (own it first): 2-of-3 quorum replay is not Byzantine fault tolerance — a colluding
jury majority could admit a lie. That's inside our stated adversary model ("few rogue agents"),
and the backstop is exactly Dilemma B's machinery: Sentinels catch it post-hoc, bisect finds it,
Excision removes it, and the signing jurors are slashed — jurors stake reputation on every
signature. Raising JURY_K is one constant.

---

## 6. Dilemma B — Drift & Poisoning

**The claim, verbatim:** *"Admission control is a border wall; a fabric needs an immune system. We
assume some poison gets in and make its removal surgical, not amnesiac."*

First-principles derivation. Any admission system validates a *claim* — but a claim never covers
everything the system must be right about. So poison that honestly wins its claimed metric while
harming an unclaimed one **defeats admission by design**, no matter how good admission is. The
biology analogy is exact: skin (border) plus immune system (detection, isolation, memory of the
pathogen). Defence in four layers:

1. **Border — the Pawl** (§4 above). Blocks the blatant attack live, reason string on screen.
2. **Structure — blast radius.** Scoped contexts + adoption-as-prior + local invariant
   enforcement. A poisoned ACTIVE capsule can degrade *optimality* inside one context; it can never
   flip an *invariant* anywhere, because every agent re-checks its own constitution on every
   action. A capsule cannot make an agent violate its constitution.
3. **Time — shadow staging.** Even admitted capsules influence nothing until a mesh-wide quorum of
   signed shadow records exists.
4. **Immune system — Sentinel → bisect → Excision.** Sentinels replay a pinned golden suite every
   60 sim-seconds against the current ACTIVE set and compare **all** KPIs — including ones no
   capsule ever claimed (that's the point). One-sided tolerance: `solve_cost` may drop freely
   (that's the fabric's purpose); `fp_quarantines`/`sla_burn` may not regress >10%. Alarm →
   provenance bisect (binary search, halves disabled per step, culprit in ⌈log₂ n⌉ probes — 4
   probes over 12 suspects in the demo) → Excision: signed REVOKE tombstone, transitive quarantine
   of `derived_from` descendants (they re-jury *without* the poisoned evidence), author slashed
   −0.4, each approving juror −0.2. Everything else untouched: **12 → 10, never to 0.**

Why the demo attack is honest (judges probe this): the blatant poison (an `allowlist_subnet` rule
in a SAFETY context) is the strawman and we treat it as one — the Pawl blocks it. The *real*
staged attack is the subtle poison: it **genuinely improves its claimed metric on scenarios it has
never seen** — admission is doing its job and it is not enough. It regresses false-positive
quarantines under traffic mixes its context under-represents. We attack our own weakest layer on
stage. Judges distrust systems whose demos only show attacks they were built to catch.

A detail worth volunteering: during bisect, one poison can *mask* another via arbitration (the
second wins the overlap, hiding the first). Our bisect probes halves **in isolation** precisely so
"the window always contains a culprit" stays true under masking — and the demo's second excise
pass shows the unmasked poison being found.

---

## 7. Dilemma C — Consistency at scale

**The claim, verbatim:** *"Storage is eventually consistent. Meaning is scoped. Decisions are
deterministic."* Three layers, because "consistency" is three different problems:

1. **Storage (CRDT, AP).** The store is an OR-set of content-addressed records. Concurrent adds
   commute; merge is set union; adds and tombstones both replicate. There is **no storage conflict
   to resolve, by construction** — two writes never contend for one cell, because content
   addressing means there is no cell, only immutable records. Partitions never block writes; heal
   is union.
2. **Meaning (scoped by context).** Two capsules with disjoint contexts are **two truths, not a
   conflict** — which is exactly the PS's "conflicting fixes valid in different contexts." The
   data model resolves most conflicts before any protocol runs.
3. **Decisions (deterministic pure function).** When contexts genuinely overlap on a live task,
   every node calls the same pure `arbitrate()` from Phase 1: priority class lexicographically →
   confidence × effect-size weight → capsule-hash tie-break. Same replicated inputs + pure
   function = identical decision on every replica. **No split-brain behavior even while stores
   momentarily diverge.** (This is state-machine replication's core trick, without the ordering
   protocol — we can skip the ordering because the inputs are a convergent set, not a sequence.)

Plus two mechanisms for the hard residue:

4. **Refine.** If the same overlap arbitrates repeatedly (≥3 tasks), that's a signal the context
   taxonomy is too coarse: *a conflict is an underspecified context.* Split the predicate along
   the dimension where the two capsules' evidence separates most (in the demo: `traffic_gbps` at
   5.5 — one capsule's evidence lives in [1.0, 5.5], the other's in [5.5, 12.0]). Both survive,
   re-validated, scoped. We sharpen the map instead of deleting a truth.
5. **Partition-provisional certs.** Quorum certs record the `partition_view` (the reachable agent
   set at cert time). On heal, any cert formed by a minority island (view < ⌈(N+1)/2⌉) demotes to
   re-jury mesh-wide. Minority knowledge is **preserved but provisional — never silently
   authoritative.**

**CAP stance, one breath:** AP for memory — and we can *afford* AP because **safety was moved out
of the consistency layer entirely**. Invariants are enforced locally by every agent on every
action, so divergence during a partition degrades optimality, never safety. *Slow, never
unguarded* (Phase 1's principle, kept).

---

## 8. The trade-off ledger — every fork, all options, full reasoning

This is the section that wins Q&A. For each decision: the options, why each rejected one loses,
and what we knowingly gave up.

### 8.1 Memory substrate: why a CRDT store and not a blockchain/ledger

The PS itself says "ledger, cache, **or equivalent**" — so this is an invited design decision.

- **Option 1: Blockchain / distributed ledger.** What a ledger fundamentally buys is **global
  total order** — every node agrees on the sequence of all writes. Getting that order requires
  consensus (PoW/PoS/PBFT), and consensus costs **liveness under partition**: a minority island
  cannot commit. Now ask: does capsule validity depend on order? No — a capsule is valid because
  its claim replays and its signatures verify, not because of its position in a chain. So a ledger
  buys the one property we don't need and charges the one property we do need (islands keep
  learning during a partition — shown live in Act 3). **Rejected: pays liveness for ordering we
  never use.**
- **Option 2: Central database / coordinator.** Simplest, but a single point of failure and a
  single point of *trust* — and the PS is explicitly about a decentralized mesh. Phase 1's whole
  point was no coordinator. **Rejected: violates the premise.**
- **Option 3: Primary-replica replication (e.g., one elected leader).** Needs leader election
  (consensus again), blocks minority-side writes during partition. **Rejected: same liveness cost
  as the ledger, plus an election protocol we'd have to defend.**
- **Chosen: CRDT OR-set + gossip anti-entropy.** Concurrent adds commute, merge is union,
  convergence is a mathematical property (join-semilattice: commutative, associative, idempotent
  merge), partitions never block, heal is trivial. **What we gave up:** global total order and
  cross-context atomicity. **Why acceptable:** capsules are advisory priors bounded by local
  invariants — nothing about their correctness needs an order. **What we kept from the ledger:**
  append-only records, signatures, content addressing, hash-linked provenance, tombstoned deletes
  — i.e., full auditability. Line for judges: *"We kept the ledger's useful properties and dropped
  its consensus bottleneck."*

### 8.2 Validation: why quorum replay and not BFT consensus, reputation, or an LLM judge

- **Option 1: Trust + reputation only** ("site-A is usually right"). Reputation is a *prior*, not
  evidence; a trusted node that starts hallucinating poisons fastest. **Rejected: exactly the
  failure mode Dilemma A describes.**
- **Option 2: LLM-as-judge** (ask a model whether the insight looks right). Non-deterministic,
  gameable by phrasing, unauditable, and circular — using a hallucination-prone system to certify
  non-hallucination. **Rejected**, and generalized into a design rule: *no LLM in the core path;
  models propose, the protocol disposes.* The Strategist is an interface — swap in an LLM
  proposer and nothing in validation changes, because validation never evaluates language, only
  replayed behavior.
- **Option 3: Full BFT consensus (PBFT-style) on each capsule.** BFT solves *agreement on a value
  under arbitrary faults* at O(n²) messages and liveness cost. But our "value" has an **externally
  checkable ground truth**: you can re-run the experiment. When independent reproduction is
  possible, you don't need agreement machinery — you need k independent reproductions and
  signatures. **Rejected: verification here is a replay problem, not an ordering problem.** (Say
  that sentence verbatim; it's the crux.)
- **Chosen: sortition jury + counterfactual replay + quorum certificate.** Cheap (3 replays),
  partition-tolerant (certs record their view), and it produces a portable artifact (the cert).
  **Given up:** resistance to a colluding jury majority. **Mitigation:** unpredictable committees
  (hash sortition), juror slashing, and the Dilemma-B immune system as backstop; JURY_K is one
  constant if you want more.

### 8.3 Jury selection: why hash sortition

- **Fixed validator set** → bribable, single target, and centralizes what the PS decentralized.
- **Author-chosen jurors** → obviously self-dealing.
- **Round-robin** → predictable far in advance; an attacker times submissions to friendly jurors.
- **Random beacon** → needs a shared randomness source = another protocol to build and defend.
- **Chosen: jurors = k lowest `sha256(agent_id ‖ capsule_id ‖ epoch)`, author excluded.** The
  capsule's *own hash* seeds selection → the committee is unpredictable before the capsule exists
  (you can't shop for jurors), yet deterministic after (anyone can verify the committee was
  correct — no "who chose the choosers"). Same idea as Algorand's cryptographic sortition; theirs
  uses VRFs (verifiable random functions), ours is plain hashing — the VRF upgrade is a drop-in at
  one function, stated openly. **Given up:** an adversary who controls the capsule body has one
  degree of freedom (mutate body → different committee). Mitigated by the claim being *binding* —
  a mutated capsule must still replay.

### 8.4 Promotion: why derived, not announced

- **Author announces "it's ACTIVE now"** → a forgeable message; the author is the least trusted
  party in the room.
- **A leader/coordinator announces** → reintroduces the coordinator.
- **Two-phase commit across nodes** → blocks under partition, and 2PC's coordinator is a failure
  point; all cost, no need.
- **Chosen: promotion is a pure monotone function over replicated signed shadow records** (≥6
  records, ≥2 distinct nodes, ≥5 wins, 0 invariant hits). Nothing to forge (records are
  individually signed), nothing to announce (each node derives it), no flapping (monotone), and
  convergent (records replicate). *"Promotion is derived, never announced — even ACTIVE isn't
  trusted state."* This mirrors how progressive-delivery/feature-flag systems flip a flag when
  metric thresholds are met — except decentralized: every node is its own flag evaluator.

### 8.5 Poison recovery: why Excision, not reset or rollback

- **Reset collective memory** → the PS explicitly forbids it ("without resetting collective
  memory"), and it's amnesia: the fleet re-pays every discovery cost.
- **Rollback to a snapshot** → destroys every *good* capsule admitted since the poison; and in an
  AP system there is no global snapshot to roll back to.
- **Delete the record silently** → in an OR-set, an un-tombstoned delete resurrects on the next
  merge; and it destroys the audit trail.
- **Chosen: tombstone + transitive quarantine + slashing.** The tombstone replicates like any
  record (deletion that survives gossip), the `derived_from` DAG makes removal *surgical*
  (descendants re-jury without the poisoned evidence — they may be fine on their own), and
  slashing makes authors and jurors stake reputation. The mistake itself is retained, auditable:
  what was believed, when, and why it was excised. **12 → 10, never to 0.**

### 8.6 Conflict resolution: why arbitrate + Refine, not LWW or locking

- **Last-writer-wins** → deletes a valid truth based on a timestamp — and "both fixes are valid in
  different contexts" is the PS's own framing. LWW answers the wrong question.
- **Global semantic locking** ("only one capsule per incident class") → serializes learning,
  blocks under partition, and forces a false choice between two valid truths.
- **Manual human review of conflicts** → doesn't scale, and the PS asks for autonomy.
- **Chosen:** disjoint contexts coexist (no conflict by data model); overlaps resolve by the same
  pure `arbitrate()` everywhere (no split-brain behavior); *persistent* overlaps trigger Refine (a
  predicate split along the most-separating evidence dimension — the same move a decision tree
  makes when one leaf holds two populations). **Given up:** cross-context atomicity and freshness
  guarantees at decision time (staleness bounded by the gossip period). **Why acceptable:**
  capsules are priors, invariants are local — a stale prior costs optimality, never safety.

### 8.7 Safety: why a monotone Pawl + local invariants, not a review board or anomaly detection

- **Human review board** → not autonomous (requirement 4 says autonomous), and becomes the
  bottleneck the fabric exists to remove.
- **Anomaly detection on capsule contents** → statistical, evadable, and produces "suspicious"
  scores rather than reasons. A guardrail must be *explainable* — ours emits a one-line reason
  string for every block, shown live.
- **Chosen: a structural one-way rule.** Tighten allowed autonomously; loosen requires a signed
  human token; unsafe verbs simply don't exist in the SAFETY vocabulary. Enforced *by
  construction, not by review* — the same philosophy as capability-dropping in OS security
  (OpenBSD's `pledge`, Linux seccomp: a process can give up privileges, never regain them). Plus
  invariants enforced locally at application time — so even a Pawl bypass cannot make an agent
  violate its constitution. Two independent layers, both mechanical.

### 8.8 Memory format: why typed capsules, not fine-tuned weights or RAG text

- **Fine-tuning agent models on solutions** → uninspectable, unattributable, unrevocable. You
  cannot excise one insight from a weight update, and you cannot show an auditor which gradient
  caused which behavior. Also model-specific: swap vendors, lose the fleet's memory.
- **RAG (retrieval-augmented text notes)** → retrieved prose still has to be *interpreted* by a
  model at use time — reintroducing hallucination at the moment of reuse; and free text can't be
  mechanically checked by a Pawl or replayed by a jury.
- **Chosen: typed, signed, content-addressed decision rules with evidence.** Inspectable (an
  auditor reads a small typed diff), attributable (provenance), individually revocable
  (tombstone), model-agnostic (behavior, not prompts), and mechanically validatable. Nearest
  living relatives: a package registry with signed artifacts and CI — *memory treated as code.*

### 8.9 Infrastructure honesty choices (state these, don't hide them)

- **In-process asyncio bus, no sockets** → the PS allows simulation; real transport adds failure
  modes without adding architectural proof. Chaos operates *on the bus* (partitions, drops), never
  reaches into stores — faults are network- and behavior-level, the honest kind.
- **HMAC keyring, not PKI** → same interface, drop-in upgrade; Phase 1 specified the identity
  layer.
- **Hash sortition, not VRF** → drop-in at one function.
- **Deterministic sim, not live LLM agents** → determinism is what makes the demo rehearsable,
  the chaos replayable, and the A/B controlled. An LLM strategist exists behind a flag as an
  interface stub — models propose, the protocol disposes.

---

## 9. Real technology we borrowed from (name-drop map)

Every mechanism has a famous production ancestor. Use these when a judge looks skeptical — each is
one sentence.

| Our mechanism | Production ancestor |
|---|---|
| Content-addressed capsules, provenance DAG, bisect | **git** — commits are content-addressed, history is a DAG, `git bisect` finds the offending commit in O(log n). "We bisect memory the way engineers bisect code." |
| OR-set store, gossip anti-entropy, tombstones, AP stance | **Amazon Dynamo / Apache Cassandra / Riak** — the canonical AP stores; Riak and Redis Enterprise ship CRDTs in production; Figma and collaborative editors (Automerge/Yjs) converge concurrent edits the same way. |
| Hash sortition juries | **Algorand** — validators self-select by cryptographic lottery so committees can't be targeted in advance (theirs VRF, ours hash — stated stub). |
| Reputation slashing for signing jurors | **Ethereum proof-of-stake** — validators who attest to bad blocks lose stake; our jurors stake reputation on every certificate. |
| Quorum certificates traveling with the artifact | **Certificate Transparency / Sigstore** — signed, auditable attestations attached to the artifact, verifiable by anyone downstream. |
| Shadow → candidate → active lifecycle | **Canary and shadow deploys** (Netflix, Google SRE practice) — new code takes mirrored traffic, affects nothing, gets promoted on measured metrics. Enterprises already trust this lifecycle — that's the adoption argument. |
| Derived (threshold) promotion | **Progressive delivery / feature flags** (LaunchDarkly-style metric-gated rollouts) — decentralized here: every node evaluates the gate itself. Theoretical backbone: the **CALM theorem** — monotone logic needs no coordination. |
| Sentinel golden-suite probes | **CI regression suites** + Netflix's automated canary analysis — a pinned test set replayed on schedule against production state. "Memory has CI." |
| Chaos injector | **Netflix Chaos Monkey** — deliberately injecting faults to prove recovery machinery, except ours is deterministic and replayable. |
| Deterministic simulation of a distributed system | **FoundationDB / TigerBeetle / Antithesis** — the gold standard for testing distributed systems: simulate the network, seed all randomness, replay any bug byte-for-byte. |
| Counterfactual same-seed replay | **Paired A/B experimentation** — same seed with/without treatment makes the delta causal, not correlational; and ML's **train/held-out split** kills overfit claims. |
| Pawl one-way monotonicity | **OpenBSD `pledge` / Linux seccomp** — privileges can be dropped, never re-acquired. Safety that turns one way *by construction*. |
| Pure-function arbitration on replicated inputs | **State-machine replication / smart-contract determinism** — same inputs + deterministic function = same output on every replica, no coordination at decision time. |
| Refine predicate splitting | **Decision-tree induction** — when one leaf holds two separable populations, split on the most-separating feature; also how databases refine partitioning schemes. |

**Cisco-specific analogies (use at least two):**

- **Cisco Talos** — Cisco already runs the world's largest *human-curated* version of this loop:
  threat intelligence discovered at one point is validated centrally and pushed fleet-wide to every
  firewall and endpoint. The Cognition Fabric is that loop for *operational* insights,
  decentralized, with the validation made mechanical and the revocation path built in.
- **Cisco Catalyst Center (DNA Center) golden images & compliance drift** — Cisco networking
  already treats "known-good state" as a pinned artifact and continuously checks the fleet for
  drift against it. Our Sentinel golden suite is exactly that pattern applied to memory.
- **Meraki staged firmware rollouts** — cloud-managed fleets already adopt changes via staged
  rings with automatic rollback; our capsule lifecycle (shadow → active → revocable) speaks that
  same operational language, which is why an enterprise operator would trust it.
- **ThousandEyes** — continuous synthetic probing to detect regressions the user hasn't reported
  yet; the Sentinel is a synthetic prober for collective memory.
- Concrete story for the business close: a 3,000-branch enterprise hits a seasonal cert-expiry
  storm. Today, hundreds of site teams independently rediscover the same fix — or file the same
  escalation. With the fabric, the first site pays discovery cost once; the fix is jury-validated
  within seconds of sim time and every other branch solves at reuse cost, *with an audit trail
  compliance can read*. "Solve once per fleet."

---

## 10. Every number and why (`fabric/config.py` — open this file when asked)

| Constant | Value | Why this value |
|---|---|---|
| `JURY_K` / `QUORUM` | 3 / 2 | Smallest committee with a non-trivial quorum that a 5-node mesh can staff excluding the author. More = collusion resistance, cost = latency; it's one constant. |
| `HELDOUT_N` / `HELDOUT_WIN` | 8 / 6 | Enough episodes that a lucky-seeds capsule fails with high probability; ≥6/8 wins requires consistency, not one outlier. |
| `MIN_EFFECT` | 0.15 | A "breakthrough" is operationally defined: ≥15% median causal improvement on author-blind scenarios. Below that, not worth fleet propagation (churn guard). |
| `CLAIM_TOL` | 0.25 | Replay must reproduce ≥75% of the claimed effect — tolerates honest noise, kills fabrication. |
| `SHADOW_QUORUM_N` / `WIN` / `MIN_NODES` | 6 / 5 / 2 | Promotion needs 6 signed records with ≥5 wins from ≥2 *distinct* nodes — a single (possibly rogue) node can never self-promote a capsule. Zero invariant hits, always. |
| `AUTHOR_MIN_EPISODES` / `AUTHOR_MIN_EFFECT` | 4 / 0.20 | Authoring gate is *stricter* than the jury gate (0.20 > 0.15): borderline capsules shouldn't even reach the pipeline. |
| `PROBE_PERIOD` / `PROBE_TOL` | 60 / 0.10 | Sentinel cadence and one-sided KPI regression tolerance; `PROBE_TOL` is *defined from* `DRIFT_THRESHOLD` in code so the two names can never diverge. |
| `REP_AUTHOR_SLASH` / `REP_JUROR_SLASH` / `REP_ISOLATION_FLOOR` | 0.4 / 0.2 / 0.3 | One revoked capsule costs an author 0.4 → two put anyone below the 0.3 isolation floor. Jurors lose 0.2 per bad signature — skin in the game. |
| `REFINE_THRESHOLD` | 3 | Same overlap arbitrated 3 times = persistent, not incidental → Refine. |
| `CONTEXT_MAX_WIDTH_FRAC` | 0.8 | An interval covering ≥80% of a dimension's space reads as a wildcard → blocked (blast-radius cap). |
| `MAX_ATTEMPTS` / `REUSE_REFINE_MAX` | 12 / 2 | Discovery = bounded hill-climb ≤12 attempts; reuse = prior + ≤2 refinements. The gap is the ratchet. |
| Cost weights | 3.0·attempts + 0.075·time + 7.5·fp + 1.5·sla + 37.5·invariants | Attempts ≈ analyst toil; invariants priced so a healthy run has zero. M7 tuning scaled all weights by one factor (1.5×) — a uniform scale provably changes no percentage threshold anywhere (`cost(k·w) = k·cost(w)`). |

---

## 11. What is genuinely creative here (claim these explicitly)

1. **The Pawl / ratchet-monotonicity framing.** Naming the guardrail after the physical mechanism
   that gives the "ratchet effect" its name — and making safety one-way *by construction*
   (unsafe verbs don't exist in the vocabulary) rather than by review. A sellable one-sentence
   guarantee: *"the system can autonomously get stricter, and can only get looser with a signed
   human decision."*
2. **Promotion as a derived, monotone, coordination-free fact.** No announcement, no leader, no
   flapping — CALM-theorem thinking applied to a trust-lifecycle problem.
3. **Falsifiable-claim capsules — proof-carrying memory.** The insight ships with the experiment
   that proves it (seeds + cert + provenance). "The proof of verification propagates with the
   insight."
4. **Memory has CI, and memory has `bisect`.** Treating collective memory exactly like a codebase:
   golden regression suite, binary-search blame, surgical revert, blameful postmortem (slashing).
5. **A conflict is an underspecified context.** Refine turns conflicts into taxonomy improvements
   — the map gets sharper instead of a truth getting deleted.
6. **Safety moved out of the consistency layer.** The architectural move that makes AP affordable:
   invariants are local, so divergence can never cost safety, only optimality.
7. **The honest adversary demo.** The staged attack that *defeats our own admission* on stage, so
   the recovery machinery is proven rather than claimed.
8. **Determinism as a feature, not a test detail.** Byte-identical replays of everything,
   including the chaos — the demo is a controlled experiment the judges are free to re-run.

---

## 12. Your numbers card (verified on the final submission, 2026-07-16)

Setup facts: **110 tests, <1s**, fully offline after `make setup`; both demos byte-identical
across runs; combined live-pace runtime ≈ 2m10s inside the 12-minute runbook.

**demo-ratchet (Acts 0–2):** discovery_median **31.43** · reuse_median **13.59** · median insight
lead **6.5 sim-s** · **Lane A saved 40.52% vs Lane B** over 80 tasks · authored 5 · mesh-promoted
10 · non-author reuse at 4 sites · reputations: authors of promoted capsules 1.05, rest 1.0.

**demo-chaos (Act 3):** pre-warmed **12** ACTIVE capsules · blatant poison PAWL_BLOCKed with
reason · subtle poison + descendant reach ACTIVE honestly · DRIFT_ALARM on `fp_quarantines` (an
unclaimed KPI) within one probe period · bisect in **4 probes** over 12 suspects (⌈log₂ 12⌉) ·
Excision: **12 → 10** · rogue reputation **0.60** after slash · store retains all 12 adds incl.
tombstones (never-reset, on screen) · partition {a,b}|{c,d,e} → both islands promote locally →
heal → **identical arbitration on all 5 nodes** → Refine splits `traffic_gbps` at 5.5 → minority
cert demoted, majority cert stands.

**The two numbers off the blueprint's target band — own them before asked:**

- **reuse_median 13.59 vs target band 4–8.** Answer: "The band was written before a binding
  design decision: reuse cost is measured through the *same* solve path that measures every
  capsule's claim — one honest measurement path for jury replay, shadow, and live reuse. Reuse
  still evaluates the prior and up to two refinement attempts, and attempts dominate the cost
  model, which floors reuse cost around 12–14. We kept measurement honesty over hitting a
  cosmetic pre-registered band; the honest headline is the **ratio** — reuse ≈ 0.43× discovery —
  and the controlled 40.5% Lane A/B saving."
- **median lead 6.5 sim-s vs target 3–6.** Answer: "Lead time rose when we upgraded shadow staging
  from single-node to *mesh-wide*: promotion now requires signed records from at least two
  distinct nodes, so no node can self-promote. The extra half-tick is the price of that stronger
  guarantee — we bought trust with latency, knowingly, and it's one constant if the trade should
  go the other way."

---

## 13. Q&A drill (beyond DEFENCE.md §7 — the answers judges don't expect you to have)

**"Why Python, single process?"** The deliverable is architectural proof, offline, deterministic,
in a demo window. asyncio's single-threaded scheduler is what makes ordered, deterministic message
delivery cheap — the same reason FoundationDB tests its distributed store inside one deterministic
process. Every algorithm is transport-agnostic; the bus is the seam.

**"How does this scale to 10,000 sites?"** Propagation is O(capsules), not O(agent-pairs) — no
N². Gossip anti-entropy costs digest exchanges (Dynamo runs this at Amazon scale). Jury load is 3
replays per authored capsule regardless of mesh size. Sentinel probing is per-node over a pinned
suite. The one thing that grows with fleet is the *value* — recurrence × sites — which is the
business argument, not a cost.

**"What if the store grows forever?"** TTL expiry (EXPIRED stays readable, stops applying),
SUPERSEDED links when a better capsule wins a context, confidence decay. The fabric forgets
gracefully, by lifecycle — never by fiat.

**"What if the simulator itself is wrong?"** Then jury and shadow validate against a wrong world —
stated openly (BLUEPRINT §13). The production seam is explicit: conformance tests are the contract
with reality, and shadow staging would consume *real* traffic before ACTIVE. The architecture is
environment-agnostic; the simulator is the demo's stand-in, not a hidden assumption.

**"Two poisons at once / a poison masking another?"** Happens in our own demo: the second poison
wins arbitration over the first and masks it. Bisect probes halves *in isolation* so the culprit
window stays valid under masking; excise → re-probe loops until the golden suite is clean.

**"Author games the context to dodge hard held-out cases?"** Held-out scenarios are sampled from
the *declared* context — declaring a narrow context shrinks where the capsule is ever applied.
Gaming the exam shrinks your own blast radius; the incentive is self-defeating. And a full-width
context reads as a wildcard and is Pawl-blocked.

**"Sybil attack — one attacker, many identities?"** Out of the stated adversary model (few rogue
agents) and said honestly: identities in production are Phase 1's signed identities (mTLS/PKI), so
identity creation is an enterprise-controlled operation, not open enrollment. New identities also
start at reputation 1.0 with rate limits and can't self-promote (SHADOW_MIN_NODES ≥ 2, jury
excludes author).

**"Why is REVOKE trusted but promotion isn't announced?"** Sharp question, symmetric answer:
REVOKE is not trusted either — it's a *signed record carrying its probe report*, replicated in the
same OR-set, and tombstone dominance is deterministic (earliest wins on merge). Both promotion and
revocation are facts derived from replicated signed evidence; neither is anyone's word.

**"What stops an agent from just not adopting a capsule?"** Nothing — adoption is as-prior, and
that's a feature: a capsule is advice with evidence attached, and the local constitution always
wins. The economics make adoption rational (reuse ≈ 0.43× discovery); the invariants make
non-adoption safe.

**"Where exactly are humans?"** Two places by design: loosening any SAFETY/COMPLIANCE bound
requires a signed operator token (the pawl's one-way clause), and Excision reports are
human-readable audit artifacts. Humans stop being the network's only memory and become curators of
what the network is allowed to remember.

**"What's Phase-1 continuity, concretely?"** The registry (extended with incident dimensions),
the invariants, the priority lattice (SAFETY > COMPLIANCE > SLO > EFFICIENCY, lexicographic — no
efficiency weight can buy out safety), signed identities, and — verbatim — `arbitrate()`: the same
function that settled two-agent contract conflicts settles N-agent memory conflicts. Capsules were
designed in our Phase 1 submission as the Phase-2 seam.

**"Show me the thresholds." / "Show me the poison."** Open `fabric/config.py` (every constant,
commented) and `tests/test_dilemma_b.py` (the poison built through the genuine pipeline,
docstring explains the mechanism). Show code, not slides.

**"Prove the demo isn't scripted."** Everything flows through the genuine pipeline — the poison
really passes a real jury, the islands really promote through real shadow records — and the whole
run is seeded: offer to re-run it live; the output is byte-identical. The three dilemmas also
exist as executable tests (`tests/test_dilemma_{a,b,c}.py`) they can run themselves.

---

## 14. Never claim (the fastest way to lose a technical judge)

- Not **BFT** — adversary model is "few rogue authors/jurors," backstopped by the immune system.
- Not **production PKI** — HMAC keyring behind the same interface; not **VRF** — hash sortition.
- Not **real traffic** — stylized simulator; the sim-to-real seam is conformance tests + shadow.
- Not **real economics** — the claim is the controlled A/B *shape* (same seed, fabric on/off),
  never the absolute numbers.
- Not a **real network** — in-process bus; simulated network, real algorithms.

Lead every answer with the mechanism, close with the limit. The honest scoping is a strength —
every "not" above is a stated, one-line-upgradeable seam, and saying it first is what makes the
rest believable.
