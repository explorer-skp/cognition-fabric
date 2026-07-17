# DEMO_WALKTHROUGH — every line the terminal prints, explained

**Private prep. Companion to JUDGE_PREP.md.** That doc is the *why*; this one is the *what you're
looking at*. Every line below is quoted from the actual run (byte-identical every time, so these
are exactly tomorrow's lines), followed by what it means and — where it matters — the sentence to
say while pointing at it. **➤ HIGHLIGHT** marks the moments to slow down on.

---

## 0. How to read the screen (30 seconds of orientation)

- **`[  21.00]`** — the number in brackets is **simulated seconds**, not wall-clock. All logic runs
  on a sim clock; the pauses you feel in live mode are display pacing only, injected after the
  fact. If asked: "no logic ever reads the wall clock — that's part of why every run is
  byte-identical."
- **`bc20a2faa5`** — capsule IDs are the first 10 hex characters of the capsule's sha256
  content address. The ID *is* the content (like a git commit): tamper with one byte, the ID
  changes.
- **`… cold open complete`** — dim lines are act/beat markers; in live pace the script breathes
  2–3 s there so you can narrate.
- **`(scripted)`** — where a beat is staged narrative rather than emergent, the script *labels it*.
  Honesty is enforced down to the demo text.
- **The five TUI panels** (with `--tui`):
  - **Mesh** — columns Agent · Site · State · Reputation · Task: who's alive, what they're working
    on, current reputation.
  - **Fabric** — Id · Class · Claim · State · Confidence · Author: the capsule table. Watch states
    move SUBMITTED → CANDIDATE → ACTIVE (and REVOKED/QUARANTINED in chaos).
  - **Ratchet** — one sparkline per incident class; bar height = best-known cost, so the line
    **visibly steps down and never up**; `best=` shows the current best cost. This is the money
    chart — requirement 5, drawn.
  - **Economics** — Lane A (fabric ON) vs Lane B (fabric OFF) cumulative cost, `Saved: %`, median
    insight lead time.
  - **Event log** — color-coded: PAWL_BLOCK red, PROMOTED green, REVOKE magenta, REFINE cyan,
    REUSE dim green.

---

## 1. Pre-flight lines (judges may watch you run these)

**`make test` → `110 passed in ~1s`** — say: "110 tests, including the three dilemmas as
*executable tests* — `test_dilemma_a/b/c.py` — and a determinism test asserting byte-identical
output across runs."

**`make demo-smoke`** prints four lines:

```
# demo-smoke (M4): twin-lane repeat-incident storm, seed=424242, tasks=60 (Lane A fabric ON · Lane B fabric OFF)
cert_expiry_storm    discovery_median=  28.00  reuse_median=    -    ratio=   -   staircase=28.0→27.9
ddos_syn_flood       discovery_median=  31.58  reuse_median=  13.59  ratio= 0.43  staircase=31.6→13.4
# ratchet: authored=5  promoted(mesh)=15  non-author reuse sites=4  median insight lead=12.0 sim-s
# economics: Lane A cumulative=1289.4  Lane B cumulative=1865.4  saved=30.9%  ...
```

Line by line: the header names the fixed seed and the twin lanes (same 60 tasks, only variable is
fabric on/off — a controlled experiment). Per class: `discovery_median` = median cost of solving
*without* memory; `reuse_median` = median cost *with* a capsule prior; `ratio` = reuse/discovery
(0.43 = reuse costs less than half); `staircase` = best-known cost, first→latest.
`cert_expiry_storm` shows `-` for reuse here because in this short run no capsule for it cleared
the promotion path — the metrics never pretend.

---

## 2. `demo-ratchet` — beat by beat (Acts 0–2, ~40 s runtime)

### Act 0 — the amnesia problem (fabric OFF)

```
[   1.00] site-a spent 31.6 cost units learning ddos_syn_flood; site-b is about to spend 33.4
          learning it again — fabric is OFF, nothing carries over.
```
A **cost unit** blends analyst toil (attempts) and service impact (mitigation time, false
positives, SLA burn) — weights are in `fabric/config.py`. The point: two sites paying full
discovery price for the *same* incident class. This is the PS's opening complaint, live.

```
[   0.00] (scripted) site-d crashes and restarts — fabric OFF means there was never anything to
          lose. Multi-agent systems today are goldfish.
```
➤ **HIGHLIGHT** the word "goldfish" — it sets up the Act 1 payoff. Note the `(scripted)` label:
this beat is narrative framing, and the script says so.

### Act 1 — the first ratchet click (fabric ON)

```
[  15.00] AUTHOR: agent:site-a submits a capsule for ddos_syn_flood (claimed -56.4%) — an insight
          is not a message, it's a claim with seeds to replay it.
```
Where does **-56.4%** come from? Not typed in — the author *measured* it by replaying its own
recorded episodes through the same replay machinery jurors use. Authoring itself is gated: ≥4
recorded episodes and ≥20% self-measured improvement (stricter than the jury's 15%, so borderline
capsules never churn the pipeline).

```
[  15.00] JURY_VERDICT: ACCEPT — jurors ['agent:site-e', 'agent:site-d', 'agent:site-c'], chosen
          by the capsule's own hash; no one, including the author, could pick the committee.
```
➤ **HIGHLIGHT**: read the juror list and point out **site-a is not in it** — the author is
excluded by construction. The committee = the 3 agents with the lowest
`sha256(agent_id ‖ capsule_id ‖ epoch)`: unpredictable before the capsule exists (the capsule's
own hash seeds it), verifiable by anyone after. Behind this one ACCEPT line, each juror ran
counterfactual replay on the author's seeds, 8 author-blind held-out scenarios, and invariant
checks on every episode.

```
[  20.00] PROMOTED: capsule bc20a2faa5 reaches ACTIVE (confidence 1.00) — push-gossip fans it
          out; that latency is the Accelerator.
```
Between 15.00 and 20.00 sim-s the capsule was a CANDIDATE in **shadow**: nodes forked live tasks,
ran both branches, wrote signed shadow records. **Confidence 1.00** = it won every counted shadow
record. Promotion was **derived** — no node announced it; each node's own pure function flipped it
ACTIVE when the replicated records crossed the quorum (≥6 records, ≥2 distinct nodes, ≥5 wins,
0 invariant hits). If a judge asks anything here, this is your deepest well: *"promotion is
derived, never announced."*

```
[  22.00] REUSE: agent:site-c solves ddos_syn_flood at cost 15.4 using a capsule it never
          authored — same class, other site, cheap. Ratchet staircase steps down and stays down.
```
➤ **HIGHLIGHT**: 15.4 vs the 31.6 site-a paid — less than half, at a site that did none of the
learning. "Solve once per fleet." The residual cost isn't zero because reuse still *verifies*: it
evaluates the prior and allows up to 2 refinement attempts — memory is a starting point, never a
blind override.

```
[  48.00] agent:site-d restarts WITH memory: store reloaded intact from .state JSONL log — memory
          survives the crash. Next task of that class (ddos_syn_flood) solved at reuse cost 13.6.
          Same crash as Act 0. Different outcome. That delta is the Fabric.
```
➤ **HIGHLIGHT — the single most important 20 seconds of the demo.** Same site, same kind of crash
as Act 0. The store reloads from an append-only JSONL log on disk; the shadow ledger re-syncs from
peers via the *ordinary* gossip anti-entropy — there is no special recovery code path to distrust.
Pause here. Let it land.

### Act 2 — more classes, changing conditions

```
[  79.00] cert_expiry_storm: staircase 28.0 → 27.9 over 9 realized solves.
[  79.00] ddos_syn_flood: staircase 31.6 → 13.4 over 71 realized solves.
```
Two things to say. First, **9 vs 71 solves** — the class mix drifts over the run (requirement 1:
changing conditions). Second — and this is a trust moment, volunteer it — the cert-expiry
staircase barely moves: **the ratchet never invents improvement**. For that class the best rule
found is only marginally better than the default, so the staircase steps 0.1 and stops. A system
that always showed dramatic wins would deserve suspicion.

### The card (final four lines)

```
discovery_median=31.43  reuse_median=13.5916  median_lead_time=6.5  Lane A saved 40.52% vs Lane B over 80 tasks
authored=5  promoted(mesh)=10  non-author reuse sites=4
reputations after Act 1-2: {'agent:site-a': 1.05, 'agent:site-b': 1.05, 'agent:site-c': 1.0, ...}
```

- **discovery 31.43** — inside the blueprint's 25–35 target.
- **reuse 13.59** — above the blueprint's 4–8 aspiration; own it if asked: reuse is measured
  through the *same* honest solve path as every claim (one measurement path for jury, shadow, and
  live reuse), which floors it — the honest headline is the **ratio, 0.43×**, and the controlled
  **40.52% saving** (target band 40–50% ✓).
- **lead 6.5 sim-s** — a touch above the 3–6 aspiration because promotion now needs records from
  **two distinct nodes** (no self-promotion). "We bought trust with latency, knowingly."
- **authored=5, promoted(mesh)=10** — ➤ **HIGHLIGHT the arithmetic**: 5 capsules were authored, 2
  earned promotion, and `promoted(mesh)` counts **10 = 2 capsules × 5 nodes**, because *every node
  independently derives* the promotion from replicated records. The metric itself is proof there's
  no central announcer. (Also: 5 authored → 2 promoted means the pipeline visibly rejects.)
- **non-author reuse sites=4** — all four non-authoring sites reused; propagation is real.
- **reputations 1.05 / 1.0** — site-a and site-b each authored one promoted capsule: 1.0 + 0.05
  promotion credit. Reputation is *derived on read* from the event history — never stored, never
  gossiped, so it can't drift or be forged.

---

## 3. `demo-chaos` — beat by beat (Act 3, ~100 s runtime)

### Pre-warm

```
[  20.00] Fabric pre-warmed: 12 capsules ACTIVE.
```
A fresh seeded world where 12 capsules have already passed the genuine pipeline (not stubbed —
they went through real Pawl/jury/shadow during the pre-warm). site-e is flagged rogue.

### Blatant poison

```
[  21.00] PAWL_BLOCK: ratchet monotonicity: unknown action dimension 'allowlist_subnet' —
          control-plane vocabulary is registry-only
```
➤ **HIGHLIGHT — read the reason string aloud, then dissect it**: `ratchet monotonicity` is the
Pawl's check #2 by name. `unknown action dimension 'allowlist_subnet'` — the attack verb **does
not exist in the registry's action vocabulary at all**. The attack isn't detected; it's
*unrepresentable*. That is "safety by construction, not by review."

```
[  21.00] A ratchet without a pawl spins backward. The guardrail can autonomously get stricter,
          and can only get looser with a signed human decision.
```
The one-sentence security posture. An operator, an auditor, and a CISO all understand it.

### Subtle poison

```
[  22.00] Watch this one get in. It genuinely improves its claimed metric on scenarios it has
          never seen — admission is doing its job and it is not enough.
[  22.50] poison capsule 3598ef047e and its descendant 71e541234f are both ACTIVE.
```
➤ **HIGHLIGHT the honesty**: we are showing our own admission system being legitimately defeated —
the poison's claim is *true* (it really does cut solve cost); its harm is on a KPI it never
claimed. Note the **descendant**: another capsule was later derived from the poison — that's the
provenance DAG growing, and it's what makes the coming excision *surgical* instead of crude.

### Sentinel probe — memory's CI

```
[  24.00] DRIFT_ALARM: fp_quarantines 1 > baseline 0 × (1+0.1) on golden-02-ddos_syn_flood under
          capsule 3598ef047e05
[  24.00] DRIFT_ALARM: fp_quarantines 2 > baseline 0 × (1+0.1) on golden-03-ddos_syn_flood ...
[  24.00] DRIFT_ALARM: sla_burn 2.2937 > baseline 1.5437 × (1+0.1) on golden-03-ddos_syn_flood ...
```
Dissect one line fully: `golden-02-ddos_syn_flood` is pinned scenario #2 of the **12-scenario
golden suite** — fixed seeds, recorded clean baselines; the Sentinel replays the suite every 60
sim-seconds against whatever is currently ACTIVE. `fp_quarantines 1 > baseline 0 × (1+0.1)` — the
clean baseline had **zero** false-positive quarantines, now there's 1; tolerance is baseline ×
1.10. The tolerance is **one-sided**: `solve_cost` may drop freely (that's the fabric's purpose);
harm KPIs may not rise. ➤ **HIGHLIGHT**: `fp_quarantines` is a KPI **no capsule ever claimed** —
this is precisely the poison admission could not see, caught within one probe period. "Memory
has CI." Third line: a *second* KPI (`sla_burn`) confirms independently.

### Bisect

```
[  25.00] bisect step 1: clean with only this half enabled — culprit in the remainder; window narrowed to 6
[  25.00] bisect step 2: clean with only this half enabled — culprit in the remainder; window narrowed to 3
[  25.00] bisect step 3: clean with only this half enabled — culprit in the remainder; window narrowed to 2
[  25.00] bisect step 4: alarms with only this half enabled — culprit inside it; window narrowed to 1
[  25.00] culprit found in 4 probes (log₂ of 12 suspects).
```
Binary search over the 12 ACTIVE suspects: replay the golden suite with **only half enabled** —
clean ⇒ culprit is in the disabled remainder; alarming ⇒ it's inside. 12 → 6 → 3 → 2 → 1 in
⌈log₂ 12⌉ = 4 probes. ➤ **HIGHLIGHT**: "we bisect memory the way engineers bisect code — this is
`git bisect` pointed at collective memory." If probed on "only this half enabled": halves are
probed **in isolation** so one capsule can't mask another via arbitration during the search.

### Excision

```
[  26.00] REVOKE: 3598ef047e tombstoned — sentinel drift: fp_quarantines regression on the golden suite
[  26.00] QUARANTINE: 71e541234f — descendant of revoked 3598ef047e, re-jury required.
[  26.00] 12 capsules to 10. Not to zero. Surgical excision, not amnesia.
[  26.50] reputation(agent:site-e) = 0.60 (isolation floor 0.30) — jurors who signed the revoked
          capsule's cert are slashed too.
```
Four lines, four concepts. **REVOKE** is a *tombstone* — a signed record carrying the probe report
that justifies it; it replicates like any record, so the mistake stays auditable forever.
**QUARANTINE** — the descendant isn't deleted: it's sent back to jury *without the poisoned
ancestor's evidence*; if it stands on its own, it returns. **12 → 10** — ➤ **HIGHLIGHT**: the PS
said "without resetting collective memory"; this line answers it literally — exactly the poisoned
subtree is removed and the other ten capsules never blinked. **0.60** = 1.0 − 0.4 author slash;
say the follow-through: one more revoked capsule puts site-e below the 0.30 floor and the Pawl
auto-rejects everything it submits — and the *jurors who signed* the poison's certificate each
lost 0.2 as well. Skin in the game, like proof-of-stake slashing.

### Partition

```
[  28.00] Chaos splits the mesh: {site-a, site-b} | {site-c, site-d, site-e}. Both islands keep
          working; each learns a different fix for the same congestion class — valid for their
          local parameter regimes.
[  29.50] Island X: 5e96aa1fa8 ACTIVE locally. Island Y: b6f953d325 ACTIVE locally. Neither is
          visible on the other island — both sides are right, for their contexts.
```
This is CAP live: an **AP** system — both islands keep learning through the partition (a
ledger/consensus design would have frozen the minority island). Each island's capsule went through
the *real* pipeline within its island — real Pawl, real jury, real shadow records. The two
capsules are the PS's "conflicting fixes, both valid in different contexts", incarnate.

### Heal

```
[  30.00] Heal: stores union (CRDT — nothing to merge by construction); overlap detected; every
          node runs the same pure arbitrate() —  agent:site-a decides: b6f953d325  |
          agent:site-e decides: b6f953d325  — identical.
```
➤ **HIGHLIGHT the two decision reads side by side** — one node from each former island, same
answer. "Nothing to merge by construction": the store is a CRDT set of immutable records, so heal
is set union — no conflict resolution code ran. The *decision* consistency comes from every node
calling the same pure function on the same replicated inputs. "No split-brain behavior, even
while stores momentarily diverge."

### Refine

```
[  31.00] REFINE: same overlap arbitrated 3 times — split along 'traffic_gbps' at 5.5 — prior
          overlap fraction 0.09.
[  32.00] Both capsules survive, scoped along 'traffic_gbps': [5.5, 12.0] vs [1.0, 5.5]. Storage
          is eventual, meaning is scoped, decisions are deterministic — a conflict is an
          underspecified context, not a truth to delete.
```
"Arbitrated 3 times" = the persistence threshold (REFINE_THRESHOLD=3): once is incidental, three
times is a signal the context taxonomy is too coarse. `overlap fraction 0.09` = the system chose
`traffic_gbps` because the two capsules' evidence ranges overlap only 9% there — the dimension
where their evidence *separates most* — and split at 5.5. ➤ **HIGHLIGHT**: both capsules survive,
each re-validated for its sharpened scope. A last-writer-wins design would have deleted a valid
truth here. "We sharpen the map instead of deleting a truth."

### Minority-island cert demotion

```
[  32.50] 5e96aa1fa8's cert saw only ['agent:site-a', 'agent:site-b']'s 2 nodes at cert time —
          below the mesh majority — demoted to QUARANTINED pending re-jury. b6f953d325's cert saw
          3 nodes, a majority — stays ACTIVE, never silently authoritative on minority-island
          knowledge either way.
```
Every quorum certificate records its `partition_view` — which nodes were reachable when it was
signed. On heal: 2 nodes < the majority threshold of 3 (⌈(5+1)/2⌉) → the minority island's
promotion is *provisional* and goes back to jury mesh-wide; the majority island's (3 ≥ 3) stands.
One sentence and move on: "minority knowledge is preserved, never silently authoritative."

### The card

```
pre-warmed capsules: 12  after excision: 10  (removed exactly 2)
bisect probes: 4  reputation after excision: 0.60
store retains 12 adds incl. the tombstoned poison — never-reset assertion.
```
The last line is quietly the deepest: the *store* still holds all 12 add-records — the revoked
poison included, as a tombstoned, signed, audit-readable record. Removal changed what *applies*,
not what *happened*. "The fabric never forgets that it once believed something wrong — that's the
audit trail an enterprise actually wants."

---

## 4. The pointing cheat-sheet (the 8 moments that make it impressive)

1. **Juror list without the author in it** — sortition, live.
2. **PROMOTED with confidence 1.00** — "derived, never announced."
3. **REUSE at 15.4 by a site that never learned it** — the ratchet clicking.
4. **site-d's second crash, restart WITH memory** — the emotional core; pause on it.
5. **The PAWL_BLOCK reason string** — read it aloud; "unrepresentable, not detected."
6. **DRIFT_ALARM on `fp_quarantines`** — a KPI nobody claimed; "memory has CI."
7. **"12 to 10. Not to zero."** — the PS answered verbatim.
8. **Two nodes' identical arbitrate() lines after heal** — no split-brain, no coordinator.

## 5. "What does that number mean?" traps, pre-answered

- **Why is the crash line stamped `[0.00]`?** It's a scripted framing beat in Act 0 (and labeled
  `(scripted)`); the *real* crash-with-memory at `[48.00]` in Act 1 is the emergent one.
- **Why does cert_expiry's staircase barely move (28.0 → 27.9)?** Because no dramatically better
  rule exists for it — the ratchet only records improvement that was actually measured. Honesty,
  not weakness.
- **Why confidence exactly 1.00?** The capsule won every shadow record that counted toward its
  quorum. Confidence = win fraction; it feeds arbitration's weighting later.
- **Why is site-e at 0.60 still allowed to submit?** The isolation floor is 0.30 — one revocation
  costs 0.4. The design intentionally doesn't death-penalty a single mistake; a *pattern* (two
  revocations) isolates. Meanwhile its rate limit already shrank (submissions scale with
  reputation).
- **Why 10 promoted from 5 authored?** 2 capsules × 5 nodes, each node deriving promotion
  independently — and 3 of 5 authored capsules never made it. The funnel is real.
- **Why reuse ~13, not ~5? / Why lead 6.5?** See the card section above (§2) — measurement
  honesty and the two-node promotion quorum, respectively. Both answers are in
  JUDGE_PREP.md §12 word-for-word.
