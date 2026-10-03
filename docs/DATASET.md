# Kairos — Golden Demo Dataset

The `dataset/` directory is a purpose-built, internally-consistent corpus that serves two roles:

1. **Canonical demo state** — a deterministic set of documents, events, and structured records that
   exercises every Kairos flow (A–D) and layer end-to-end.
2. **Evaluation benchmark** — `00_Reference/00_KAIROS_CANON.md` is the single source of truth for every
   fact (assets, dates, tag numbers, the failure narrative), so answers can be scored against it.

**Setting:** Rajgarh Petrochemical Complex (RPC), Gujarat. In-story "today" = 15-Jul-2026.

## Structure

| Folder | Contents |
|---|---|
| `00_Reference/` | `00_KAIROS_CANON.md` (ground truth), `dataset_manifest.csv` (file → ingestion path / flow / layer), `VERIFICATION_REPORT.md` |
| `01_Structured_Backbone/` | `asset_registry.csv` (10 assets), `alias_table.csv` (11 aliases incl. "the old Fischer"→EQ-101), `telemetry_eq101.csv` (140 OT readings), `work_orders_eq101_family.csv` |
| `02_Document_Corpus/` | 14 PDFs + a P&ID PNG — OEM manuals/bulletins, SOPs, inspection records, PTW, regulatory excerpts |
| `03_Multiformat_Variants/` | Handwritten, scanned/degraded, and Hinglish variants — OCR and multi-script stress |
| `04_Events_And_Quarantine/` | Event JSONs (work order, PTW, shift handover, recurring failure), quarantine items, and a field voice note (`.mp3` + transcript) |

## The narrative it encodes

- **Flow A — the knowledge gap Kairos exists to close.** Fischer issues seal bulletin `FSL-2240A → FSL-2240B`
  (Jan 2025); it never reaches the stores before EQ-101's third seal failure (May 2025), which is repaired
  with the *old* part. On demo day a new EQ-101 work order opens with live telemetry matching that signature.
- **Flow B — PTW dual sign-off.** `PTW-2026-0714` isolates V-247; a quarantined PG-18 deviation rides along.
- **Flow C — silent knowledge decay.** Meridian revises HE-3xx max pressure `18.5 → 16.2 bar`; the blast radius
  contaminates four SOPs and two inspection records that still cite the old limit.

## Loading it

The dataset is mounted read-only into the API container at `/app/dataset`. Load it through the **real**
API endpoints so the true pipeline runs (OCR → NER → graph → index for documents; brief assembly for events):

```bash
make load-dataset                 # full pipeline (needs NIM/Groq keys + Temporal running)
make load-dataset ARGS=--fast     # structured backbone + events only, no document pipeline
```

Everything is idempotent — assets `MERGE`, documents dedup by SHA-256 — so re-running is safe.

Loader: `backend/scripts/load_demo_dataset.py`. The file → `document_type` / `authority_level` / `asset_id`
mapping lives in that script (`DOCS`), derived from `dataset_manifest.csv` and the canon. The loader also
registers a demo **off-boarding programme** (departing expert `ramesh.kumar@kairos.local`, 5 equipment-family
sessions) via the real `POST /elicitation/offboarding` — idempotent, so re-running it won't duplicate. The
per-session interview questions are then generated asynchronously by the off-boarding Celery worker (NIM).

### Keeping it current for a demo

The four event JSONs carry fixed dates (2026-03-22, 2026-07-15) and the loader copies them verbatim, so as
the calendar moves on the events age out of the RCA and recurring-failure windows (90/30 days) and the
Overview trend ends in the past. Everything else the loader writes (SLA deadlines, brief times) is already
relative to load time. Shift the data, not a clock:

```bash
make redate-demo           # dry run: prints the anchor, the shift and every before/after
make redate-demo APPLY=1   # writes: cloud Supabase + Neo4j
```

One whole-day shift moves the newest **golden** event to "yesterday" and every other golden event by the
same amount, so order, spacing and time of day are kept. Golden means the rows the loader created from these
four files, matched with the loader's own mapping on (source system, event type, work order / PTW id / shift
lead). Events created live during a demo, or by a QA sweep, never match, so they can neither become the
anchor nor be pushed into the future. The off-boarding programme is shifted separately (first interview →
yesterday). Re-running on the same day shifts by 0.

Writes are ordered so a re-run after any failure is safe: Neo4j first with absolute values, then all golden
events in one bulk upsert (one transaction); per off-boarding programme the retirement date, then its
interviews in one upsert, with the retirement date put back if that fails. `APPLY=1` modifies the golden
stores; no benchmark question pins an event date (checked 2026-09-27), but re-run the benchmark after the
first apply.

## The showcase plant (the demo login's data)

A second, fictional plant (Veridian Petrochemicals: a 119-asset complex and a 38-asset tank farm, about 470 documents (about 70 written by hand,
three generated records per piece of equipment, and a dated failure history card for each of the eight recurring failures), 90 days of about 700 events, ten knowledge conflicts, a full governance queue, off-boarding programmes) that the one-click demo login works.
It lives in the same stores as this dataset, marked by `DEMO-` ids and showcase sites, and every login sees it
(`SHOWCASE_VISIBLE_TO_ALL=true`; false hides it from everyone but the demo role). The benchmark graders never count it, but
retrieval for a benchmark run should be measured with the switch off. Nothing in it is shared with the golden dataset (no tag, person, vendor or part
number), because the graph merges those by text. Design and decisions: `docs/implementation/demo-data.md`.

```bash
make load-showcase                  # dry run: the plan, an audit of every row's marker, what is already loaded
make load-showcase APPLY=1          # writes the current stores (needs SHOWCASE_CONFIRM=load-showcase-into-current-stores)
make generate-showcase              # rewrite the showcase_* files in dataset/ from the generator (touches no store, no golden file)
make redate-showcase                # keep it current: shift its dates so the newest event is yesterday
make reset-showcase                 # undo what visitors changed (state only, never the vault)
```

The data is files in this dataset, beside the golden ones in the same folders, every data file named `showcase_*` (`00_Reference`, `01_Structured_Backbone`,
`02_Document_Corpus`, `03_Multiformat_Variants`, `04_Events_And_Quarantine`, plus `05_Governance_And_Handover` for briefs, MoC and
off-boarding). The loader, redate and reset read only those files; `make generate-showcase` is how they are (re)written, and its
README (`dataset/00_Reference/SHOWCASE_README.md`) lists what is where. The golden files are never written, and the golden loader names its files one by one, so it never reads these.

Dates in the files are as at a snapshot anchor and are moved to the load time on read, so it never goes stale: `redate-showcase` (or `SHOWCASE_AUTO_REDATE=true`)
moves the loader's own rows forward, and a visitor's rows are never touched. The load takes the demo account's real
id for the briefs addressed to it, runs the documents through the real pipeline, and asserts the real-mode counts are
identical before and after.

## Using it as a benchmark

Because `00_KAIROS_CANON.md` fixes every fact, it is the answer key for the Problem Statement's evaluation
focus — entity-extraction accuracy, copilot answer quality, blast-radius correctness, and compliance-gap
detection. Query the loaded stack and score responses against the canon. The automated harness that does
exactly this lives in [`benchmark/`](../benchmark) — methodology in [`BENCHMARKS.md`](./BENCHMARKS.md),
latest run in [`benchmark/RESULTS.md`](../benchmark/RESULTS.md).

## Data hygiene

The golden dataset is the *canonical* state. Integration-test entities (prefixed `ASSET-TEST-`,
`ASSET-DEDUP-`, `WO-*`, `DOC-*`, …) must never mix into it — the suite purges its own residue on teardown,
and `make purge-test-data` removes any that leak. For a guaranteed-clean rebuild:
`make nuke && make dev && make init-all && make seed && make load-dataset`. See [`TESTS.md`](./TESTS.md).
