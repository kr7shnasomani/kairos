# Kairos: Nebius x NVIDIA prep, and the UI/UX pass

Working list for the **Nebius x NVIDIA Global AI Hackathon** (submission deadline **30 Oct 2026**,
judging 1 to 15 Dec, winners ~11 Jan 2027). Brief: `docs/problem_statement/Nebius_x_NVIDIA_Global_AI_Hackathon.md`.

Track: **Best Apps and Agents**. Fit assessed at **7/10 as the repo stands**, ~9/10 with sections 0 to 2
and 5 done.

Two kinds of item are mixed below, and they are not interchangeable:

- **Eligibility** (section 0). Without these the submission fails the Stage One pass/fail check and is
  never scored.
- **Score** (sections 1 to 6). These move the four equally weighted criteria: technological
  implementation, design, potential impact, quality of the idea.

**The product test (added 2026-09-22).** Every item that changes the product must be something a
paying plant customer would want in production. Work that exists only to impress a judge (canned
demo flows, fixes tuned to the demo dataset) stays out of the codebase; the video and the deck carry
the demo story instead. Items that are pitch material rather than product are labelled **pitch**
and produce no product code. What the test removed is listed under
[Removed by the product test](#removed-by-the-product-test).

Effort is in focused days for one person working with Claude Code. Add ~20% for this repo's own
process (skill dispatch, tests, keeping `status.md` current).

---

## 0. Eligibility, and where each item now stands

Decisions taken 21 Sep 2026: this repo stays **proprietary**; the open-licensed copy lives in a
separate submission repo. The demo video exists and needs refinement only. README and deployment are
end-of-cycle work. The build items are the focus.

| # | Item | Effort | State |
|---|---|---|---|
| E1 | **Open-source licence on the submission repo.** Rules require Apache 2.0 / MIT / MPL 2.0, visible in the About box. This repo keeps its proprietary licence; the mirror carries the open one. Closest match to the current terms: **MPL 2.0** (see below). | minutes | Deferred to the mirror repo, by decision |
| E2 | **A runtime call to Nebius Token Factory.** Code path is in place as tier 1; it activates the moment `NEBIUS_TOKEN_FACTORY_API_KEY` is set. The rules define it: the project "makes a runtime call to the Token Factory inference API, or is deployed/run using Nebius AI Cloud compute". A key sitting unused in `.env` does not qualify, and Stage One is pass/fail on this. | 0.5 to 1 d | **The one hard build blocker** |
| E3 | Provider refactor. Optional for eligibility, worth it for reuse. See N1. | done | **Done 21 Sep 2026**: `services/model_providers.py` |
| E4 | Demo video, public on YouTube, **under 3 minutes**, audio covering the Token Factory and Nemotron usage. | refinement only | Existing video needs a recut and new narration |
| E5 | README: Nemotron usage, Token Factory, feedback, and what changed since 26 Aug. | 0.5 d | Deferred to the end, by decision |
| E6 | Demo reachable through 15 Dec. | 0 to 1 d | Deferred, by decision |

### Which licence matches the current one

None of the three preserves "no redistribution, no derivatives", since that is what open source gives
away. Ranked by how much of the current licence's intent survives:

1. **MPL 2.0, the closest.** File-level copyleft: anyone who modifies your files has to publish those
   modifications under MPL, so the code cannot be taken closed. It also carries an explicit patent
   grant with litigation termination, and it explicitly allows combining with proprietary code, so a
   private fork can keep its own closed parts.
2. **Apache 2.0, the safe default.** Permissive, but with the most protective boilerplate of the
   permissive licences: patent grant with retaliation, NOTICE attribution, no trademark grant, and
   warranty and liability language close in effect to what the current licence says. Most familiar to
   judges.
3. MIT gives away the most and matches least.

One thing to be clear-eyed about: the submission repo must contain all the source needed to run the
project, so once that copy is published under an open licence, that version of the code is open
permanently. Keeping this repo proprietary does not change that.

---

## 1. Nebius and the model plane

### Why this passes the product test

Token Factory is **required for eligibility**, and it is also production value: the provider registry
lets a client choose Token Factory, NIM, OpenRouter or Gemini by configuration, with automatic
fallback between them. Every Nebius item kept in this section serves one of those two purposes.

### What Token Factory usage actually requires

- A **runtime call** to the Token Factory inference API from the running project, or the project
  deployed on Nebius AI Cloud compute (Serverless Jobs, Serverless Endpoints, DevPods).
- At least **one NVIDIA open-source model**. Nemotron on Token Factory satisfies both at once.
- Judges test the demo and read the repo, and the video has to describe the usage, so an unused key
  is not an option.

### Cost, which is smaller than it looks

Every catalog model is paid, but the **Nebius Builder Program gives hackathon entrants Token Factory
credits** (and Tavily credits), which is the intended route. Usage here is also small: a full
`run_benchmark.py` pass is 46 questions at roughly 3k to 6k prompt tokens each, so a few hundred
thousand tokens per run, and live demo traffic is a handful of calls. Check current pricing, but at
these volumes a benchmark run costs a fraction of a dollar.

**Cheapest compliant setup:** route only copilot synthesis through Token Factory Nemotron. One model,
one call path, everything else unchanged.

### Model picks from the Nebius catalog

| Use | Model | Note |
|---|---|---|
| Copilot synthesis, briefs | `Nemotron-3-Super-120b-a12b` (NVIDIA) | Same model the system already runs on NIM, so behaviour should carry over |
| NER, query classification | `Nemotron-3-Nano-30B-A3B` (NVIDIA) | Replaces Meta `llama-3.2-11b-vision`; cheaper and faster than Super |
| P&ID vision | `Nemotron-Nano-V2-12b` (NVIDIA, vision) | The only NVIDIA vision model in the catalog at a sane size. `Cosmos3-Super-Reasoner` is the larger option |
| RCA deep reasoning | `Nemotron-3-Ultra-550b-a55b` (NVIDIA) | Optional. Expensive, and `/rca` already takes ~90 s |
| OCR | stays on NIM `nemotron-ocr-v2` | No Nemotron OCR in the Nebius catalog |
| Embeddings | stays on Jina | No NVIDIA embedding model in the catalog, and switching means re-embedding the corpus, a dimension change and a cloud write. Do not |

### Work items

| # | Item | Effort | Why |
|---|---|---|---|
| N1 | **Done 21 Sep 2026.** Provider registry (`services/model_providers.py`); Token Factory is tier 1 when `NEBIUS_TOKEN_FACTORY_API_KEY` is set, NIM stays behind it on the same model. Only the key is outstanding. How it works: `docs/BACKEND.md`, provider cascade. | done | Satisfies E2 once keyed |
| N2 | Once the key arrives, check two things: `verify_served_model` (`services/llm.py:652`) against Token Factory's model id spelling, and whether `chat_template_kwargs.enable_thinking` is honoured there (`llm.py:615`). | 2 h | A mismatch flags every answer |
| N3 | NER to Nemotron Nano, P&ID vision to Nemotron Nano V2 12B. Re-check extraction F1 after. | 1 to 2 d | Makes NVIDIA models load-bearing rather than incidental |
| N4 | Re-run the benchmarks against Token Factory. | 0.5 d + credits | The 41/46 was measured through NIM |
| N5 | Model size routing, Nano for extraction, Super for the copilot, Ultra for RCA, with the answering model shown in the UI. | 1 to 2 d | The track brief asks for exactly this |

### The provider refactor

Done 21 Sep 2026. The design and the rules for adding a provider are documented once, in
`docs/BACKEND.md` (provider cascade); this file does not repeat them.

---

## 2. Quick wins: product polish

| # | Item | Effort | Notes |
|---|---|---|---|
| Q1 | **Done for assets, 22 Sep 2026; quarantine left to review.** **Hide QA test data from live screens.** `QA-TEST-155635` appears in compliance; "QA: scoring..." and a voice note whose transcript is "." appear in quarantine. | 1 to 2 h | Two different problems. The id prefix extends the read-time predicate in `services/corpus.py:56`. The "." note is degenerate *content*, so it needs its own rule (hide or label quarantine items below a minimum content length). Widening the filename denylist carries the D8 evidence bar: it must not swallow a plausible real document. Read-time filter only, nothing deleted |
| Q2 | **Done 22 Sep 2026.** **Fix the empty screens**, with honest empty states rather than imported numbers. | 2 to 3 h | `system-benchmarks/page.tsx` is deliberately live-only (its header comment says the numbers a judge sees are read from the running system). Do **not** render `RESULTS.md` figures into it: that is a fixture wearing a results page and it breaks the live-only rule. Make empty states say why they are empty and when the last recorded run was. Same treatment for Timestamp Drift and zero-count asset pages |
| Q3 | **Overview's "last 14 days" chart is flat at zero** on the demo data, whose events sit in July story time. Production-correct fix: when the window is empty, say so and show when the last event was ("No events in the last 14 days. Last event: 15 Jul"). Do **not** anchor the window to the dataset's dates: in production that would hide a genuinely quiet plant. | 1 to 2 h | Computed from the events the page already fetches, so no database change |
| Q4 | **Done 22 Sep 2026.** **Login page cleanup.** Drop "Seeded users: admin, engineer, field_worker" (`app/login/page.tsx:132`) and relabel the demo button (`:127`). | 20 min | Stops the first screen reading as a dev build |
| Q6 | **Done 22 Sep 2026.** **Explain Kairos's own concepts in place**: authority levels L1 to L5 on `AuthorityBadge`, blast radius, quarantine, candidate versus verified topology. Not industry terms like PTW or MoC, which plant users already know. | 1 to 2 h | A real need: these are this product's vocabulary, and the compliance and management personas are not engineers |
| Q7 | **Done 22 Sep 2026** (compact-rhythm breakpoint 820px to 1020px, re-measured with 24px nav headers). **Nav overlap bug**: the "Governor, active" pill overlaps the Knowledge group at 1440x900, clipping "Documents". | 30 min | |
| Q8 | **Resolved 22 Sep 2026, not a bug.** The lower Overview sections looked faded in an emulated, scaled browser window. In a normal window they fade in once scrolled into view, as designed. | done | |

**Section 2 total: 1.5 to 3 days.**

---

## 3. Impact and credibility

| # | Item | Effort | Notes |
|---|---|---|---|
| I1 | **Pitch.** **Quantify the benefit**, but not with the time-to-answer headline. `status.md` records that advantage falling from 25.6% to 9.5%, and explains that a 21-document corpus caps how much retrieval can win. A judge who digs finds a number you already walked back. | 0.5 d | Lead instead with Flow A from the golden dataset: the Fischer seal bulletin that never reached the stores before the third failure. Concrete, in the corpus, and it does not rest on a flagged benchmark. Do not attach an invented cost figure. Cite a public range or leave cost out |
| I2 | **Customer discovery, the most production-relevant item here.** **External validation**: one quote or feedback session with a real plant or maintenance engineer. | calendar, not effort | Start asking now. Answers "would anyone really use this" better than any feature |
| I3 | **Real public documents in the corpus**, then re-run the benchmarks. | 3 to 5 d | Three catches. (a) The repo must be public for Nebius: CSB reports and regulations are redistributable, **OEM manuals are copyrighted and must not go in**. (b) Grading is deterministic against a ground-truth key, so documents without labelled questions grow the corpus without improving any number, and can *lower* the linkage percentage. Add the answer key in the same change. (c) It is a cloud write and needs explicit authorization at the time |
| I4 | **Pitch.** **Cite the workforce and knowledge-loss claims** on the landing page and in the deck, or soften them. | 1 to 2 h | The ET brief supplied those figures; they were never independently verified here |

---

## 4. Technical implementation

| # | Item | Effort | Notes |
|---|---|---|---|
| T1 | **A real agent: the governed RCA investigator.** Plans its own steps and calls the search, graph, OT and compliance tools, with the reasoning trail shown. Tools read-only and authorised through OPA as the acting user, no quarantine promotion, output through the existing safety gate. | 5 to 8 d | Biggest single score gain. There is no tool-calling code anywhere in the repo today. The governance angle is what makes it non-obvious rather than "another agent demo" |
| T2 | **Tavily integration**: external alerts, bulletins and incident reports arrive in quarantine at authority level 5. | 2 to 3 d | $3,000 bonus prize, stackable with a track or overall prize. The architecture already describes this path and marks it out of scope |
| T3 | **Elasticsearch readiness after reboot.** Confirmed real: compose uses `condition: service_started`, and `api/main.py:53` only logs when index creation fails. | 2 to 4 h | Small, real robustness |
| T4 | **Re-run safety eval and cross-functional** after the model and corpus changes. | 0.5 d + credits | Cross-functional reads NULL because of corpus size, so it only moves if I3 happens |
| T5 | **Handwriting OCR (recall 0.333)**: leave it. | 0 d | Raising it means a different model or the deferred local VLM path, which is research, not a fix. Present the current behaviour as correct: those documents went to review instead of being indexed. Calibrated honesty scores better than a chased number |
| T6 | **Copilot latency**: skip. | 0 d | p50 is 1.5 s and p95 9.8 s on Nemotron 3 Super, which is fine live. A cache would have to key on query, as-of date, role and site scope, and gets correctness-risky against time-travel queries |

---

## 5. UI and UX

**Where it stands.** A good foundation, so this is polish and information architecture, not a rebuild:
about 150 design tokens with light and dark palettes, 21 shared primitives in `components/ui.tsx`,
68 of 86 page files using them, 75 frontend test files, no hardcoded colours. The catch is scale:
**48 routes, ~14k lines in pages, 2,234 `className` uses in page code**, so layout changes are
page-by-page work.

| Scope | Covers | Effort |
|---|---|---|
| **Tier 1** | Overview dashboard only: move "what needs me now" above the fold (attention items, briefs awaiting sign-off, riskiest assets), fix the dead chart (Q3) | 3 to 5 d |
| **Tier 2** | The core daily-workflow screens: Overview, Copilot, Briefs, Asset detail, RCA, Quarantine. Chosen because users live there; the video happens to use the same ones | 8 to 12 d |
| **Tier 3** | All 48 routes, navigation restructure, mobile field app | 20 to 30 d. **Not before 30 Oct** |

| # | Item | Effort | Notes |
|---|---|---|---|
| U1 | **Simpler navigation.** ~22 sidebar links in 5 groups plus 4 system links, and Governance hides 8 sub-pages behind a card grid. | 0.5 d | Cheaper than it sounds: nav entries already carry roles, so this is default-collapsing advanced groups per persona |
| U2 | **Accessibility pass** (axe, keyboard, contrast). | 0.5 d core screens, 2 to 4 d everywhere | Core workflow screens first. Enterprise procurement often asks for this, so it is product work, not polish |
| U3 | **Landing page maintainability**: `app/page.tsx` is a single 2,099-line file. | 1 d | Optional. Only if it gets in the way |

---

## 6. The demo narrative (pitch)

| # | Item | Effort | Notes |
|---|---|---|---|
| D1 | **Pitch.** **Lead with what is unique**: time travel ("what was true last March"), the refusal card, and a proactive brief arriving with no question asked. | folded into E4 | The video's storyboard. It decides the order of the demo, not which features get built |

---

## Totals and sequencing

| Block | Effort |
|---|---|
| 0. Eligibility (E2 only; E1, E4 to E6 deferred or done) | 0.5 to 1 d |
| 1. Nebius and model plane (N2 to N5) | 2.5 to 6 d |
| 2. Quick wins (remaining: Q3, Q6, Q8) | 0.5 to 1 d |
| 3. Impact and credibility (without I3) | 1 d |
| 4. Technical (T1 to T3) | 8 to 12 d |
| 5. UI, Tier 2 | 8 to 12 d |
| **Build total, remaining** | **~20 to 32 d** |

Available: roughly 27 working days between 22 Sep and 30 Oct. Done so far: N1, Q1 (assets), Q2,
Q4, Q6, Q7, Q8. Remaining build order, with licence, video, README and hosting handled outside this list:

Ordered light to heavy by decision (22 Sep 2026). Blocked items slot in when their key arrives.

**Light (hours each):**
1. ~~**T3**: Elasticsearch readiness after a reboot.~~ **Already solved**, found 22 Sep 2026: the API
   depends on Elasticsearch with `condition: service_healthy`, and Elasticsearch has a health check.
   An earlier note here said otherwise; it had read the frontend's `service_started` by mistake.
2. **U1**: role-based nav, advanced groups collapsed by default. **Recommended to drop**: role
   filtering already hides pages a persona cannot use, the clipping it was meant to relieve is fixed
   (Q7), and collapsing groups by default costs discoverability. A customer would not ask for it.
3. **U2**: **done 22 Sep 2026.** Measured audit of the six core screens in light, dark and
   high-contrast modes found two real WCAG AA failures, both fixed (nav header target size, amber
   badge contrast). Details and method: `status.md` § Verification snapshot.
4. **N2**: **prepared 22 Sep 2026**, needs only the key. Casing-tolerant served-model check, a
   Token Factory thinking switch separate from NIM's, a health probe that sends what real answers
   send and reports the served model, and readable provider names under Copilot answers. Turning it
   on is five steps in `docs/BACKEND.md` › Turning on Nebius Token Factory.

**Medium (1 to 3 days each):**
5. **N5**: show which model answered, and route by model size. The display can be built now; the
   routing to Nano or Ultra **needs the key**.
6. **N3, N4**: NER and vision onto Nemotron, then re-measure. **Needs the key.** Keep a swap only if
   the re-measured F1 is equal or better.
7. **T2**: Tavily. Needs a Tavily API key; cut first if the schedule slips.

**Heavy (last):**
8. **T1**: the governed RCA agent.
9. **Tier 2 UI polish** on the core screens. After T1, because the agent adds a reasoning-trail view
   to the RCA screen and polishing it first would mean doing it twice.

**Parked:** Q3, the empty Overview window, until the end by decision.
**Pitch, alongside the video:** D1, I1, I4.

Running in parallel on calendar time rather than effort: **I2** (find a plant engineer to talk to).

Cut if the schedule slips: T2, U3, I3, and all of Tier 3 UI.

### Removed by the product test

| Item | Why it went |
|---|---|
| Q5, "Start here" scenario launcher | Canned buttons pointing at demo-dataset ids (HE-301, PTW-2026-0714). A real plant would never want them on its dashboard, and they would need maintaining as the data changes. The video carries the demo path instead |
| N6, Nebius Serverless Jobs for ingest or benchmarks | Not required for eligibility (the rules list it as encouraged; a Token Factory runtime call is enough). Celery and Temporal already run background work, so a second job runner is cost with no customer benefit |
| Q3 as first written (anchor the chart window to the dataset's dates) | Would hide a genuinely quiet period in production. Replaced by the honest empty-window message |

Project debt found while doing this work (not hackathon-specific) is recorded in
[`status.md` § Pending](./status.md#pending--as-of-2026-09-22), P10 to P12 (P9 is fixed), not repeated here.

## Decisions still open

| | Decision | Blocks |
|---|---|---|
| 1 | Builder Program credits, or pay per token | N1, N4. Nothing else moves until a Token Factory key exists |
| 2 | Whether to grow the corpus with public documents, and accept the cloud write plus the answer-key work | I3, T4 |
| 3 | Whether this work happens on a branch until AI Builders results are out (~25 Sep) | sequencing only |

## Settled

| Decision | Date |
|---|---|
| This repo stays proprietary; the submission mirror carries MPL 2.0 or Apache 2.0 | 21 Sep 2026 |
| Demo video exists, needs a recut to under 3 minutes plus Token Factory and Nemotron narration | 21 Sep 2026 |
| README and deployment are end-of-cycle work | 21 Sep 2026 |
