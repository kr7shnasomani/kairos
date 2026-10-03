# Showcase data (the demo login's plant)

An extension of this dataset: the same six folders, new files beside the golden ones (every data file starts
with `showcase_`). The golden files are untouched and the golden loader never reads these. The showcase is
a second, fictional plant (Veridian Petrochemicals, two sites) that the public demo login works, and **the
loader reads these files**: `make load-showcase` pushes them through the real system (assets and documents
through the API and the ingest pipeline, the rest straight into the tables). Edit a file and the next load
uses it.

| Folder | Showcase files |
|---|---|
| `00_Reference` | this file, `showcase_manifest.json` (snapshot anchor, counts), `showcase_document_manifest.csv` (every showcase document and where it lives) |
| `01_Structured_Backbone` | `showcase_asset_registry.csv` (158 assets with the DEMO-GENERAL placeholder), `showcase_alias_table.json`, `showcase_plant_operating_states.json` |
| `02_Document_Corpus` | the PDF documents (manuals, bulletins, procedures, inspection reports, regulation summaries), listed in the manifest |
| `03_Multiformat_Variants` | the plain-text documents (shift logs, permits), listed in the manifest |
| `04_Events_And_Quarantine` | `showcase_operational_events.json` (699 events), `showcase_live_events.json` (9 sent through the event API), quarantine, knowledge conflicts |
| `05_Governance_And_Handover` | `showcase_briefs.json` and feedback, MoC, knowledge capture, off-boarding (new folder; the golden set has no governance output) |

476 showcase documents in all. Dates are written as at the anchor in `showcase_manifest.json`; the
loader moves them to the moment of loading and swaps in the demo account's id and each document's real id.
Every row carries a showcase marker (`DEMO-` asset or person id, or a `SITE_DEMO` site), which keeps it out of
real accounts.

Regenerate with `make generate-showcase` (writes only the showcase files). Load with `make load-showcase`
(a dry run until `APPLY=1`).
