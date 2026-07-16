# Cognition State Protocol (CSP) — Phase 1 Design Ideation

**Team Beacon · Code With Cisco 2026 · PS-1: Agentic Superintelligence Networks**

This is our thinking document, not the submission. It is organized the way the judging is framed: as a chain of questions we asked ourselves, the options we weighed, what we chose, and what each choice costs us. Section 13 maps this material onto the five submission answers, and Section 8 keeps a door open for the unrevealed Phase 2.

---

## 0. The problem in one paragraph, from first principles

TCP guarantees your bytes arrive intact and in order. TLS guarantees nobody read or modified them on the way. Nothing in the stack guarantees that the *meaning* arrived intact, or that the two endpoints' *goals* are compatible. Two competent agents can exchange perfectly valid, perfectly encrypted JSON and still wreck each other's work, because one is optimizing for throughput and the other for inspection depth, and neither has a machine-checkable way to discover that, bound it, or resolve it. That missing layer — meaning and goal compatibility as a network primitive — is the "cognitive layer" the problem statement is pointing at, and the Cognition State Protocol (CSP) is our proposal for it.

The single most important reframe we made early, and the one that shaped everything below: **we are not synchronizing minds, we are synchronizing contracts.** Full mental-state synchronization between heterogeneous agents is impossible (their internals aren't comparable), expensive (it's what bloats the network with token histories), and dangerous (it's the leak). What Agent A actually needs from Agent B is never "what are you thinking" — it is "what will you guarantee, for how long, and what happens if you stop." A contract is small, typed, signable, checkable, and expirable. A mind is none of those things.

## 1. Question zero: what does one agent actually need to know about another?

We decomposed the problem statement into three sub-problems, which map one-to-one onto submission Questions 1, 2, and 3:

1. **Representation** — how do you state what you want, compactly and unambiguously, across different model architectures?
2. **Negotiation** — what happens when two stated wants cannot both hold, and how do you guarantee it ends?
3. **Trust** — how do the first two happen without leaking what you must not leak?

The networking analogy that guided us throughout is **BGP, not telepathy**. Routers never share their configurations or internal tables with each other; they advertise routes with a small set of typed attributes, and each router applies local policy to what it hears. The internet scales because the advertisement is small, standardized, and policy-mediated — not because routers understand each other deeply. CSP applies the same discipline one layer up: agents advertise small, typed, signed **intent envelopes** — never prompts, weights, or reasoning traces — and apply local policy to what they hear.

One clarification on scope, since the problem statement warns against chatbot-shaped thinking: LLMs (or any decision model) sit *behind* CSP, translating an agent's private goals into protocol objects and translating agreed contracts back into behavior. The protocol itself is deterministic end to end. Our one-line summary of the architecture: **models propose, the protocol disposes.** Everything that must terminate, verify, or be audited lives in the protocol; everything creative or private stays inside the agent.

## 2. Representing intent — the state synchronization problem (feeds Answer 1)

### 2.1 The question we asked

How do two agents built on entirely different architectures communicate "deep semantic intent" in messages measured in hundreds of bytes, not tens of thousands of tokens — and in a form the receiver can *compute over*, not merely read?

### 2.2 Why the naive answer fails

The obvious approach is to exchange natural language: prompt histories, goal descriptions, chain-of-thought summaries. It fails on four independent axes. Cost grows with conversation length, which is exactly the "token-heavy prompt histories" the problem statement forbids. Meaning depends on the reader — two different models parse the same sentence differently, which is precisely where "hallucinated boundaries" come from. Nothing is verifiable — there is no mechanical test for "we have now agreed." And it leaks maximally — free text carries your reasoning style, your internal vocabulary, your business context, all of it.

### 2.3 The options we weighed

**Option A — shared embedding vectors.** Compact and superficially "semantic," but embedding spaces are architecture-specific. Agent A's vector means nothing in Agent B's space without a co-trained projection, which is a pairwise coupling an internet-scale protocol cannot afford (N agents would need N² projectors, retrained whenever anyone fine-tunes). Vectors are also opaque: you cannot audit one, cannot check an invariant against one, and cannot do the arithmetic that negotiation actually needs, like "is your minimum below my maximum."

**Option B — semantic graphs.** Expressive, and the research literature loves them, but there is no canonical form (the same meaning has many graph encodings), comparing two intents becomes a subgraph-matching problem, and size is unbounded. A good knowledge representation is not automatically a good wire protocol.

**Option C — typed, declarative intent descriptors over a shared dimension registry (chosen).** Intent is expressed as a position in a small, versioned, shared vocabulary of *operational dimensions* — things like `inspection_depth`, `added_latency_ms`, `sampled_fraction`, `risk_budget`. An agent declares which dimensions it is pushing and in which direction, what region of each dimension it can live with, and which constraints are absolutely non-negotiable. Serialized as protobuf or CBOR, this is a few hundred bytes.

### 2.4 What "intent" means in CSP, precisely

An **IntentDescriptor** contains:

- `agent_id`, `epoch`, `registry_version` — who, which version of their state, which vocabulary
- `objectives` — a list of `{dimension, direction (min|max), weight}` entries: what the agent is optimizing
- `feasible` — per dimension, an interval or enumerated set the agent can accept
- `invariants` — hard predicates no agreement may ever violate (the agent's constitution)
- `priority_class` per objective — one of `SAFETY > COMPLIANCE > SLO > EFFICIENCY` (see §4.4)
- `elasticity` — per dimension, how far the agent is willing to concede, in quantized steps. **Sealed, not advertised** (see §5.4a): the descriptor carries only its salted commitment; the value opens when the selection rule runs at signing, or at arbitration
- `signature` — the whole descriptor is signed by the agent's key

The decisive consequence of this representation: **negotiation becomes geometry.** Two intents are compatible if and only if the intersection of their feasible regions is non-empty. That is interval arithmetic — deterministic, cheap, auditable, and identical no matter which model architecture computed the descriptor. We traded expressive freedom for computability on purpose; Section 9 records that trade.

### 2.5 Keeping the wire cold

Beyond the representation itself, three mechanics keep payloads small. First, agents exchange **deltas against epochs**, not full state — after the first ADVERTISE, updates carry only the dimensions that changed. Second, anything large (capability manifests, policy documents) is **content-addressed**: the wire carries a hash, and the peer fetches the blob only if it has never seen that hash. Third, CSP is strictly a **control plane** — the actual task traffic between agents flows on a separate data plane that the contract governs but never travels through. Ballpark budget: HELLO ≈ 200 B, ADVERTISE ≈ 600 B, a full signed contract ≈ 1 KB. The entire handshake costs less than one paragraph of prompt history.

### 2.6 The cost we accepted

A shared registry means both agents must agree on what `inspection_depth` *means*. This is the classic ontology problem and we did not pretend to solve it — we contained it. The registry is versioned and its version is negotiated in HELLO; each dimension carries a unit, a measurement procedure, and a **conformance test**, so vocabulary agreement is verified against observables rather than assumed — and heartbeat telemetry checks contract compliance against the *same* test that defines the word; unknown or experimental dimensions are namespaced (`x-…`) and ignorable by rule, so extension never breaks interop; and governance of the registry is explicitly punted to an IANA/IETF-shaped process (§12), which is a familiar and honest answer for a protocol pitch. The trade is real: CSP can only negotiate what the registry can express. Our defense is that BGP has the same property and runs the internet.

## 3. Discovery, identity, and the order of operations

A question we almost skipped, and are glad we didn't: **do you authenticate before or after you advertise intent?** The answer became a design rule — *trust before truth*. The sequence is DISCOVER → AUTH → ADVERTISE, and the information revealed grows strictly with the stage. Discovery messages carry only a coarse capability class ("I am a traffic-policy agent, registry v3"), nothing about goals. Authentication establishes mutual identity — per-agent keypairs with SPIFFE/DID-style identifiers, capability claims signed by the operating organization, and an optional attestation hook (TEE quote) for claiming things like "my policy engine is the one my operator published." Only after both identities verify does any intent move. The ordering is itself a security control: nothing semantically meaningful is ever said to an unauthenticated peer.

For the prototype we run a self-signed CA and stub attestation; the seam where real attestation plugs in is explicit. (Being clear about prototype-vs-production at each layer is a theme — see §11.)

## 4. Conflict resolution mechanics (feeds Answer 2)

### 4.1 The question we asked

The feasible regions don't intersect — the fast agent's ceiling is below the auditor's floor. With no human and no central coordinator, how do you *guarantee* the system arrives at a bounded decision rather than an endless negotiation loop? "Usually converges" is not a protocol property; "provably terminates" is.

### 4.2 Why "let the models talk it out" fails

The tempting design is to have the two agents' LLMs argue until one persuades the other. We rejected it early and it's worth recording why: there is no termination guarantee (persuasion can loop forever), it is vulnerable to exactly the adversarial pressure the brief warns about (a persuasion channel is a prompt-injection channel — conversely, CSP's closed registry vocabulary leaves **no free-text channel between agents at all**, so cross-agent prompt injection is structurally impossible rather than filtered; we now say this explicitly in Answer 3, because it is a headline property, not a side effect), it burns tokens (recreating the payload-bloat problem in the control plane), and it is non-reproducible — you cannot explain to an auditor *why* agreement happened, only that it did.

### 4.3 What we chose: an escalation pipeline from cheap to decisive

**Stage 0 — intersection check (zero rounds, deterministic).** Compute the intersection of the two feasible regions. Non-empty → select the contract point by the standard rule (§4.5) → done. We expect most encounters to end here; the negotiation machinery below is the exception path, not the common case.

**Stage 1 — monotonic concession, hard-capped at K rounds.** If the intersection is empty, agents enter at most K rounds (K = 4 in the prototype). Each round, each agent must either accept the standing counter-proposal or concede by at least ε (the public, quantized minimum step) in at least one disputed dimension, within its sealed elasticity. Concessions are *monotone* — once made, never retracted. Termination is then arithmetic, not hope: utilities range over a bounded set, every round moves at least ε, so the process ends within (range ⁄ ε) rounds — and K caps it regardless of what agents do. This is the classic monotonic-concession protocol from negotiation theory; our contribution is quantizing concessions so "at least ε" is mechanically checkable by the peer, not asserted.

**Stage 2 — deterministic arbitration, with no arbiter.** If the region is still empty after K rounds, both agents evaluate the *same pure function* over inputs both parties committed to before Stage 1 began (commit-reveal, §5.4). The function: (1) per disputed dimension, the higher priority class wins outright — SAFETY beats COMPLIANCE beats SLO beats EFFICIENCY; (2) among equal classes, take the elasticity-weighted midpoint of the final standing offers (a Nash-bargaining-flavored point that splits the remaining gap in proportion to declared flexibility); (3) any residual tie breaks on `hash(nonce_A ‖ nonce_B)` — deterministic, unbiased, and unguessable in advance because each side's nonce was committed blind. Because the function is pure and its inputs are signed commitments, both sides compute the *identical* result independently. This is the trick that removes the central coordinator: arbitration without an arbitrator.

**Stage 3 — safe fallback.** If arbitration inputs fail verification — a reveal doesn't match its commitment, a signature fails, a peer times out — both agents drop to a pre-declared safe default contract: the most conservative point in the space (in the running example: full inspection, minimum throughput, short TTL). The design principle is that **liveness never buys safety**: the worst failure mode of CSP is *slow*, never *unguarded*.

### 4.4 Why a priority lattice, and why it isn't a cop-out

A pure numeric weighted sum has a fatal flaw: a large enough efficiency weight can buy out a safety constraint. Making the classes *lexicographic* — no amount of EFFICIENCY weight can ever outvote a SAFETY-class term — closes that hole by construction rather than by tuning. The classes are deliberately few and coarse: they are the protocol's constitution, not its knobs. Class membership is declared in the IntentDescriptor and signed, so an agent claiming SAFETY for a throughput goal is committing verifiable fraud against its own attestation — a reputation event (§5.6), not a silent win.

### 4.5 Even agreement needs a rule

A subtle point we caught in review: when the intersection is *non-empty*, which point inside it becomes the contract? If that choice is itself negotiable, you've reintroduced the loop you just removed. So Stage 0 uses the same elasticity-weighted midpoint function as Stage 2. One selection rule everywhere; nothing left to argue about.

### 4.6 Stability over time: contracts are leases

A contract carries a TTL and explicit renegotiation triggers with **hysteresis bands**: renegotiation fires only when a monitored metric leaves its band and stays out for a dwell time. This is stolen directly from route-flap damping in BGP, and for the same reason — without damping, two agents on a noisy boundary would renegotiate forever, which is the slow-motion version of the endless loop. Between renegotiations, both agents' behavior is bounded by the standing contract, and heartbeats carry telemetry against it.

### 4.7 Why we can defend this in review

Four properties, each checkable: **terminating** (bounded rounds plus a deterministic tail — there is no input on which CSP fails to produce a decision); **reproducible** (pure functions over signed inputs mean any third party can replay the negotiation from the audit log and get the same contract); **Pareto-respecting** (monotonic concession never moves to an outcome both parties rank worse); **fail-safe** (every abnormal path terminates in the conservative fallback, not in deadlock or in an unguarded state).

## 5. The semantic security gap and minimum disclosure (feeds Answer 3)

### 5.1 Naming the gap precisely

TLS secures the channel. Nothing in the stack secures the *decision about what to say*. In agent-to-agent negotiation, the payload itself is the secret: your constraint boundaries reveal your capacity, your risk appetite, your compliance posture, your business rules. The characteristic attacks here are semantic — a peer running the protocol *honestly* can still learn far too much simply by negotiating with you cleverly. That is the gap CSP has to close, and it cannot be closed with more encryption; it needs structural and policy controls at the layer where meaning lives.

### 5.2 The threat list we designed against

1. **Direct leakage** — prompts, weights, reasoning traces, or business context traveling in payloads.
2. **Boundary probing** — a peer binary-searches your thresholds through repeated offers or repeated negotiations.
3. **Concession-dynamics inference** — the *pattern* of your concessions reveals the shape of your internal utility function.
4. **Impersonation and sybils** — fake peers harvesting intent, or flooding negotiation.
5. **Replay** — resurrecting a stale, more permissive contract.
6. **Adaptive lying in arbitration** — restating your "true" limits after seeing the peer's position.
7. **Onward leakage** — anything shared here escaping through Phase-2-style knowledge broadcast later.
8. **Envelope inference from public elasticity** (self-inflicted; caught in final review) — if elasticity is *advertised*, then `advertised bound ± elasticity` reveals the reachable envelope. In our own worked example it pinpointed the landing exactly: Flow ceiling 2 + elasticity 1 = 3, Warden floor 4 − elasticity 1 = 3 — an observer of the two ADVERTISEs could compute the deal before any concession happened, making Stage 1 theater and the sealed reservation commitments pointless. Fix: elasticity moved into the salted COMMIT (§5.4a); only the minimum step ε stays public.

### 5.3 The disclosure ladder (structural control)

Information moves in strictly increasing levels, each gated: **L0** capability class only, at discovery. **L1** *quantized* feasible intervals, at ADVERTISE — quantization means a peer learns which band your threshold is in, never the exact value, which blunts binary search to a coarse and rate-limited game. **L2** feasibility verdicts ("acceptable / not acceptable") during negotiation — answers about *proposals*, not statements about *yourself*. **L3** committed arbitration inputs, revealed only if Stage 2 is actually reached, and only for the dimensions actually in dispute. Never on the wire at any level: utility function internals, prompts, chains of thought, model parameters, or anything not in the registry vocabulary. Each level transition is gated by **policy-as-code** (an OPA-style engine evaluating "may I disclose X to peer Y at trust level Z"), so disclosure is an auditable rule, never a model's judgment call in the moment.

### 5.4 Commit-reveal (cryptographic control)

Before Stage 1 begins, each agent sends a salted hash of its true reservation values and elasticity. If Stage 2 is reached, values are revealed and checked against the commitments. An agent can still lie — but it must lie *in advance and blind*, before seeing the peer's position, which destroys the profitable adaptive lie (threat 6) and converts dishonesty into something detectable across encounters. Nonces for tie-breaking are committed the same way, which is what makes the tie-break unguessable.

### 5.4a Sealed elasticity (closing threat 8)

Elasticity has two consumers: the peer's *verification* that each concession moves at least ε (needs only the public step size, not the budget), and the *selection/arbitration rule* (needs the value — but only after the region is fixed or arbitration is reached, when revealing it is cheap). So nothing requires elasticity to be public during negotiation. It now travels as a salted hash inside COMMIT, alongside the reservation values, and is opened and checked against its commitment exactly when a rule consumes it. Lying about it is therefore blind, pre-registered, and detectable — the same property commit-reveal already gives reservation values. What each side observes mid-negotiation shrinks to: quantized intervals, per-round steps, and verdicts.

### 5.5 The upgrade path we designed the seam for

The core private comparison in CSP — "is my minimum below your maximum, without either of us revealing our number" — is *literally* Yao's millionaires' problem, one of the founding problems of secure two-party computation. Range proofs and 2PC comparison are drop-in replacements at exactly one interface (the feasibility check), and the message flow does not change. The prototype ships quantization plus commit-reveal; the submission says so plainly, because "we designed the seam and can name the primitive" is technically credible, while "we implemented ZKP during a hackathon" is not.

### 5.6 Behavioral and policy controls

Per-peer negotiation rate limits and a **disclosure budget metered in bits** defeat probing at the protocol level: because every dimension is quantized into 2^k buckets, leakage is *computable* — a yes/no feasibility verdict costs at most 1 bit, an advertised interval at most 2k bits per dimension — so the budget is an information bound, not a request counter, and a peer that keeps re-negotiating to walk your boundaries exhausts a stated number of bits rather than the anomaly-detection level, though offer-pattern anomaly flags exist too. Every disclosure event is written to an append-only, hash-chained audit log. And every verified reveal and every honored-or-breached contract feeds a per-peer **reputation score** — which Phase 1 uses to gate disclosure levels, and which Phase 2 will want anyway as the trust weight for knowledge propagation.

## 6. The protocol itself — LLD sketch

### 6.1 Message set

| Message | Stage | Carries | ~Size |
|---|---|---|---|
| HELLO / HELLO_ACK | discovery | capability class, registry version, nonce | 200 B |
| AUTH | identity | ID, signed capability claims, attestation stub | 400 B |
| ADVERTISE | intent | IntentDescriptor (quantized; elasticity as commitment only), epoch | 600 B |
| COMMIT | pre-negotiation | salted hashes of reservation values **and elasticity**, nonce | 300 B |
| PROPOSE / CONCEDE / ACCEPT | negotiation | offer point or region delta, round number | 300 B |
| REVEAL | arbitration only | committed values + salts, disputed dims only | 400 B |
| CONTRACT | agreement | dual-signed contract object (§6.3) | 1 KB |
| HEARTBEAT | monitoring | telemetry vs contract bounds | 200 B |
| VIOLATION / RENEGOTIATE | monitoring | breached trigger, proposed scope | 300 B |
| BYE | teardown | reason code | 100 B |

### 6.2 Per-agent state machine

`IDLE → DISCOVERING → AUTHENTICATING → ADVERTISED → NEGOTIATING(round k ≤ K) → {AGREED | ARBITRATED | FALLBACK} → MONITORING → (RENEGOTIATING → NEGOTIATING | EXPIRED → IDLE)`

The invariant that matters: **every state has a timeout edge into FALLBACK.** There is no state in which a silent or malicious peer can hold you indefinitely; the worst outcome of any hang is the conservative default contract.

### 6.3 The contract object — what everything above exists to produce

```json
{
  "contract_id": "c-7f3a…",
  "epoch": 12,
  "parties": ["agent:flow-01", "agent:warden-02"],
  "registry_version": "3.1",
  "bounds": { "inspection_depth": 3, "added_latency_ms": [0, 12], "sampled_fraction_unflagged": 0.2 },
  "invariants": ["no_flow_bypasses_flagging", "auth_never_disabled"],
  "ttl_s": 300,
  "renegotiation_triggers": [
    { "metric": "flagged_rate", "band": [0, 0.05], "dwell_s": 30 }
  ],
  "provenance": { "path": "concession", "rounds": 2 },
  "sig_A": "…", "sig_B": "…"
}
```

Note `provenance`: contracts remember *how* they were reached (intersection, concession, or arbitration, and in how many rounds). This is cheap to record, makes the audit log self-describing, and — not coincidentally — is exactly the metadata a Phase-2 knowledge artifact needs (§8).

### 6.4 Transport and encoding

CBOR over mTLS in the prototype (protobuf over gRPC is an equally fine answer). CSP is deliberately transport-agnostic: it is a session/semantic-layer protocol, and nothing in it cares whether the bytes ride TCP, QUIC, or a message bus.

## 7. Worked micro-example (the seed for Answer 4)

Two agents, opposing by construction. **FlowAgent** (objective: maximize throughput; class SLO) and **WardenAgent** (objective: maximize inspection coverage; class COMPLIANCE), negotiating over three registry dimensions: `inspection_depth` (0–7), `added_latency_ms`, and `sampled_fraction`.

At ADVERTISE, FlowAgent declares feasible `inspection_depth ∈ [0, 2]` and `added_latency_ms ≤ 8`, with an invariant that end-to-end p99 latency stays under its SLO. WardenAgent declares feasible `inspection_depth ∈ [4, 7]` and `sampled_fraction ≥ 0.8`, with an invariant that *no flagged flow ever bypasses inspection*. Stage 0 finds the intersection on `inspection_depth` empty — a genuine impasse, exactly the scenario in the brief.

Concession round 1: FlowAgent raises its ceiling 2 → 3, offering full sampling on flagged flows in exchange; WardenAgent lowers its floor 4 → 3, conditional on `sampled_fraction = 1.0` for flagged traffic and a widened latency budget of 12 ms. Round 2: both accept the now-non-empty region ({3} on depth); elasticity commitments open, verify, and feed the selection rule. Registry 3.1 scopes inspection dimensions by flag status: the rider pinned the flagged pair (depth 3, sampling 1.0); unflagged sampling is Warden's floor minus its opened elasticity (0.8 − 0.6 = 0.2), unflagged depth the quantized midpoint of [0, 3], giving 1. Contract: latency bound 12 ms, TTL 300 s, renegotiation trigger if the flagged rate exceeds 5% for 30 s, epoch = higher party epoch + 1. Both invariants survive intact — the COMPLIANCE-class invariant was never negotiable, and FlowAgent's SLO invariant reshaped *how* coverage was bought (sampling) rather than being overridden.

The submission version of this compresses to: one ADVERTISE snippet per agent, one CONCEDE snippet, the final CONTRACT JSON, and a four-line narration of the stages — comfortably inside two pages, no diagrams needed.

## 8. Phase 2 foresight: broadcasting intelligence

What we know: after conflicts resolve, Phase 2 concerns an agent sending its intelligence to other agents so they can use it. Our bet on the unit of shareable intelligence is the **cognition capsule**: a signed, content-addressed artifact containing a resolution (a contract, or a policy delta learned from one), an **applicability predicate** over registry dimensions ("relevant when your peer is COMPLIANCE-class and `inspection_depth` is in dispute"), the provenance chain from §6.3, a confidence value, a TTL, and a revocation pointer.

Distribution is gossip or pub-sub — epidemic, coordinator-free, exactly like route advertisement. Adoption is **local and deterministic**: a receiving agent checks the applicability predicate against its own IntentDescriptor, verifies signatures and the publisher's reputation, and then adopts the capsule *as a prior* — a better opening position for its next negotiation — never as an override of its own invariants. That last rule is the poisoning defense: a malicious capsule can at worst waste one negotiation round; it can never make an agent violate its constitution.

The reason we belabored representation in Section 2 pays off here: **typed, registry-based intent transfers across heterogeneous agents; embeddings would have died at this exact step.** A capsule written by a transformer-based auditor is directly consumable by a rules-engine load balancer, because it speaks registry dimensions, not model internals. Signatures, epochs, provenance, and reputation — all already built for Phase 1 — become the trust fabric of propagation for free. Even the hysteresis idea recurs: knowledge that keeps flipping gets damped before rebroadcast, the gossip-layer version of route-flap damping. Threats we're pre-noting for Phase 2: capsule poisoning (contained by adopt-as-prior), staleness (TTL plus confidence decay), and amplification storms (damping plus dedup by content hash).

## 9. The trade-off ledger

| Decision | Alternative rejected | What we gave up | Why acceptable |
|---|---|---|---|
| Typed registry intent | Shared embeddings | Open-ended expressiveness | Computability, auditability, cross-architecture transfer; extension dims recover flexibility |
| Deterministic arbitration | LLM-negotiated settlement | Adaptive cleverness | Termination proof, reproducibility, injection immunity |
| Quantized disclosure | Exact constraint values | Negotiation precision (may miss thin agreements) | Blunts boundary probing; ZK/2PC seam recovers precision later |
| Contracts as leases | Continuous renegotiation | Instant adaptation | Flap damping; bounded behavior between renegotiations |
| Lexicographic priority classes | Pure weighted sum | Fine-grained cross-class tradeoffs | Safety cannot be bought out; classes are few and constitutional |
| Sealed elasticity | Advertised elasticity | Peers can't pre-compute your concession budget | Envelope inference (threat 8) closed; verification needs only the public step ε |
| Bit-metered disclosure budget | Request-count rate limit | Simplicity of a counter | Leakage bound is *stated in bits*, thanks to quantization; probing has a price |
| Commit-reveal | Full ZKP in prototype | Cryptographic privacy of committed values until reveal | Honest scoping; named primitive and a one-interface seam |
| Pairwise (2-agent) protocol | N-party consensus from day 1 | Multilateral optimality | Pairwise contracts + Phase-2 capsules approximate it; N-party is Phase-2+ scope |

## 10. Failure modes and adversarial dry runs

**A lying agent** overstates its constraints to extract concessions: commit-reveal forces the lie to be blind and pre-registered, arbitration outcomes are audited against reveals, and repeated dishonesty craters reputation and disclosure level. **A probing agent** re-negotiates to map your thresholds: quantization caps what any probe can resolve, and the per-peer disclosure budget caps how many probes exist. **Network partition** mid-contract: leases expire, both sides fall back to safe defaults independently — availability degrades, safety doesn't. **Replay** of an old permissive contract: epochs and nonces make stale contracts unverifiable. **Sybil flooding**: identity attestation plus admission control at AUTH; unauthenticated peers never reach the intent layer at all. **Two maximally stubborn agents**: Stage 2 produces an outcome regardless — stubbornness only forfeits your influence over *which* outcome, since arbitration weights concessions. **Registry version mismatch**: negotiate down to the highest common version or refuse cleanly; refusing to negotiate meanings you don't share is correct behavior, not a failure. **Arbitration gaming**: the arbitration function's inputs were all committed before Stage 1, so there is nothing left to game by the time you know you'll need it. **Clock skew**: dwell timers and TTLs are measured against heartbeat-relative time, not wall clocks.

## 11. What we deliberately did not build, and why saying so helps

No **central coordinator** — it's a single point of failure and the brief forbids the spirit of it; determinism-without-an-arbiter (§4.3) is our replacement. No **shared embedding projector** — pairwise coupling cannot scale past a handful of agents. No **full ZKP implementation** — the seam is designed and the primitive is named (§5.5); implementing it in a hackathon would be theater. No **learned negotiation policy** — an LLM negotiating on the wire is unverifiable and non-terminating; models stay behind the protocol, translating goals into descriptors and contracts into behavior. Stating the non-goals is part of the defense: every one of them is a scoping decision with a reason, not an omission.

## 12. Open questions we are still carrying honestly

**N-party generalization** — do pairwise contracts compose into coherent multilateral behavior, or does true N-party negotiation need its own mechanism? Our lean: pairwise plus capsule sharing approximates multilateral well enough for an internet-scale system, the same way pairwise BGP sessions produce global routing. **Incentive compatibility** — is truthful declaration a dominant strategy under CSP? Commit-reveal plus reputation *approximates* it; the theory-complete answer is a VCG-style mechanism, which we judged too heavy for Phase 1 but can cite as the known destination. **Registry governance** — who owns the dimension vocabulary? This is an IANA/IETF-shaped question, which is a natural thing to say to Cisco. **Semantic drift** — even a versioned registry can't stop `inspection_depth` from subtly meaning different things to different operators over time. Partially addressed since first draft: dimensions now carry conformance tests (§2.6), so drift is *detectable* against an observable; periodic cross-calibration probes remain the sketch for correcting it.

## 13. Mapping to the five submission answers

**Answer 1** (state sync vs payload overhead, 200–300 w) ← §2, with the byte budget from §2.5 and the ontology trade from §2.6. **Answer 2** (conflict resolution, 200–300 w) ← §4, leading with the four defensibility properties of §4.7. **Answer 3** (semantic security & minimum disclosure, 250–350 w) ← §5, structured as gap → threats → ladder → commit-reveal → seam. **Answer 4** (end-to-end example, ≤2 pages) ← §7 with the JSON snippets from §6.3; text and JSON only, no diagrams, per the rules. **Answer 5** (AI-tool disclosure, ≤500 w) ← keep a running log of prompts used during ideation and drafting from today onward, so the disclosure is a summary of a real record rather than a reconstruction.

## 14. Final-review deltas (post-draft, pre-submission)

A second AI-assisted pass reviewed the drafted answers against the limits and the example's arithmetic. Three refinements were adopted into the submission; all are recorded above in their home sections:

1. **Sealed elasticity** (§2.4, §5.4a, threat 8) — elasticity moved from ADVERTISE into COMMIT after we caught that public elasticity let anyone compute the negotiation's landing point from the two advertisements alone.
2. **Bit-metered disclosure budget** (§5.6) — the probing defense upgraded from a request counter to an information bound: quantization makes each verdict's leakage computable, so the budget is stated in bits.
3. **Conformance-grounded registry** (§2.6) — every dimension carries a unit and a conformance test; vocabulary agreement is verified against observables, and heartbeats check compliance against the same test. This is our concrete answer to the "deep semantic intent across architectures" phrasing, and it partially converts §12's semantic-drift worry from undetectable to detectable.

Housekeeping folded in at the same time: `batch_release` cut from the worked example (declared, never used); the flagged/unflagged contract values now derived on the page (0.8 − 0.6 = 0.2; midpoint of [0, 3] quantized to 1); contract epoch defined as higher party epoch + 1; trailing commas fixed so every JSON snippet parses; word counts verified inside every limit; Answer 4 confirmed at exactly two rendered pages.

Verified final counts: A1 294/300 · A2 281/300 · A3 343/350 · A4 pages 3–4 of the rendered doc · A5 312/500.
