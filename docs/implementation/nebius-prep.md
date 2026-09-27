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

## State as of 2026-09-23

**Shipped and pushed to `main`** (`ca2f16b`, `c7fc783`, `bdf1436`, `42b1e02`): the provider registry
with the Token Factory tier, the test-asset read filter with reported exclusions, nullable issue
counts, the demo-polish and accessibility fixes, and the docs for all of it. CI green on Tests, Linting, Docker and Frontend CI.

**Credits.** Nebius Builder Program joined 2026-09-22: $25 Token Factory credit applied (balance
$29.50 plus a $1 trial), $25 Tavily credit available to claim. LangSmith, Toloka and Tandem credits
were assessed and declined (see *Decisions still open*).

**The Token Factory key is in the local `.env` and no call has been made with it.** The user paused
spending on 2026-09-22, so N2, N3 and N4 wait for an explicit go-ahead. Note that the key being
present is enough: whenever the stack runs, Token Factory is tier 1 and every answer spends credits.
Commenting the key line out reverts the cascade to NIM with no code change.

**Two sessions, one working tree.** A parallel session owns the UI overhaul (section 5, uncommitted
at the time of writing: 103 files, two routes removed). Backend and plan work is owned here. Anything
in section 5 is theirs; do not edit frontend files from this plan without checking with them first.

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
| N2 | **Prepared 2026-09-22, paused by the user 2026-09-22 (no calls until they say so).** Once cleared, check two things: `verify_served_model` (`services/llm.py:652`) against Token Factory's model id spelling, and whether `chat_template_kwargs.enable_thinking` is honoured there (`llm.py:615`). | 2 h | A mismatch flags every answer |
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
| Q2 | **Done 22 Sep 2026.** **Fix the empty screens**, with honest empty states rather than imported numbers. | 2 to 3 h | `system-benchmarks/page.tsx` (page removed 2026-09-22) was deliberately live-only (its header comment says the numbers a judge sees are read from the running system). Do **not** render `RESULTS.md` figures into it: that is a fixture wearing a results page and it breaks the live-only rule. Make empty states say why they are empty and when the last recorded run was. Same treatment for Timestamp Drift and zero-count asset pages |
| Q3 | **Overview's "last 14 days" chart is flat at zero** on the demo data, whose events sit in July story time. Production-correct fix: when the window is empty, say so and show when the last event was ("No events in the last 14 days. Last event: 15 Jul"). Do **not** anchor the window to the dataset's dates: in production that would hide a genuinely quiet plant. | 1 to 2 h | Computed from the events the page already fetches, so no database change |
| Q4 | **Done 22 Sep 2026.** **Login page cleanup.** Drop "Seeded users: admin, engineer, field_worker" (`app/login/page.tsx:132`) and relabel the demo button (`:127`). | 20 min | Stops the first screen reading as a dev build |
| Q6 | **Done 22 Sep 2026.** **Explain Kairos's own concepts in place**: authority levels L1 to L5 on `AuthorityBadge`, blast radius, quarantine, candidate versus verified topology. Not industry terms like PTW or MoC, which plant users already know. | 1 to 2 h | A real need: these are this product's vocabulary, and the compliance and management personas are not engineers |
| Q7 | **Done 22 Sep 2026** (compact-rhythm breakpoint 820px to 1020px, re-measured with 24px nav headers). **Nav overlap bug**: the "Governor, active" pill overlaps the Knowledge group at 1440x900, clipping "Documents". **Superseded 2026-09-27:** the nav headings are gone, rail rows have a `min-height` floor and the pill hides when collapsed; re-measured at 1440x900 as 0 overflow for both the engineer and the full admin rail, so the overlap cannot recur at that size. | 30 min | |
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

### T1 in detail: what "agentic" means here

Today RCA is a fixed pipeline: retrieve, then summarise. As an agent it plans its own investigation
and calls tools for each step: failure history for the asset, the same failure mode on sibling assets,
the OEM position, whether the recommended action was actually executed, the historian's pre-failure
signature, then ranked hypotheses with citations.

What makes it Kairos's rather than a generic agent, and what must not be dropped while building it:

- **Read-only tools**, authorised through OPA **as the acting user**, so the agent can never surface
  what that person cannot see.
- **No promotion.** It cannot move anything out of quarantine or write a canonical edge.
- **The safety gate still applies** to its conclusion, so it refuses rather than guesses on a
  safety-critical parameter.
- **Every tool call is logged** to the audit trail, so a reviewer can see how a hypothesis was reached.
  An auditable agent is the differentiator; an unlogged one is a demo.

**What is deliberately not an agent:** ingestion, compliance mapping, proactive briefs and the
Temporal workflows. The first two are deterministic and auditable as they stand, and an agent would
only add a way to be wrong. The last two are automation with fixed steps, and the pitch should say so
plainly rather than claim them as agentic.

### T2 in detail: how Tavily is used, and where it is not

**Tavily is an ingestion path, never a retrieval path.** It does not participate in Copilot answers.
Every claim the Copilot makes cites a governed vault document with an authority level and a
verification status; a web result has none of those, so admitting one into synthesis would break the
guarantee the whole system is built on.

The flow, which is the one `ARCHITECTURE.md` already describes for external industry sources:

1. A scheduled watcher queries Tavily for material tied to the asset registry: regulatory amendments
   (OISD, PESO, CPCB), OEM safety bulletins for the equipment classes in use, and public incident
   reports such as CSB findings.
2. Each hit becomes a **quarantine item** (`quarantine_items`) at **authority level 5**, linked to an
   equipment **class**, not to a tag. An external advisory is evidence about a class of pump, never
   about your EQ-101, and collapsing that distinction is the failure mode to avoid.
3. It surfaces where quarantine already surfaces: the review queue and the asset page, labelled
   unverified.
4. A human promotes it. Only then can the Copilot cite it, and it still carries its authority level.

Two practical constraints: there is **no Celery beat schedule** in this project, so the watcher runs
on Temporal's cron (Temporal is already in the stack); and writing quarantine rows is a **cloud
write**, so the first real run needs an explicit go-ahead.

---

## 5. UI and UX (owned by the parallel UI session since 2026-09-22)

**Where it stands.** A good foundation, so this is polish and information architecture, not a rebuild:
about 150 design tokens with light and dark palettes, 21 shared primitives in `components/ui.tsx`,
68 of 86 page files using them, 75 frontend test files, no hardcoded colours. The catch is scale:
**48 routes, ~14k lines in pages, 2,234 `className` uses in page code** (see the note below for
the post-overhaul figures), so layout changes are
page-by-page work.

> These figures are a **2026-09-22 snapshot, taken before the overhaul began**, and the overhaul
> changed them. As of 2026-09-27: **46 page files** (44 under `(app)` plus `/login` and the landing;
> `/system-benchmarks` and `/system-information` were removed), which the e2e sweep numbers as **42
> live routes** because it collapses some dynamic variants. Primitives grew by `ButtonLink` and the
> `icon.tsx` set. Re-measure before quoting any of it; the owning session's notes are in
> `ui-overhaul.md`.

| Scope | Covers | Effort |
|---|---|---|
| **Tier 1** | Overview dashboard only: move "what needs me now" above the fold (attention items, briefs awaiting sign-off, riskiest assets), fix the dead chart (Q3) | 3 to 5 d |
| **Tier 2** | The core daily-workflow screens: Overview, Copilot, Briefs, Asset detail, RCA, Quarantine. Chosen because users live there; the video happens to use the same ones | 8 to 12 d |
| **Tier 3** | All routes (48 then, 46 now), navigation restructure, mobile field app | 20 to 30 d. **Not before 30 Oct** |

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

| Block | Remaining effort | Owner |
|---|---|---|
| 0. Eligibility (E2 needs only the go-ahead; E1, E4 to E6 are end-of-cycle) | 0.5 to 1 d | this session |
| 1. Nebius and model plane (N2, N3, N4) | 2 to 4 d | this session, paused |
| 2. Quick wins (Q3 parked; Q1's quarantine half is P10) | 1 to 2 h | user decision first |
| 3. Impact and credibility (I1, I4 pitch; I2 calendar; I3 optional) | 1 d | user, with this session |
| 4. Technical (T1 agent, T2 Tavily; T3 was already solved) | 7 to 11 d | this session |
| 5. UI and UX, including N5's display half | in progress | parallel UI session |
| **Remaining here, excluding section 5 and the pitch** | **~10 to 16 d** | |

Available: roughly 27 working days between 23 Sep and 30 Oct.

### The work list, by owner (2026-09-23)

**The user decides or acts (minutes each):**

| | Item | Why it is theirs |
|---|---|---|
| 1 | Leave the Token Factory key active, or comment it out | Every stack start spends credits while it is set |
| 2 | Decide U1 (recommendation: drop) | Product judgement |
| 3 | Resolve P10: dispute or archive the two QA quarantine items | Cloud write |
| 4 | Pull and restart the AWS server | Backend changes are not live until then |
| 5 | Claim the Tavily credit and add the key when T2 starts | Account action |

**The parallel UI session:** section 5 in full, plus N5's display half (showing which model answered).

**This session, unblocked, backend only:**

| | Item | Effort |
|---|---|---|
| 7 | **T1** governed RCA agent: tools, agent loop, API, audit-trail logging. The view is the UI session's | 5 to 8 d |
| 8 | **T2** Tavily watcher into quarantine (needs the Tavily key) | 2 to 3 d |

**Paused until the user allows Token Factory calls:** N2 (2 h), N3 (1.5 to 2.5 d), N4 (0.5 d).

**Parked:** Q3 (Overview empty window, by user decision), P11 (failing offboarding test), P12
(`ARCHITECTURE.md` cascade section).

**End of cycle, in this order:** E1 licence on the mirror repo, E4 video recut under 3 minutes, E5
README section, E6 hosting through 15 Dec, then the pitch items D1, I1, I4. I2 (talk to a plant
engineer) runs on calendar time and should start whenever possible.

**Cut if the schedule slips:** T2, U3, I3, and anything in section 5 beyond the overhaul in progress.

### Removed by the product test

| Item | Why it went |
|---|---|
| Q5, "Start here" scenario launcher | Canned buttons pointing at demo-dataset ids (HE-301, PTW-2026-0714). A real plant would never want them on its dashboard, and they would need maintaining as the data changes. The video carries the demo path instead |
| N6, Nebius Serverless Jobs for ingest or benchmarks | Not required for eligibility (the rules list it as encouraged; a Token Factory runtime call is enough). Celery and Temporal already run background work, so a second job runner is cost with no customer benefit |
| Q3 as first written (anchor the chart window to the dataset's dates) | Would hide a genuinely quiet period in production. Replaced by the honest empty-window message |

Project debt found while doing this work (not hackathon-specific) is recorded in
[`status.md` § Pending](./status.md#pending--as-of-2026-09-27), P10 to P14 (P9 is fixed), not repeated here.

## Decisions still open

| | Decision | Blocks |
|---|---|---|
| 1 | Whether the Token Factory key stays active in `.env` (spends credits on every answer) or is commented out until the work resumes | N2, N3, N4 |
| 2 | Whether to grow the corpus with public documents, and accept the cloud write plus the answer-key work | I3, T4 |
| 3 | U1: collapse nav groups by default. Recommendation is to drop it | nothing; closes an item |

## Settled

| Decision | Date |
|---|---|
| This repo stays proprietary; the submission mirror carries MPL 2.0 or Apache 2.0 | 21 Sep 2026 |
| Demo video exists, needs a recut to under 3 minutes plus Token Factory and Nemotron narration | 21 Sep 2026 |
| README and deployment are end-of-cycle work | 21 Sep 2026 |
| Build order runs light to heavy; the heavy items (T1, UI) come last | 22 Sep 2026 |
| Nebius Builder Program joined; $25 Token Factory credit applied, balance $29.50 plus $1 trial | 22 Sep 2026 |
| **No Token Factory calls** until the user says so, credits being the concern | 22 Sep 2026 |
| Partner credits assessed: **claim Tavily** ($25, the only one tied to planned work, T2). **Decline LangSmith** ($100: tracing and evaluation for LangChain apps, duplicating OTEL to Grafana and the deterministic benchmarks), **Toloka** ($50: human labelling, but ground truth comes from the canon dataset) and **Tandem** ($50: no use here) | 23 Sep 2026 |
| `.env` and `.env.example` are kept in sync, same names and order; 19 variables were missing locally and were added with the example's defaults, all existing values preserved byte-for-byte | 23 Sep 2026 |
| Tavily is an **ingestion** path into quarantine, never a Copilot retrieval path (see T2 in detail) | 23 Sep 2026 |
| The one agentic feature is the **governed RCA agent** (T1); briefs, ingestion, compliance mapping and Temporal workflows stay deterministic and are described as automation, not agents | 23 Sep 2026 |
| Section 5 (UI and UX) handed to the parallel UI-overhaul session | 22 Sep 2026 |
