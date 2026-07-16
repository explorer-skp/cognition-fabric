# Cognition Fabric

**Team Beacon · Code With Cisco Phase 2**

A memory layer for a mesh of autonomous incident-response agents. Phase 1 gave agents a shared
language (a registry, invariants, and `arbitrate()`); Phase 2 gives them a shared, validated,
revocable memory — the *Cognition Fabric* — so an insight discovered once at one site is replayed,
proven, and reused everywhere else, without ever letting an agent apply an action its own
constitution forbids.

The core claim: **memory has to earn trust the way code earns trust** — replayed, not just
asserted — and it needs an immune system, not just a border wall, because admission validates a
*claim*, and claims don't cover everything a system needs to be right about.

## Quickstart

```bash
uv venv --python 3.11 && uv pip install -e ".[dev]"   # or: make setup
make test              # full suite, < 1s
make demo-smoke        # ≤20s CI gate: twin-lane storm, byte-identical across runs
make demo-ratchet      # RUNBOOK Acts 0-2: the amnesia problem → the first ratchet click
make demo-chaos        # RUNBOOK Act 3: poison, Sentinel, bisect, Excision
```

Both demo scripts default to plain, deterministic text output (diffable, no terminal required).
Add `--tui` for the live `rich` dashboard, `--pace=live` to insert the RUNBOOK's narration beats
for a human audience, and `--theme=high-contrast` for a washed-out projector.

## The three dilemmas

- **Innovation vs. Hallucination** (`tests/test_dilemma_a.py`) — a capsule's claim is never
  believed, it is replayed: fabricated numbers die at counterfactual replay of the author's own
  seeds, cherry-picked claims die at author-blind held-out scenarios, true-but-unsafe optimizations
  die at invariant/conformance — only an honestly-better capsule reaches ACTIVE, with a quorum
  certificate that travels with the insight.
- **Drift & Poisoning** (`tests/test_dilemma_b.py`) — admission validates the claim; Sentinels
  validate the system. A subtle poison can genuinely improve its claimed metric and pass the
  border honestly, then regress an off-claim KPI a golden-scenario Sentinel probe catches within
  one probe period; bisect finds the exact culprit; Excision tombstones it and quarantines its
  derived descendants — the capsule count drops by exactly the poisoned subtree, never to zero.
  Collective memory is retained, not reset.
- **Consistency** (BLUEPRINT §7) — storage is eventually consistent (CRDT gossip merge, milestone
  M4); decisions are deterministic (`arbitrate()`, milestone M4). The third leg — meaning is
  scoped, via partition-driven Refine — is milestone M6, which this build does not implement (see
  "Known gaps" below); `tests/test_dilemma_c.py` does not exist yet.

## Milestones built this session

M0–M5 and M7 (`docs/PROGRESS.md` has the full per-session log). **M6 was deliberately skipped** —
BLUEPRINT's build order is strictly M0→M7, and this session jumped from M5 to M7 on explicit
instruction rather than build the chaos injector + partition semantics. Concretely, that means:

- No `chaos/injector.py`, no partition/heal/Refine, no minority-cert demotion.
- `demo-chaos`'s Act 3 stops after Excision and prints an explicit note at the point where
  partition/heal would run, rather than faking the beat.
- `docs/DEMO_RUNBOOK.md`'s Act 3 partition/heal beats (8:45–10:15) are not reproduced live.

Everything else in the RUNBOOK — the amnesia problem, the first ratchet click, crash/reload with
memory (a *live* re-proof of milestone M2's persistence guarantee inside a running mesh), the
poison/Sentinel/bisect/Excision sequence — is real, and runs on fixed seeds byte-identically across
runs.

## Documentation

- `docs/BLUEPRINT.md` — architecture, schemas, algorithms, thresholds, vocabulary (source of truth).
- `docs/DEFENCE.md` — why each design choice exists; the Q&A bank for judges.
- `docs/DEMO_RUNBOOK.md` — the scripted 10–15 minute live demo this code delivers (modulo the M6
  gap above).
- `docs/PROGRESS.md` — the session-by-session build log; the only memory between sessions.
- `CLAUDE.md` — the engineering constitution this codebase was built under (determinism rules,
  code style, the milestone build order, the session protocol).

## Honest scoping

Transport is simulated (in-process); the algorithms above it — gossip, sortition, quorum certs,
CRDT merge, Sentinel probes, bisect, Excision — are real and would ride any transport. Signing is
an HMAC keyring behind the same interface real PKI would use. Sortition is hash-based, not
VRF-based. The adversary model is "few rogue authors/jurors," not arbitrary Byzantine majority.
Full list: BLUEPRINT §13.
