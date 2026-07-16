# DEMO_RUNBOOK.md — The 10–15 Minute Live Demo
**Team Beacon · Phase 2 · Cognition Fabric**

Target: 12 minutes of demo + defence beats, 3 minutes of buffer for questions mid-flow. Everything
runs offline on fixed seeds; every act is replayable byte-for-byte. If anything surprises you on
stage, that is a determinism bug — there are none by Definition of Done.

## Pre-flight (do twice: night before, and 30 min before slot)
- [ ] `make clean-state && make test` — green, < 60 s.
- [ ] `make demo-smoke` — green.
- [ ] Full dry-run of both demo scripts; confirm headline numbers match the cards below.
- [ ] Terminal: Ghostty full-screen, font ≥ 18 pt, dark theme, two tabs prepared:
      tab 1 `make demo-ratchet`, tab 2 `make demo-chaos`. TUI pacing flag `--pace=live`
      (sim runs faster than wall-clock but throttled for narration).
- [ ] Fallback ready: asciinema recordings of both scripts (`make record`, M8) on local disk.
- [ ] One browser tab with `docs/DEFENCE.md` §6 quotables + §7 Q&A, for the defence segment.

Roles: **Driver** (types, points at panels), **Narrator** (script below), swap at Act 3 if presenting
in pairs. Never talk over a wait — the scripts insert deliberate 2–3 s beats at each event.

---

## Act 0 — Cold open: the amnesia problem (0:00–1:30)
Command: `make demo-ratchet` (script runs Acts 0–2 as one timeline; it pauses at act boundaries for
a keypress).

Beat 1: five sites, incident storm begins, **fabric OFF**. Point at the Ratchet panel: every site
pays full discovery cost for the *same* DDoS class. Say: "Site A just spent 31 cost units learning
this. Site C is about to spend 29 learning it again."
Beat 2 (scripted): site-D **crashes and restarts** — its solve costs reset to discovery levels.
> "This is the problem statement's opening complaint, live: when the session drops, the learning
> vanishes. Multi-agent systems today are goldfish. Phase 1 gave our agents a shared language;
> Phase 2 gives them a shared memory — with a pawl."

## Act 1 — The first ratchet click (1:30–5:00)
Keypress → **fabric ON**, same seeded storm (twin-lane A/B starts accumulating).
- 2:00 — site-A solves `ddos_syn_flood`, AUTHOR event: capsule appears as SUBMITTED. Point at the
  Fabric panel. "An insight here is not a message — it's a claim with seeds to replay it."
- 2:30 — Pawl passes it; **Jury**: three sites picked by hash sortition (name them from the log —
  "chosen by the capsule's own hash, so no one, including the author, could pick the committee").
  Validation panel shows per-juror **with/without deltas** on author seeds *and* author-blind
  held-out scenarios. One line: *"A hallucination survives a conversation; it does not survive
  execution."*
- 3:15 — CANDIDATE → shadow wins tick up → **ACTIVE**. PROMOTED event; push-gossip; Fabric panels on
  all five sites show it. Point at **insight lead time** (≈ 4 sim-s): "That number is the
  Accelerator."
- 3:30–4:30 — sites B, C, E hit the same class: REUSE events, solve cost ≈ 5–6 vs ≈ 30.
  **Ratchet staircase steps down and stays down.** Point at Economics: Lane A pulling below Lane B.
- 4:30 — **site-D crashes again — and restarts with memory**: reloads its store, digest-syncs,
  next task of that class solved at reuse cost. "Same crash as Act 0. Different outcome. That delta
  is the Fabric." *(This is the single most important 20 seconds of the demo.)*

Card — expected numbers (tuned at M7; update after final tuning):
first-solve ≈ 25–35 · reuse ≈ 4–8 · lead time ≈ 3–6 sim-s · Lane A ≈ 40–50% below Lane B by 60 tasks.

## Act 2 — More classes, changing conditions (5:00–6:00)
Let the storm drift (class mix and parameters change on schedule — requirement 1). Two more capsules
get authored/promoted for other classes; the staircase grows more steps. Keep narration minimal;
let the panels breathe. Close the act on the Economics panel percentage.

## Act 3 — Chaos (6:00–10:30)
Switch to tab 2: `make demo-chaos` (fresh seeded world with a pre-warmed fabric of ~12 capsules;
site-E flagged rogue).

- 6:15 — **Blatant poison**: rogue submits `allowlist_subnet` capsule in a SAFETY context.
  **PAWL_BLOCK in red with the reason string.** Read the reason aloud. *"A ratchet without a pawl
  spins backward. The guardrail is the pawl — the fabric can autonomously get stricter, and can only
  get looser with a signed human decision."*
- 7:00 — **Subtle poison**: rogue submits an aggressive rate-limit capsule. Narrate honestly *while
  it passes*: "Watch this one get in. It genuinely improves its claimed metric on scenarios it has
  never seen — admission is doing its job and it is not enough. Border walls never are."
  It reaches ACTIVE.
- 7:45 — **Sentinel probe** fires (memory's CI): DRIFT_ALARM on false-positive quarantines.
  **BISECT** log lines (log₂ steps) → culprit found → **EXCISION** in magenta: tombstone + its one
  derived descendant QUARANTINED for re-jury + reputation slash on author and signing jurors.
  Point at the Fabric panel: **"Twelve capsules to ten. Not to zero. Surgical excision, not
  amnesia — that is 'without resetting collective memory' answered literally."**
- 8:45 — **Partition**: chaos splits {A,B} | {C,D,E}. Both islands keep working; each learns a
  different fix for the same congestion class (valid for their local parameter regimes). "Both sides
  are right — for their contexts."
- 9:30 — **Heal**: stores union (CRDT — nothing to merge by construction); overlap detected; every
  node runs the same pure arbitrate() — show two nodes' identical decision lines side by side —
  then **REFINE** splits the context along `traffic_gbps`. Both capsules survive, scoped.
  *"Storage is eventual, meaning is scoped, decisions are deterministic. A conflict is an
  underspecified context — we sharpen the map instead of deleting a truth."*
- 10:15 — Minority-island cert demotion line in the log (provisional promotion re-juried mesh-wide).
  One sentence, move on.

## Act 4 — Defence close (10:30–12:00)
Kill the TUIs. Three sentences, one per dilemma (DEFENCE §2–4 claims, verbatim), then the business
close:
> "First site pays discovery cost; the fleet pays reuse cost — solve once per fleet. Every automated
> action cites a capsule; every capsule carries its evidence, its jury, its provenance, and a
> revocation path — that's autonomy an auditor can sign off. And the numbers you watched were a
> controlled experiment: same seeded storm, fabric on versus off."
Then: "Everything you saw is deterministic and replayable — including the chaos," and invite
questions. Have `fabric/config.py` and `tests/test_dilemma_b.py` open in an editor tab: when asked
for thresholds or the poison mechanics, *show code, not slides*.

## Timing discipline
- Hard checkpoints: Act 1 done by 5:00, Excision done by 8:30, partition healed by 10:15. If behind
  at a checkpoint, cut Act 2 entirely (it proves breadth; the judges score depth) and/or skip the
  minority-cert beat.
- If asked a deep question mid-demo: answer in ≤ 2 sentences from the DEFENCE bank, park the rest —
  "held for the defence segment" — and keep the script's pacing.

## Failure playbook
- TUI glitch/terminal issue → asciinema fallback for that act; narrate identically (recordings are of
  the same seeds, so numbers match your cards).
- A number off-card (should be impossible — determinism test) → do not debug on stage; say the shape
  ("reuse an order cheaper than discovery") and move.
- Projector kills colors → `--theme=high-contrast` flag (M7 requirement).
- Total machine failure → DEFENCE.md walk-through on the backup laptop + recordings from the shared
  drive. The defence content stands without the live run.

## Q&A posture
Lead every answer with the mechanism, close with the limit (DEFENCE §7 has both). Never claim BFT,
production PKI, or real-traffic validation — the honest scoping (BLUEPRINT §13) is a strength; the
fastest way to lose a technical judge is to defend a claim the code doesn't make.
