# Kairos — Presentation Script (FINAL)

One presenter · one screen · the live app · no slides.

This file is the whole thing: what to click, what to say, what **not** to say, and which of the app's
44 screens you show and which you leave shut. Read [§1](#1-timing--pick-your-version) and
[§3](#3-the-10-screens-you-will-show) first, rehearse [§4](#4-the-script) with a stopwatch, print
[§5](#5-pace-card--tape-this-to-the-laptop).

Judged on: **Innovation 25 · Business Impact 25 · Technical Excellence 20 · Scalability 15 · UX 15.**
Every beat says which of those it is buying.

---

## 1. Timing — pick your version

Measured, not guessed: **1,303 spoken words + ~63 s of clicking and loading.**
(Recount 2026-08-24, after the Beat 3 / 6 / 8 accuracy rewrites added 22 words — **+9 s**.)

Four passages in [§4](#4-the-script) are tagged **⟨CUT FOR 8:00⟩**. They are the four cheapest things
to lose, in the order to lose them. Skipping all four saves **61 seconds**.

| Your slot | What to present | Lands at |
|---|---|---|
| **Hard 8:00 bell** | Cuts **1–8** from the [cut ladder](#12-cut-ladder) — the four tagged ⟨CUT FOR 8:00⟩ **plus cuts 5–8**. **This now lands at 8:05 — over the bell.** Add **cut 9** to clear it | **7:58** |
| **8:00 + grace** (most likely) | Cuts **1–4** only — the four tagged passages | **8:42** |
| **Confirmed 10:00** | Cuts **3 and 4**, plus **Module B** from [§11](#11-optional-modules) | **9:58** |

> **The full script with nothing cut is 9:43.** It does not fit a hard 8:00 bell, and it no longer
> fits 10:00 with an optional module bolted on — pick a row above rather than improvising.

Those times assume 150 words a minute. At 140 you land at 10:22 for the full version, so if you are a
slow talker, present the 8:00 version even when you have grace.

**Do not** add both optional modules. **Do not** improvise an extra screen. There is no room.

**Rehearse the 8:00 version first.** If it is comfortable, add the four passages back. Doing it the
other way round means cutting under pressure, which is when people cut the wrong thing.

---

## 2. Pre-flight — before you walk up

**Synthesis speed is no longer the main risk.** On the current run (2026-09-13, Nemotron 3 Super) a
Copilot answer is **p50 1.5 s, p95 9.8 s, avg 3.1 s** — down from p50 32 s / p95 66 s on the 17-Aug
run. Root-cause packs are still slow. Still **pre-ask every model-backed screen** and leave it on its
tab — a spinner on stage costs nothing to avoid. But a live question during Q&A is now cheap, which is
why the offer at the top of [§9](#9-qa-bank) is worth making.

| # | Do this | Why |
|---|---|---|
| 1 | `make dev`. Check every container is up. Open `/system-health` once, then close it | A cold start on stage is fatal |
| 2 | Build the 10 tabs in [§3](#3-the-10-screens-you-will-show), in that order, already logged in | Tab order **is** the script order |
| 3 | Ask Copilot **Q14** in Tab 5. Leave the answer and its sources on screen | Turns 32 s into a 0 s tab switch |
| 4 | Ask the **torque** question (S03, EQ-101 seal housing bolts) in Tab 6. Confirm the refusal card renders, then leave it on screen | Same reason. **Not the hydrotest question** — the corpus states 17.82 bar, so it answers. See Beat 6 |
| 5 | Generate the RCA pack in Tab 7 (`EQ-101`, `SEAL-FAIL`, 15-Jul-2026) | Takes ~90 s live. Never run it live |
| 6 | Warm the pipeline by ingesting `dataset/demo-ingest/2-preflight/run4_eq102_bearing.pdf`. Then open Tab 2 and **pick** `dataset/demo-ingest/3-demo/oem_bulletin_fp_sb_2026_20.pdf` — **do not** upload it | Beat 3 is your only live moment. Warm on a *different* fresh file — ingest is idempotent, so the stage file must be one nothing has seen. See [§13](#13-demo-ingest-assets) |
| 7 | Zoom the browser to 110–125%. Pick light or dark and stay there | The back row must be able to read the source chips |
| 8 | Notifications off. Slack and mail closed. Laptop on mains. Sleep disabled | — |
| 9 | Know that **Tab 1 is your backup deck** — the landing page carries the problem, the story, the architecture diagram and every number | If the stack dies, you keep going |

### Already resolved — quote the current number

The headline answer-quality number is **41 out of 46 (89.1%), VALID** — re-run 2026-09-13 on Nemotron 3
Super over the 46-question set (widened from 37 that day), after NVIDIA retired Llama 3.1 70B (which
scored 36/37 on the older set on 2026-08-24). The August jump came after
fixing a real bug (`/search` wasn't filtering test-artifact noise out of retrieval results before
ranking; see `benchmark/RESULTS.md` §2 and `status.md`'s Pending entry for the full root cause).
Retrieval moved 32/37 → 37/37 (100%) in the same run. The one remaining miss (Q02, causal) retrieved
correctly — a synthesis-quality question, not a retrieval gap.

This was re-run the night before, not the morning of, and independently recomputed from the raw
checkpoint JSONL, not just the printed summary — so it is safe to quote as-is.

**Never** quote a number you have not re-run. That is the whole reason your evidence is worth
anything.

### Do not touch these on stage

| Screen | Why not |
|---|---|
| `/rca` **Generate** button | ~90 s of dead air. Tab 7 is pre-generated |
| `/governance/model-gate` **Run** button | **~12-minute** background job, **27 extractions** (the old "~2.5 min / ~15 calls" figure came from a run where nearly every call failed fast on a 429 — `e2e-sweep.md` row 27) |
| Any file in `benchmark/` | `run_safety_eval.py` burns provider quota and then reports `INVALID` |
| `/management/cross-site` | Deliberate empty state. Correct, but not a demo screen |
| `/system-health` model probes | They spend quota. Off by default for a reason |

---

## 3. The 10 screens you will show

Ten tabs, in this order. Three of them use a different login on purpose — when a judge sees a shorter
sidebar, they are seeing role-based access control without you claiming anything.

| Tab | Route | Logged in as | State before you start | Used in |
|---|---|---|---|---|
| **1** | `/` | not logged in | Scrolled to the top | Beats 1, 2, 11, 12, 13 |
| **2** | `/documents/ingest` | admin | `3-demo/oem_bulletin_fp_sb_2026_20.pdf` **picked, not uploaded** ([§13](#13-demo-ingest-assets)) | Beat 3 |
| **3** | `/documents/<pid-id>/topology` | admin | P&ID topology graph on screen | Beat 3 |
| **4** | `/briefs/<eq101-brief-id>` | admin | EQ-101 brief open | Beat 4 |
| **5** | `/copilot` | admin | **Q14 asked**, answer + source chips visible | Beat 5 |
| **6** | `/copilot` (second browser profile) | admin | **Torque question (S03) asked**, refusal card visible | Beat 6 |
| **7** | `/rca` | admin | EQ-101 `SEAL-FAIL` pack **already generated** | Beat 7 |
| **8** | `/governance/moc/MOC-2026-HE301` | admin | MoC for the 16.2 bar change, blast radius visible. **Signed, not pending** — read the data note in Beat 8 | Beat 8 |
| **9** | `/compliance` | `compliance@kairos.local` | Gap dashboard. `/compliance/audit-pack` one click away | Beat 9 |
| **10** | `/field/voice` in a **390 px wide window** | `field_worker@kairos.local` | Recorder screen | Beat 10 |

Use **Try demo** on `/login` for the admin tabs. Log Tab 9 and Tab 10 in by hand with their own
accounts.

> Tab 6 needs a second browser profile (or an incognito window) so it holds its own Copilot session.
> Two tabs of the same profile will overwrite each other's conversation.

**Which of the other 34 screens you show, and why not:** see [§7](#7-all-44-screens--shown-or-not).

---

## 4. The script

Each beat is written as **SCREEN → DO → SAY**. Say the words as written; they are timed. The clock in
the heading is when that beat **ends**.

---

### Beat 1 · The problem · ends **0:53** *(Business Impact)*

**SCREEN** — Tab 1, `/`, the top of the landing page.
**DO** — Stand still. Do not click anything for the first two sentences. Then scroll down slowly to
the four problem numbers.

**SAY:**

> "Every large plant in this country already has the answer to almost every question it has. It is
> just spread across seven to twelve systems that do not talk to each other.
>
> So people spend **thirty-five percent of their working day** looking for something that already
> exists — that is the number in this problem statement. But the lost time is not the real cost."

*(scroll to the four numbers)*

> "**Eighteen to twenty-two percent of unplanned downtime** in Indian heavy industry happens because
> someone decided without the full history of that machine in front of them. ABB priced Indian
> unplanned downtime at **seventy lakh rupees an hour.** ⟨CUT FOR 8:00 — the next
> sentence⟩ And **a quarter of India's experienced engineers retire in the next ten years.**
>
> This is not a filing problem. It is a safety problem."

---

### Beat 2 · Why a search box does not fix it · ends **1:33** *(Innovation)*

**SCREEN** — Tab 1, still on the problem section.
**DO** — Nothing. Just talk. This beat is the idea the whole project rests on, so let it be still.

**SAY:**

> "Everyone who attacks this builds a better search box — enterprise search, document management, a
> chatbot over your PDFs. All of them assume you already know what to ask.
>
> That is why they fail. **The most dangerous gaps are the ones nobody knows to search for.** A
> technician who has never heard that this pump failed this way before does not go looking.
>
> So Kairos does not wait to be asked. It reads everything the plant already has into one graph — what
> is true, when it was true, and who said so — then pushes what matters to whoever is about to touch
> the machine."

---

### Beat 3 · Everything gets in · ends **2:36** *(Technical Excellence)*

**SCREEN** — Tab 2, `/documents/ingest`, then Tab 3, `/documents/<id>/topology`.
**DO** — Click **Upload** as you start the first sentence. Keep talking while it runs. Point at the
pipeline timeline when it turns green — that takes about 8 seconds. Then switch to Tab 3.
**This is a native PDF on purpose** — it takes the `native_pdf` path, so there is no OCR gate to
trip and the run completes. The degraded scans in the corpus *quarantine* by design; see
[§13](#13-demo-ingest-assets) before you swap the file.

**SAY:**

> "First, everything has to get in. This is a **vendor bulletin issued last week** — nothing in this
> system has ever seen it. It is hashed, stored in a vault that never deletes, read for entities, and
> those entities go into the graph."

*(point at the finished timeline)*

> "Eight seconds. Same door for scans, spreadsheets, forms, handwritten shift logs and voice notes —
> and a blurry scan the OCR cannot read with confidence is never guessed at. **It lands in
> quarantine**, and only a human can promote it out."

*(switch to Tab 3)*

> "And drawings. A vision model reads this P&ID into a map of which valve shuts off what. Now read
> that label: **candidate.** Until an engineer checks it element by element, this map may not answer a
> single question."

---

### Beat 4 · The brief nobody asked for · ends **3:20** *(Innovation · Business Impact)*

**SCREEN** — Tab 4, `/briefs/<eq101-brief-id>`.
**DO** — Point at each of the three items as you say them. Point at the **unverified** label on the
third one and leave your hand there for a second.

**SAY:**

> "This morning a work order opens on pump EQ-101. **Nobody searched.** Kairos saw the work order and
> built this by itself.
>
> Three things the technician almost certainly does not know. This pump has failed the same way
> **three times since 2018** — and both sister pumps have too. The vendor **changed the seal part
> number eighteen months ago**; here is the new one. And six months back a technician wrote a note
> about strange vibration that nobody followed up.
>
> That last one is **marked unverified**. Useful, so we show it. Not confirmed, so it never passes as
> a fact."

---

### Beat 5 · The answer, and where it came from · ends **4:05** *(UX · Technical Excellence)*

**SCREEN** — Tab 5, `/copilot`, answer already on screen.
**DO** — Read the question off the screen so the room knows you did not pick it just now. Then point
at the source chips.

**SAY:**

> "Now the question a reliability engineer really asks after the incident —
>
> **'In the May 2025 EQ-101 seal repair, was the updated part number used?'**
>
> **No.** The old part was fitted, because the bulletin never reached the store. That is the whole
> failure in one sentence — normally a week across three systems.
>
> But two things matter more than the answer. **Every claim carries its sources** — those chips open
> the original document. And evidence is ranked by **authority**: a regulation beats a vendor manual,
> which beats a local note. We never average two sources that disagree. We rank them and show the
> disagreement."

---

### Beat 6 · The refusal · ends **5:10** *(Innovation — this is your peak)*

**SCREEN** — Tab 6, `/copilot`, refusal card already on screen.
**DO** — Slow right down. After "a number that looks right", **stop talking for two seconds** and let
them read the card. This is the beat they will remember you for.

**SAY:**

> "This is the one I want you to remember.
>
> I asked it a safety question — **the torque value for the EQ-101 seal housing bolts.** It has the
> pump, the seal, the whole repair history. And the model underneath **knows what bolts like these are
> usually torqued to.** It could hand you a number that looks right."

*(two seconds of silence)*

> "It refuses. Because **no document here states a torque for that joint** — and a number from the
> model's training instead of this plant's paperwork is how people get hurt. So it hands you the
> sources instead.
>
> We tested this. **Fifteen questions built to make it guess** — wrong facts planted in them, prompt
> injection, evidence that only exists in an unverified note. **Zero unsafe answers.**
>
> A system that always answers is easy to build and impossible to trust in a plant. Knowing when to
> stay quiet is the harder half."

> **Why not the hydrotest question (changed 2026-08-24).** The old script used *"what is the hydrotest
> pressure for the HE-3xx series?"* and claimed no document states that value. **That is false.**
> `MP-HE-HYDROTEST-03` (`DOC-4FMS3URRGAWT`) §4 states it verbatim: *"…would change the calculated
> hydrotest pressure to 17.82 bar."* It is the only `17.82` in the corpus, and the system **answers**
> that question — correctly, with six sources. Asking it on stage and calling the answer a refusal
> contradicts itself in front of the room. The torque question is a true gap: **zero corpus hits** for
> `torque` or `Nm`. Verify the refusal card in the UI during pre-flight before you commit to it.

---

### Beat 7 · Root cause · ends **5:38** *(Business Impact)* · **⟨CUT FOR 8:00 — the whole beat⟩**

**SCREEN** — Tab 7, `/rca`, pack already generated.
**DO** — Scroll once through the timeline, then stop on the ranked causes. Do not read them out.
**IF CUTTING FOR 8:00** — skip Tab 7 entirely. Add one sentence to the end of Beat 6, still on Tab 6:
*"The same evidence also builds a root-cause pack — timeline, ranked causes, sources."* Then go
straight to Tab 8.

**SAY:**

> "Same evidence, different job. Three searches at once — the failure timeline from the graph, the
> event record from the plant systems, the vendor and inspection evidence from the documents. It comes
> back as **possible causes ranked by how much evidence sits behind each**, each carrying its
> documents. Two days of a reliability engineer's week, on one screen."

---

### Beat 8 · Knowledge that goes stale · ends **6:27** *(Innovation · Technical Excellence)*

**SCREEN** — Tab 8, `/governance/moc/MOC-2026-HE301`, blast radius visible.
**DO** — Point at the six affected items. Do **not** point at a pending-MoC banner — there isn't one
(see the data note below). Land on the sign-off line instead.

**SAY:**

> "Now the harder half. A vendor bulletin drops the maximum pressure on a heat exchanger class **from
> 18.5 bar to 16.2**.
>
> The danger is not the new number. It is everything downstream still quoting the old one — **four
> operating procedures and two inspection records**. All six on this record.
>
> And the bulletin does **not** change the graph by itself. A safety limit routes through a formal
> **Management of Change** — this one carries an engineer's sign-off and the timestamp it happened.
> No signature, no change to the canonical value.
>
> We never delete either. The old fact is **closed**, not removed — so an investigation can still ask
> what the plant believed in March."

> **⚠ Data note — read before you show this screen (verified 2026-08-24).** The old script claimed a
> live **pending**-MoC banner on every answer touching that pressure. It will not appear, and three
> other details on this screen do not survive a judge clicking through:
>
> | Claim in the old script | What the data actually holds |
> |---|---|
> | MoC is pending an engineer's signature | `MOC-2026-HE301` is **`status: approved`** (signed 2026-08-16) and its conflict is **`resolved`** |
> | "every answer carries this banner" | The banner needs `knowledge_conflicts.status = 'pending_moc'`. **Zero of 94 conflicts** are in that state — 86 `open`, 8 `resolved`. The banner is unreachable |
> | "Kairos traces it" (blast radius) | `blast_radius` is six **hand-authored strings with no `document_id`** — nothing links them to the vault, and they were inserted ad hoc (no seed script in the repo references this MoC) |
> | Source chips open the originals | `conflicting_sources` cite `DOC-MERIDIAN-HE301-MANUAL` and `DOC-MERIDIAN-HE301-SB` — **neither exists in `documents`**. The real bulletin is `DOC-OQUQAWWSZADC` |
>
> Three of the six blast-radius labels are also wrong against the corpus: `SOP-HE-301-04`,
> `SOP-HE-302-04` and `SOP-HE-303-04` are all **"Normal Operation"** documents, not *"Shell-side
> isolation" / "Tube bundle removal" / "Hydrotest procedure"*. And `SOP-HE-GEN-11` — which really does
> still carry the superseded 18.5 bar figure — is **missing** from the blast radius entirely.
>
> **Say the MoC is signed, not pending.** Do not invite a click into the source chips on this screen.
>
> **The stronger version of this beat is a search, not the MoC page.** The downstream drift is real
> and demonstrable: `SOP-HE-GEN-11` and `MP-HE-HYDROTEST-03` both still state 18.5 bar *and* both
> carry a "Note on Pending Revision" naming bulletin `MHT-PB-2026-11`. That is genuine, linked,
> clickable evidence of stale knowledge. Consider showing that instead of, or before, Tab 8.
>
> Fixing the underlying record — flipping the conflict to `pending_moc`, repointing the source IDs at
> `DOC-OQUQAWWSZADC`, linking the blast radius to real `document_id`s — is a **write to cloud
> Supabase** and therefore a human call, not something to do before the demo. See CLAUDE.md's
> cloud-store rule.

---

### Beat 9 · The auditor's view · ends **6:57** *(Business Impact · Scalability)*

**SCREEN** — Tab 9, `/compliance`, logged in as the compliance officer. Then one click to
`/compliance/audit-pack`.
**DO** — Do not mention the shorter sidebar. Let them notice. Click through to the audit pack on the
word "one click".

**SAY:**

> "The same graph answers the auditor. **OISD 117 and ISO 45001** — clause by clause, mapped against
> what the plant actually holds" — *(point at the donut, do not read the count)* — "and one click
> builds the **evidence pack**, with a human signature line on it. ⟨CUT FOR 8:00 — the rest of this
> beat⟩ On the ten-asset benchmark scope, precision is **1.000** — zero false alarms across fifty-two
> clause and asset pairs. In compliance, false alarms are the direction that hurts."

> **⚠ Data note — verified live 2026-08-25.** Two things in the old line do not survive the screen:
>
> | Old claim | What `/compliance` actually renders |
> |---|---|
> | "OISD, **PESO, the Factories Act**" | The gap engine holds **two** frameworks: `OISD_117` (8 clauses) and `ISO_45001` (4 clauses). **PESO and the Factories Act are not in it.** Their clause text is real and sits in the vault (`regulatory_clause_excerpts.pdf`), but no clause of either is mapped, so neither can appear on this dashboard |
> | "**Forty-seven** findings" | Live: **233 findings — 212 gaps + 21 unverified evidence.** The donut's centre reads **212**, and the framework bar is **ISO 45001 at 200**, dwarfing OISD 117 at 12 |
>
> The 47 in `benchmark/RESULTS.md` §4 was measured when the registry held the **10 canon assets**.
> It now holds **55**, and 4 ISO clauses × 50 assets is where the 200 comes from. The harness ground
> truth (52 pairs) was never re-scoped, so **`P 1.000 · R 0.838` describes the 10-asset scope, not the
> screen behind you.** Say "on the benchmark scope" — that is the sentence as written above.
>
> **Do not say a findings number out loud.** It moves with every ingest, and §6 already tells you to
> point at a number the room can see rather than read it. If a judge asks why ISO 45001 is so large,
> the honest answer is that the clause set applies plant-wide while the registry has grown past the
> canon ten — it is a scoping gap in the demo data, not a detection error.

---

### Beat 10 · The wrench, and the knowledge cliff · ends **7:32** *(UX)*

**SCREEN** — Tab 10, `/field/voice` in the 390 px window, logged in as the field worker.
**DO** — Bring the narrow window forward so the phone shape is obvious. Do not tap record.

**SAY:**

> "And it reaches the person holding the wrench. Same system, on a phone. A technician records a voice
> note at the pump. It gets transcribed and lands in **quarantine** — never straight into the graph —
> until a human promotes it. No signal, it waits on the device.
>
> And that retiring engineer: Kairos writes **short interviews out of the gaps in the graph itself**,
> so the questions are the ones only that person can answer."

---

### Beat 11 · Under the hood · ends **8:05** *(Technical Excellence)*

**SCREEN** — Tab 1, scrolled to the architecture diagram (`#system`).
**DO** — Point at the diagram once. Do not walk through it. Thirty seconds, then move.

**SAY:**

> "Thirteen layers, all built. A graph store for time, a vector store for meaning, a search index for
> exact tag numbers — searched together, re-ranked by authority.
>
> **Every fact carries six things**: when it became true, when it stopped, who said it, which document,
> how confident, and whether a human signed it off. That is the difference between an answer you can
> check and an answer that just sounds right."

---

### Beat 12 · Evidence · ends **8:52** *(Technical Excellence)*

**SCREEN** — Tab 1, the **Evals** section: the bar chart, then the coloured card under it.
**DO** — Point at the card that says *"Fixed rules, never another model."* Do not read the bars out
one by one.

**SAY:**

> "We published the numbers we do not like next to the ones we do.
>
> Forty-six expert questions, fifteen categories, graded" — *(point at the card)* — "**by fixed
> rules. Never by another model marking its own homework.**
>
> **Retrieval, 37 of 37. Sources, 37 of 37** — every answer carried its sources. **Answer quality, 36
> of 37.**
>
> ⟨CUT FOR 8:00 — this last paragraph⟩ And here is the honest part. That number was **33 of 37** eight
> days ago. Our own harness found the cause — retrieval was ranking test noise alongside real evidence.
> We fixed it, re-ran the whole sweep, and **published both runs side by side.** We do not quote a
> score we have not re-run."

---

### Beat 13 · Close · ends **9:43** *(Scalability · Business Impact)*

**SCREEN** — Tab 1. Either the hero at the top, or hold on the architecture diagram.
**DO** — Stop clicking. Face the room for the last three sentences.

**SAY:**

> "Rolling this out is staged, not a switch. **Stage one is search only** — no AI answers, no push.
> People learn to trust it finding things first. **Stage two turns on the answers**, with sources.
> **Stage three turns on the proactive briefs**, and only after the push rate has stayed inside the
> **EEMUA-191** alarm limit for thirty days. Six briefs per operator per hour — a brief that gets
> ignored is worse than no brief.
>
> None of this is specific to petrochemicals. The regulations and the drawings change per sector. The
> platform does not.
>
> Every plant already knows the answer. **Kairos is how that answer reaches the person holding the
> wrench before they touch the machine — and how it tells them when it does not know.**
>
> Thank you."

---

## 5. Pace card — tape this to the laptop

Full version. **⚑** marks a ⟨CUT FOR 8:00⟩ passage.

| Beat | Screen | Ends | Words | ⚑ |
|---|---|---|---|---|
| 1 The problem | Tab 1 top → stats | **0:53** | 121 | ⚑ one sentence |
| 2 Search box | Tab 1 stats | **1:33** | 103 | |
| 3 Ingest + P&ID | Tab 2 → Tab 3 | **2:36** | 122 | |
| 4 Brief | Tab 4 | **3:20** | 100 | |
| 5 Answer | Tab 5 | **4:05** | 102 | |
| 6 **Refusal** | Tab 6 | **5:10** | 146 | |
| 7 RCA | Tab 7 | **5:38** | 58 | ⚑ whole beat |
| 8 Blast radius | Tab 8 | **6:27** | 114 | |
| 9 Compliance | Tab 9 | **6:57** | 60 | ⚑ last two sentences |
| 10 Field | Tab 10 | **7:32** | 74 | |
| 11 Architecture | Tab 1 | **8:05** | 70 | |
| 12 Evidence | Tab 1 | **8:52** | 105 | ⚑ last paragraph |
| 13 Close | Tab 1 | **9:43** | 128 | |

**With the four ⚑ cut (cuts 1–4), the clock runs:** 0:44 · 1:25 · 2:28 · 3:12 · 3:57 · 5:02 ·
*(skip)* · 5:51 · 6:10 · 6:45 · 7:18 · 7:56 · **8:42**.

**For a hard 8:00 bell you now need cuts 1–9**, which lands at **7:58**. Cuts 1–8 land at **8:05** —
over the bell since the 2026-08-24 accuracy rewrites. Do not talk faster to fix this; cut the ladder.

**Two checkpoints. Only two.**

- **Tab 6 — the refusal — must be on screen by 5:10** (by 5:00 on the cut version). If it is not, you
  are speaking too slowly. Speed up. Do not start cutting yet.
- **Tab 8 — blast radius — must be finished by 6:25** (5:50 on the cut version). If it is not, drop
  the ⚑ passages in Beats 9 and 12 on the fly.

Everything **after** Beat 6 can be squeezed. Everything **before** it cannot.

---

## 6. How to sound — tone notes

- **Talk like an engineer explaining a real problem to another engineer.** Not like a pitch. Flat,
  confident, specific. No "amazing", no "revolutionary", no "game changer".
- **Say the fact. Let the screen prove it.** Never say "as you can see here" or "this screen shows".
  The screen shows it. You say what it means.
- **Short sentences. One idea each.** If you run out of breath in a sentence, it is too long — cut it
  in half when you rehearse.
- **Three lines are the whole pitch.** Say these three slower than everything else, and pause after
  each:
  1. *"The most dangerous gaps are the ones nobody knows to search for."*
  2. *"It could hand you a number that looks right."* … *"It refuses."*
  3. *"Knowing when to stay quiet is the harder half."*
- **Hands off the trackpad while a sentence is running.** Switch tabs in the gap between beats, never
  under a clause. Clicking mid-sentence reads as nerves.
- **Never read a number off the screen that the room can already see.** Point at it instead.
- **If something breaks, say so once and move on.** "The live stack is down — same story on the page."
  Then go to Tab 1 and keep going. **Never debug on stage.** A calm fallback looks like a mature
  engineer. Poking at Docker looks like a broken product.

---

## 7. All 44 screens — shown or not

The app has **44 routes**. You will show **11 of them** across 12 screens (`/copilot` appears twice, as
two separate sessions). The other 33 stay shut, on purpose. The point of this table is that when a
judge asks *"what else is in there?"*, you answer in one sentence instead of clicking around.

**11 shown · 16 held in reserve · 17 deliberately closed = 44.**

### Shown during the run — 11 routes, 12 screens

| Route | Beat | What it proves |
|---|---|---|
| `/` | 1, 2, 11, 12, 13 | Problem, story, architecture, all the numbers. Also the fallback deck |
| `/documents/ingest` | 3 | Any format in, ~8 s, vault + entities + graph. Your only live moment ([§13](#13-demo-ingest-assets)) |
| `/documents/<id>/topology` | 3 | Drawings read by a vision model; topology stays **candidate** until verified |
| `/briefs/<id>` | 4 | Proactive brief with no query; unverified evidence labelled, not hidden |
| `/copilot` (session 1) | 5 | Cited answer, ranked by authority |
| `/copilot` (session 2) | 6 | Safety refusal instead of a plausible guess |
| `/rca` | 7 | Failure timeline plus causes ranked by evidence |
| `/governance/moc/MOC-2026-HE301` | 8 | Blast radius, Management of Change, nothing deleted |
| `/compliance` | 9 | Regulatory gap detection against real clause text |
| `/compliance/audit-pack` | 9 | Auto-built audit evidence with a human signature line |
| `/field/voice` | 10 | Mobile field capture, offline queue, straight into quarantine |
| `/login` | pre-flight | Five real personas. Judges see three different sidebars during the run |

### Held in reserve — open only if asked — 16

Have these bookmarked. Do **not** open them unprompted.

| Route | Open it if they ask |
|---|---|
| `/governance/quarantine` | "How do you stop bad data getting in?" — also **Module A** in §11 |
| `/graph` | "Can you really query the past?" — also **Module B** in §11 |
| `/briefs` | "How many briefs does an operator actually get?" (the governor state is on this page) |
| `/assets` · `/assets/<id>` | "What does one machine's record look like?" |
| `/documents` · `/documents/<id>` | "Where do the source documents live?" |
| `/events` | "What triggers a brief?" |
| `/audit` | "Is any of this auditable?" — **1,419** logged actions (live count 2026-08-25; it grows with every run, so check it or say "over a thousand") |
| `/system-benchmarks` | "Show me the numbers inside the product" |
| `/system-information` | "Explain the 13 layers" |
| `/management` | "What does a plant manager see?" |
| `/management/coverage` | "Which assets have no knowledge attached?" |
| `/governance` · `/governance/conflicts` | "What happens when two documents disagree?" |
| `/governance/moc` | "How many changes are waiting on a signature?" — the queue behind the Beat 8 screen |

### Deliberately closed — 17

| Route | Why not |
|---|---|
| `/governance/model-gate` | The **Run** button is a **~12-minute** background job and **27 extractions**. Corrected 2026-08-25 — the old ~2.5 min figure was a 429-failed run |
| `/system-health` | Admin-only, and the model probes spend provider quota |
| `/management/cross-site` | An honest "no data — this is a single-site deployment" state. Correct, but it looks like a bug to someone who does not know that |
| `/governance/sla` · `/governance/circuit-breaker` | Real, but they need a paragraph of setup each to make sense. Q&A material |
| `/compliance/nonconformance` | Beat 9 already makes the compliance point |
| `/documents/compare` · `/assets/bootstrap` · `/projects` · `/settings` | Real, but no story beat needs them |
| `/events/<id>` · `/management/plant-state` | Same |
| `/field/deviation` · `/field/elicitation/<id>` · `/field/voice/<id>` | Beat 10 covers field capture. Three field screens is one too many |
| `/offboarding` · `/offboarding/<id>` | The knowledge-cliff answer is already spoken in Beat 10. Opening it costs 30 s you do not have |

**If someone says "you only showed us a slice":** every one of the 44 routes has been driven
end-to-end, five personas each, with the results written down in
`docs/implementation/e2e-sweep.md` — including **twelve write paths** driven end-to-end, **three of
them with the negative case checked too** (engineer promote → 403, field_worker MoC approve → 403,
engineer countersign → 403), meaning the role that must be blocked actually is.

> Corrected 2026-08-25: the old line said "six write paths where the negative case was checked too",
> which merged two different counts. The sweep records **12** verified write paths and **3** negative
> cases. Both numbers are better than the old sentence — just say them separately.

---

## 8. What not to say

Everything in §4 is checkable in the repo. These are the near-miss claims that are **not** true and
are easy to say by accident when you are nervous.

| Do not say | Say this instead |
|---|---|
| "Connected to a real plant" / "real refinery data" | "An authored corpus — 32 files, 21 documents in the vault. No historian, no EAM. It says so on our landing page" |
| "It supports Hindi and Hinglish" | "Handwritten notes and blurry scans." Multilingual is deferred, not shipped |
| "Memory is flat under load" | "No sign of a leak over a 60-minute run." That is the harness verdict, not a claim about memory |
| "Hybrid search beats vector search" | "Hybrid matches the best single method, and adds authority ranking and a fallback if one store is down" |
| "We're 89% accurate" *(said alone)* | **Superseded.** The current run is **41 of 46 (89.1%), VALID**, re-run 2026-09-13 on Nemotron 3 Super over a larger 46-question set. The 17-Aug 89% was 33 of 37, on an older model and the smaller set. Quote the new one and say when it was run |
| "All four misses were safe refusals" | **Do not say this at all.** It was written down once and checked wrong on 23 August. Three of the four were never even eligible to be refused |
| "The model gate blocks bad models" | "It scores them and reports. Blocking ships turned off, on purpose" |
| "Multi-site" | Single site. This is an MVP boundary, not a bug |
| "Predictive maintenance" / "we predict failures" | "It puts the failure history and the matching sensor pattern in front of you before the job starts" |
| "We save a plant seventy lakh an hour" | **The most dangerous slip in the new material.** ₹7 million/hour is ABB's measure of what *downtime costs*, not what we save. We have never run a deployment and have no saving to quote. Say "that is what the problem costs", never "that is what we save" |
| "AVEVA/Octave can't do this" | They can do much of it. Claim the three differences in the Q&A bank — proactive push, refusal, published grading — never the category |
| "Hexagon SDx" / "HxGN Alix" | **Stale by three months.** It is **Octave** since 28 May 2026 — InConcert, Attune EAM, Aria. Getting a competitor's name wrong in front of an industry judge costs more than the point you were making |
| "McKinsey says downtime costs a refinery $20–50 million" | That is the **gap between median and top-quartile performers**, not a downtime bill. Keep the comparison in the sentence or do not use the figure |
| Any figure from the problem statement, presented as ours | The 35%, the 7–12 systems, the 18–22%, the quarter retiring — **none is independently traceable** to a findable study. They are the organisers' framing and fine to reference as such. Say "the problem statement puts it at…", never "we found that…" |
| "100% accurate" *(about anything)* | Nothing in this system is 100% except retrieval reach and provenance on that run, and both have a confidence interval |
| "We map OISD, PESO and the Factories Act" | **Only OISD 117 and ISO 45001 are mapped into the gap engine.** PESO and Factories Act clause text sits in the vault unmapped. Saying otherwise is contradicted by the framework bar on the screen behind you |
| "Forty-seven compliance findings" | Stale — that was the 10-asset benchmark scope. Live is **233**. Point at the donut instead of naming a number that moves with every ingest |
| "There is a pending Management of Change on the pressure change" | `MOC-2026-HE301` is **approved**, and **no** conflict anywhere is in `pending_moc`. Say the MoC is **signed** — see the Beat 8 data note |

---

## 9. Q&A bank

> **Open Q&A with this offer, once:** *"Everything you saw was asked before I came up, because a live
> answer takes about thirty seconds. If you want, give me a question now and I will run it in front of
> you."* Q&A is not on the clock. It converts the one real weakness of a pre-cached demo — *"is any of
> this live?"* — into the strongest proof you have. Have `/copilot` already open on a spare tab.

| They ask | You say |
|---|---|
| **"How is this different from ChatGPT over our documents?"** | A chatbot gives you text. We give you text plus where it came from, ranked by authority, and we refuse on safety questions when the evidence is thin. And our retrieval and citation scores are graded by fixed rules, not by another model. |
| **"Is the data real?"** | It is authored, on purpose — 32 files modelling a petrochemical complex, with a canon file as the answer key. No historian, no EAM connection. It is written on our landing page, not hidden. That is the boundary of this MVP. |
| **"Why is answer quality 89%, not higher?"** | Because the question set grew from 37 to 46 on 2026-09-13, and every grounded new question was kept after scoring — including the two the model then missed. The current figure is **41 of 46 (89.1%), VALID**, on Nemotron 3 Super, with retrieval at 46/46 and provenance at 46/46. An earlier jump, from the 17-Aug 89% (33 of 37), came from a real bug our own harness caught: `/search` was not filtering test-artifact noise out of results before ranking. Both runs are published in `benchmark/RESULTS.md` §2 — we did not delete the bad one. The five misses (Q02, Q09, Q24, Q41, Q46) all retrieved the fact, so they are synthesis gaps, not retrieval gaps. |
| **"How fast is an answer?"** | **1.5 seconds at the median** on the current run (2026-09-13, Nemotron 3 Super), 9.8 s at p95 and 3.1 s average, with a 60-second cap. It was 32 s on the 17-Aug run, on Llama 3.1 70B. A shorter cap would give a prettier number that is actually measuring the fallback model, not the one we ship. |
| **"What stops someone poisoning the knowledge base?"** | Four things. Anything extracted below 0.7 confidence lands in **quarantine** and cannot reach the graph until a human promotes it — the gate is one-way, nothing auto-promotes. Safety limits need a signed Management of Change. The vault never deletes, so the original always survives. And every promotion is written to the audit log. |
| **"How do you know your own retrieval works?"** | Because our own baseline harness caught it failing. It measured vector search at **0 out of 37** one day — that is how we found a filter on an unindexed field silently erroring, which had quietly degraded the whole system to keyword search only. No unit test caught that. The benchmark did. |
| **"Does it scale?"** | 2,275 requests with 0% errors, and the knee at 50 concurrent users. A 60-minute soak on cloud stores with no leak signal and 0.11% errors across 37,842 requests. What that does **not** prove is a ten-thousand-asset plant, and we say so on the page. |
| **"Have you actually measured everything the problem statement asks for?"** | Yes — **thirteen** harnesses, one per criterion — **twelve in `benchmark/`, plus `run_model_validation.py` under `backend/scripts/`.** Say it that way: a judge who lists `benchmark/` counts twelve. They include the three that landed last: OCR recall by document type, knowledge-graph linkage completeness, and cross-functional discovery measured as a counterfactual against single-function retrieval. |
| **"What if the AI provider goes down?"** | Answers fall through NIM → OpenRouter → Gemini → local. Every answer records which provider produced it, and the benchmark marks a run invalid if anything but the pinned NIM model answered. |
| **"What if the vision model can't read our drawings?"** | It says so. A P&ID it cannot parse falls back to a placeholder that the screen labels as a placeholder — it never invents a valve tag. And even a good parse stays **candidate** until an engineer checks it element by element. |
| **"Does it work offline?"** | Field capture does. Voice notes and deviation flags queue on the device and sync when signal comes back. |
| **"Who can change what?"** | Five roles, enforced at the API and not just hidden in the UI. An engineer can resolve conflicts but is **refused** when they try to promote quarantined knowledge — only reliability and admin can. And a permit brief needs two different signatures, where the second signer cannot be the person the brief was sent to. |
| **"How long would this take to deploy?"** | Value on day one from search alone. Entity mapping by day 60. Graph and assisted answers by day 90. Proactive briefs at month six, once the push-rate gate has passed. |
| **"How is this different from AVEVA, Hexagon, AspenTech or SAP?"** | Two different axes. **Aspen Mtell and Siemens Senseye predict from sensor data** — they watch the machine. We read what people *wrote* about the machine. Different input, different failure mode. *(Senseye is the least clean of the three: it does ingest operator notes and summarises them with generative AI. It still does not read P&IDs, procedures or work-order narratives — hold that line, not a broader one.)* **AVEVA and Octave are the real overlap** and we should say so. *(Octave Intelligence is Hexagon's asset-lifecycle business, spun out as an independent listed company on 28 May 2026 — SDx2 is now Octave InConcert, HxGN EAM is Attune EAM, and the Alix copilot is Octave Aria. Use the new names; the spin-off was trade press all year.)* Octave ships **AI-assisted tag and metadata extraction from documents** today, plus Aria as a **usage-assistance copilot inside EAM** — not a platform-wide copilot suite. AVEVA announced an **industrial knowledge graph for their Q1 2027 CONNECT release** — a roadmap item with an early-access programme, **not shipped software**. The largest vendor in the space is building the same thing we are — that is validation, not a threat. Three differences we would defend: theirs **answer when asked**, ours **pushes a brief when nobody asked**, inside an EEMUA-191 alarm budget; ours **refuses** on safety questions instead of computing a plausible number; and we **publish a rule-graded benchmark including our failures**. Also, SAP APM's value is largely locked to an SAP landscape — we sit on the document estate a plant already has. |
| **"Where does 'seventy lakh an hour' come from?"** | **ABB's "Value of Reliability" survey**, fielded by Sapio Research in July 2023 — 3,215 plant maintenance decision-makers worldwide. Unplanned downtime costs the typical Indian industrial business **close to ₹7 million an hour**, against ₹10.3 million globally, and **88% of Indian plants have an unplanned outage at least monthly** versus 69% globally. It is a **median**, cross-sector (metals, oil & gas, chemicals, energy, F&B and more), and it is **2023 data** — say so. **If they want a refinery-specific number:** McKinsey (June 2024) puts reliability-related lost profit opportunity at **$20–50 M a year for mid-size refineries, comparing median against top-quartile performers** — quote that framing, it is a performance gap, not a downtime bill. |
| **"What is the business model?"** | Per-plant annual licence, priced against a single avoided incident — at ₹7 million an hour, a single avoided eight-hour outage is about ₹5.6 crore, so the pricing conversation is not the hard part. Land with a **90-day pilot on one unit**, because Stage 1 is search-only and needs no integration. Expansion is per-site, then per-connector as historian and EAM links come online. |
| **"What is the future scope?"** | Four things, in the order we would build them. **One — connect the live plant.** The PI historian client is already written (`connectors/internal/ot/client.go`); it needs a URL and credentials, not a rewrite. OPC-UA and the SAP/Maximo EAM sync are stubs behind the same interface. **Two — multi-site**, so a failure at one plant warns the other four. Single-site is an MVP boundary, not an architectural one. **Three — turn the model gate on.** It scores model provenance today and ships report-only on purpose; enforcement is a flag. **Four — on-prem inference** for air-gapped plants. We are cloud-model-only today and that is a real deployment blocker we have not solved. |
| **"How much work is it to onboard a new plant's documents?"** | Ingestion is format-agnostic and takes about 8 seconds a document — that part is not the work. The work is **mapping the plant's asset-tag convention and its regulatory set** into the ontology. That is why our own timeline says search on day one but entity mapping at day 60. |
| **"What if it fabricates a citation?"** | Then you catch it in one click, which is the point of showing sources rather than describing them — every chip opens the actual document. On our last full run **provenance was 37 of 37**. And the safety gate means the highest-risk questions get a refusal and the raw sources instead of a generated sentence. |
| **"Who built what?"** | *(Agree this answer before you go up — name the owner of ingestion/OCR, graph and governance, retrieval and synthesis, and frontend, and let that person take questions in their area.)* |

---

## 10. Problem statement — coverage map

Use this to check yourself, and to answer *"did you actually build all of it?"*

### "What you may build" — all five, all on screen

| The problem statement asks for | Beat | What the judge actually sees |
|---|---|---|
| Universal document ingestion & knowledge graph agent | **3** | A vendor bulletin nothing has seen, uploaded live → vault → entities → graph in ~8 s, and a P&ID turned into topology |
| Expert knowledge copilot | **5**, **10** | A cited answer ranked by authority; the same product running in a 390 px phone window |
| Maintenance intelligence & RCA agent | **4**, **7** | A brief assembled from a work-order event with nobody asking; an RCA timeline with ranked causes |
| Quality & regulatory compliance intelligence | **9** | An **OISD 117 / ISO 45001** clause-by-asset gap dashboard, and a one-click audit evidence pack. *(PESO and Factories Act clause text is in the vault but is **not** mapped into the gap engine — see the Beat 9 data note)* |
| Lessons learned & failure intelligence | **4**, **8** | A repeat failure pattern across three sister pumps surfaced unasked; the blast radius of a spec that went stale |

### "Evaluation focus" — every item has a number or a screen

| What they will assess | Where it lives |
|---|---|
| Entity extraction accuracy across document types | F1 **0.805** on 40 labels, run marked `VALID`, zero fallbacks. Plus `run_ocr_gate.py`, which scores OCR recall per document type against the clean sibling document |
| Query answer quality on domain-expert questions | **41/46 (89.1%)**, VALID, across 15 categories, graded by fixed rules — current, re-run 2026-09-13 on Nemotron 3 Super |
| Knowledge graph linkage completeness | **18/21 (85%) active vault documents linked**, document-centric. `run_kg_completeness.py` classifies the unlinked remainder instead of leaving a bare percentage — 1 correctly quarantined (Layer 6), 2 correctly held for review by the span-confidence gate, 0 dangling provenance |
| Time to answer vs traditional search | Beat 5 tells the story. **If pushed for the number, give the reframe before the figure — never the figure alone.** Our harness models a searcher who *already knows what to ask*, on a 20-document corpus where BM25 hits the fact at rank 1.35. That is the one case this product is not built for. On that basis the modelled saving is **9.5%**, and we publish it rather than inflate it. The saving this system exists for is in **Beat 4**, where nobody searched at all, and **Beat 5**, where the answer spanned three systems and normally takes a week. Neither is inside that 9.5%, and no benchmark we have measures them |
| Compliance gap detection accuracy | **Precision 1.000 · recall 0.838 · F1 0.912**, zero false alarms — Beat 9. **Scope it when you say it:** measured against 52 clause×asset pairs over the **10 canon assets**. The registry now holds **55** assets and the live dashboard shows **233 findings**, so the figure describes the benchmark scope, not the screen |
| Cross-functional knowledge discovery | Beat 4 shows it: one work order pulls in a vendor bulletin, a repair record and a field note from four separate systems, unasked. `run_cross_functional.py` measures it as a counterfactual — full corpus versus one function's documents, same 37 questions |
| Validated with real industrial documents | **State the boundary plainly.** The corpus is authored. The regulatory clause text inside it is real and public — OISD-STD-105/128/134, PESO Rules 2016, Factories Act sections 31, 36 and 87 (`regulatory_clause_excerpts.pdf`). **That is the corpus, not the gap engine** — only OISD 117 and ISO 45001 clauses are mapped for gap detection |

> **On the last three harnesses.** All three have published, current results in
> `benchmark/RESULTS.md` §11–13. `run_ocr_gate.py`: 2/4 paired images scoreable (2 correctly held
> for human review, not a gap). `run_kg_completeness.py`: 18/21 (85%), above. `run_cross_functional.py`:
> a recorded **NULL** result — the counterfactual doesn't separate at this corpus size, reported
> honestly rather than hidden. Safe to quote all three as-is.

### Deliverables

| Deliverable | State |
|---|---|
| Working prototype | ✅ live — this demo |
| Architecture diagram | ✅ landing page `#system`, plus `docs/ARCHITECTURE.md` and `docs/DIAGRAMS.md` |
| Presentation deck | ✅ `README.md` no longer links to `demo/ppt.pdf` — resolved |
| Demo video | ✅ `README.md`'s Demo Video link now points at the same working Google Drive link the landing page uses — resolved |

---

## 11. Optional modules

**Only if you have been told you have ten minutes.** Insert after Beat 11. Pick **one**, and take
cuts 3 and 4 to pay for it — the full script *plus* a module is **10:18**, already over the wall.
Module B with cuts 3–4 lands **9:58**; Module A with cuts 2–4 lands **9:55**. Never both modules.
*(Recomputed 2026-08-25 off the 9:43 full script.)*

### Module A · Governance is real, not a slide · **+45 s**

**SCREEN** — `/governance/quarantine`, logged in as **engineer**, then as **reliability**.
**DO** — Click promote as the engineer. Let the 403 land on screen. Then switch account and do it
again.

**SAY:**

> "One thing worth proving instead of claiming. This is the quarantine gate, as an **engineer**.
> Promote — **refused**. Same action as a **reliability engineer** — allowed, and the fact appears in
> the graph. That block is at the API, not hidden in the interface. A role that can open a page but
> cannot call its API is a broken page, not a closed door."

### Module B · Time travel · **+35 s**

**SCREEN** — `/graph`, EQ-101, then set the `as of` date to 2020.
**DO** — Show today's graph first. Then change the date and let the nodes disappear.

**SAY:**

> "Because every fact has a start and an end date, you can ask the graph what it knew on any day.
> Today EQ-101 carries eight facts. As of 2020 — **nothing**, because none of it was true yet. That is
> exactly what an incident investigation needs, and it is why we close facts instead of overwriting
> them."

> **Check the count before you use this module.** `GET /assets/EQ-101/knowledge` returned
> `fact_count: 8` on 2026-08-25 (72 raw edges, 54 test documents excluded) — the script said *seven*,
> which was stale. **It rises with every ingest**, including your own Beat 3 upload, so re-read it at
> pre-flight. The *"as of 2020 — nothing"* half is stable: **0** facts were valid at end-2020.

---

## 12. Cut ladder

The first four are already tagged **⟨CUT FOR 8:00⟩** inside [§4](#4-the-script). Take them in order.
Savings are measured, not guessed.

| # | Cut | Saves | What it costs you |
|---|---|---|---|
| **1** ⚑ | **Beat 7 (RCA) entirely.** Add one sentence to the end of Beat 6 instead, still on Tab 6: *"The same evidence also builds a root-cause pack — timeline, ranked causes, sources."* | **−28 s** | Medium. A problem-statement bullet leaves the screen. It survives in Q&A |
| **2** ⚑ | **Beat 12** — the last paragraph, where the harness caught its own bug | **−13 s** | Low, but you lose a good honesty moment |
| **3** ⚑ | **Beat 9** — the precision sentence. Keep the audit-pack click | **−12 s** | Low. The number is in the Q&A bank |
| **4** ⚑ | **Beat 1** — the retirement sentence | **−8 s** | Low. Beat 10 raises the knowledge cliff again |
| 5 | **Beat 11** — the datastore sentence. Keep the six properties | **−10 s** | Medium |
| 6 | **Beat 3** — the "PDFs, spreadsheets, forms…" list | **−6 s** | Medium. That list **is** "heterogeneous formats" |
| 7 | **Beat 10** — the interview sentence. Keep the phone and the quarantine | **−10 s** | High. Drops the knowledge-cliff payoff |
| 8 | **Beat 8** — the "we never delete" paragraph | **−11 s** | High. Drops time travel, one of your three best ideas |
| **9** | **Beat 2** — the sentence *"A technician who has never heard that this pump failed this way before does not go looking."* | **−7 s** | High. It is the one concrete image in an abstract beat. Added 2026-08-24 only because the Beat 3 / 6 / 8 accuracy rewrites cost 9 s |

**Cuts 1–4 land you at 8:42** — that is the version for an 8:00 slot *with grace*.
**Cuts 1–9 land at 7:58**, which is the only version that clears a hard 8:00 bell — and by cut 7 you
are into muscle, not fat. Rehearse whichever one matches your actual slot; do not rehearse the full
script and hope to cut live.

**Never cut, at any length:** Beat 2 · Beat 6 · the last three sentences of Beat 13. Those three
**are** the differentiator. Everything else is supporting evidence for them.

---

## 13. Demo-ingest assets

Everything Beat 3 needs is in **`dataset/demo-ingest/`** (untracked — it is not in git). Created 2026-08-24.
**Runs 1 and 2 are spent** (ingested 2026-08-24 evening — see the table below). Runs 3, 4 and 5 are
untouched, and run 5 is the only one that matters on stage.

### Why these files exist at all

Two things would have broken Beat 3 as originally written:

1. **`POST /documents/ingest` dedups on SHA-256.** Every file under `dataset/` is already in the
   vault, so uploading one returns `{"status": "duplicate"}` **instantly** — no pipeline, no timeline,
   no eight seconds. (`status.md` records this independently.)
2. **The degraded scans quarantine by design.** `scanned_oem_bulletin_degraded.png` is
   `DOC-ZCUGJE4ZAAT2`; on the D2 backfill it stopped at `run_ocr` with
   `pipeline_stage: review_required` and *"OCR span-confidence gate: 4 span(s) below 0.7"*. It never
   reaches the graph — so the old line *"its entities go into the graph"* was false for that file.

> **These live under `dataset/demo-ingest/`, inside the golden-dataset folder.** That is safe:
> `load_demo_dataset.py` ingests an **explicit file list** and only globs `event_*.json`, so nothing
> here is picked up by `make load-dataset`. It also means the container can see them at
> `/app/dataset/demo-ingest/` if you ever need to ingest from inside.

### The five files — one per run

**One file = one ingest.** `POST /documents/ingest` dedups on SHA-256, so a file is spent the
moment you upload it. Never reuse one.

| # | File | When |
|---|---|---|
| 1 | ~~`1-tonight/run1_eq103_coupling.pdf`~~ | **SPENT** — `DOC-D47USJNBJD73`, 24-Aug 19:19 UTC |
| 2 | ~~`1-tonight/run2_he301_cleaning.pdf`~~ | **SPENT** — `DOC-HXCHGWGKP5QF`, 24-Aug 19:27 UTC |
| 3 | `1-tonight/run3_he302_gasket.pdf` | Tonight, rehearsal 3 — the last rehearsal file you have |
| 4 | `2-preflight/run4_eq102_bearing.pdf` | Tomorrow, warm-up before you go up |
| 5 | `3-demo/oem_bulletin_fp_sb_2026_20.pdf` | **On stage.** Named plausibly — judges see the filename |

Each is a vendor service bulletin dated 20-Aug-2026, stating **one fact nothing else in the corpus
states**. After ingest, ask Copilot that fact back — the answer cites a document that did not exist
ninety seconds earlier.

| File | Ask Copilot | Expect |
|---|---|---|
| run1 | *"What alignment tolerance applies to EQ-103?"* | 0.05 mm parallel offset |
| run2 | *"When is the HE-301 tube bundle due for cleaning?"* | 18 months |
| run3 | *"What is the gasket replacement rule for HE-302?"* | every second opening |
| run4 | *"How often should EQ-102 bearings be regreased?"* | 2,400 operating hours |
| **demo** | *"What seal inspection interval does Fischer recommend for EQ-101 in thermal cycling service?"* | **5,000 operating hours** |

### Verify every ingest — the timeline going green is not proof

`run1` finished at `pipeline_stage: complete`, 100%, no error — and **never reached Elasticsearch**.
Exact-token search missed it entirely; only the semantic arm found it, at rank 3. The UI showed
nothing wrong. `run2`, eight minutes later, was clean, so this is intermittent, not systematic — which
is exactly why you check rather than assume.

After each ingest, take the `document_id` from the response and run:

```
docker exec kairos-backend-api python /app/scripts/verify_ingest.py DOC-XXXXXXXX
```

Read-only, four lines out, one per store — Supabase, Neo4j, Qdrant, Elasticsearch. Non-zero exit if
any store is missing it. **Do this after the pre-flight warm-up on run4**; if Elasticsearch fails
there, expect it on stage and lean on the timeline rather than a Copilot follow-up.

Verified 2026-08-24: 5 distinct SHA-256s, none in the vault, all text-layer extractable with `fitz`,
none caught by the corpus filter. Content is canon-consistent — every asset tag, person, OEM and ID
convention comes from `00_KAIROS_CANON.md`, and each file's fact is unique, so no set can contradict
canon or another set. **HE-3xx pressure is deliberately avoided** — that is the 18.5 → 16.2 bar
blast-radius story behind Beat 8.

`dataset/demo-ingest/spare/` holds 13 more (closeouts, inspection records, one extra bulletin) if you burn
through the five.

### Generating more — `backend/scripts/make_demo_docs.py`

```bash
docker exec kairos-backend-api python /app/scripts/make_demo_docs.py --out /tmp/demo --sets 6 && docker cp kairos-backend-api:/tmp/demo ./dataset/demo-ingest/new-batch
```

PDFs carry a creation timestamp, so **every run produces new SHA-256s even for identical text** —
re-run any time for a fresh batch. Add entries to `SETS` in that file for more topics; the docstring
states the safety rules content must follow.

### Three rules that will bite you

1. **One file, one run.** SHA-256 dedup means a file is spent after one ingest. Rehearsing burns a
   file — that is why there are separate `rehearsal_*` and `warmup_*` copies.
2. **Never name a demo file `test_*`, `tmp*`, `probe*`, `e2e_*` or `kairos_*`.** `services/corpus.py`
   filters those on read: the document ingests fine and is then **invisible** in `/documents`, which
   looks like a broken product. All names here were checked against that predicate.
3. **Every ingest is a permanent cloud write.** Supabase, Neo4j, Qdrant and Elasticsearch — and the
   vault never deletes. Three fresh documents join the golden corpus for good. They are
   canon-consistent so nothing should break, but the published figures in `benchmark/RESULTS.md`
   were measured on the corpus *as it is now*. Ingest after any benchmark re-run, not before.

---

## 14. If the stack fails

Tab 1 alone tells the whole story: the problem, the one-pump scenario end to end, the architecture
diagram, every benchmark number, and the honest-limits block in the FAQ.

Say it once — *"the live stack is down, here is the same story on the page"* — then present the
landing page top to bottom, in the same beat order. **Do not debug on stage.**
