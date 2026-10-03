"""The showcase plant as dataset files, in the same six folders as the golden set, beside the golden files.

The showcase is an extension of `dataset/`: same folders, new files. Golden files are never written, read
or renamed here. Every data file carries a `showcase_` prefix (and the README `SHOWCASE_`), and the documents
keep names that no golden file uses (a test pins both), so the two sets share folders but never a file. The
golden loader names its files one by one, so it cannot pick a showcase file up. The generator
(`scripts/generate_showcase.py`) writes these files; the loader (`scripts/load_showcase.py`), the redate and
the reset read them. Nothing at load time rebuilds the data, so a file edited by hand is what gets loaded.

    00_Reference               SHOWCASE_README.md, showcase_manifest.json, showcase_document_manifest.csv
    01_Structured_Backbone     showcase_asset_registry.csv, showcase_alias_table.json, showcase_plant_operating_states.json
    02_Document_Corpus         the PDF documents, exactly as they are uploaded
    03_Multiformat_Variants    the plain-text documents (shift logs, permits)
    04_Events_And_Quarantine   showcase_operational_events.json, showcase_live_events.json, quarantine, conflicts
    05_Governance_And_Handover showcase_briefs.json, brief feedback, MoC, knowledge capture, off-boarding

Dates are stored as written at the snapshot anchor (`showcase_manifest.json`). `bind` moves them to the
moment of loading, and swaps in the real ids that did not exist when the files were written: the demo
account's id (recipients) and each document's id in the vault (sources).
"""

import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.showcase.docs import Doc
from scripts.showcase.history import Showcase, pending_id
from scripts.showcase.redate import TIME_COLUMNS, shift_row, shift_value
from scripts.showcase.spec import GENERAL_ASSET, Asset

REF = "00_Reference"
BACKBONE = "01_Structured_Backbone"
CORPUS = "02_Document_Corpus"
VARIANTS = "03_Multiformat_Variants"
EVENTS = "04_Events_And_Quarantine"
GOVERNANCE = "05_Governance_And_Handover"

# Where each table's rows live. Every table the loader writes is in here; a test fails if one is missing.
TABLE_HOME = {
    "asset_alias_map": (BACKBONE, "showcase_alias_table.json"),
    "plant_operating_states": (BACKBONE, "showcase_plant_operating_states.json"),
    "operational_events": (EVENTS, "showcase_operational_events.json"),
    "quarantine_items": (EVENTS, "showcase_quarantine_items.json"),
    "knowledge_conflicts": (EVENTS, "showcase_knowledge_conflicts.json"),
    "briefs": (GOVERNANCE, "showcase_briefs.json"),
    "brief_feedback": (GOVERNANCE, "showcase_brief_feedback.json"),
    "moc_items": (GOVERNANCE, "showcase_moc_items.json"),
    "elicitation_sessions": (GOVERNANCE, "showcase_elicitation_sessions.json"),
    "offboarding_sessions": (GOVERNANCE, "showcase_offboarding_sessions.json"),
    "offboarding_session_items": (GOVERNANCE, "showcase_offboarding_session_items.json"),
}
LIVE_EVENTS = (EVENTS, "showcase_live_events.json")
REGISTER = (BACKBONE, "showcase_asset_registry.csv")
MANIFEST = (REF, "showcase_document_manifest.csv")
META = (REF, "showcase_manifest.json")
# `Showcase` attribute for each table.
FIELD = {
    "asset_alias_map": "aliases", "plant_operating_states": "plant_states", "operational_events": "history_events",
    "quarantine_items": "quarantine", "knowledge_conflicts": "conflicts", "briefs": "briefs", "brief_feedback": "brief_feedback",
    "moc_items": "moc_items", "elicitation_sessions": "elicitation_sessions", "offboarding_sessions": "offboarding_sessions",
    "offboarding_session_items": "offboarding_items",
}
REGISTER_COLUMNS = ("asset_id", "tag_number", "name", "equipment_class", "criticality", "site_id", "facility_id",
                    "parent_asset_id", "unit", "aliases")
MANIFEST_COLUMNS = ("file_name", "path", "title", "document_type", "authority_level", "asset_id", "age_days", "mime")
# Time-valued keys inside a live event's request body.
LIVE_TIME_KEYS = ("occurred_at", "handover_time")


@dataclass(frozen=True)
class DocFile:
    """A document as the loader sees it: the manifest row, and the file to upload."""
    file_name: str
    document_type: str
    authority: int
    asset_id: str
    age_days: int
    mime: str
    title: str
    path: Path

    def data(self) -> bytes:
        return self.path.read_bytes()


@dataclass
class Dataset:
    anchor: datetime
    demo_user_placeholder: str
    assets: list[Asset]  # includes the DEMO-GENERAL placeholder, so the loader posts exactly this list
    docs: list[DocFile]
    showcase: Showcase  # as written: dates at the anchor, placeholder ids


def render_document(doc: Doc) -> bytes:
    """The document as bytes: a text PDF for PDF documents, UTF-8 for the plain-text ones."""
    if doc.mime != "application/pdf":
        return doc.text.encode()
    import fitz  # PyMuPDF, already in the image

    pdf = fitz.open()
    lines = doc.text.split("\n")
    page, y = None, 0.0
    for line in lines:
        if page is None or y > 780:
            page = pdf.new_page(width=595, height=842)
            y = 60.0
        # insert_textbox would wrap; a short manual wrap keeps the text layer plain and readable
        while len(line) > 95:
            cut = line.rfind(" ", 0, 95)
            cut = cut if cut > 0 else 95
            page.insert_text((50, y), line[:cut], fontsize=10)
            line, y = line[cut:].lstrip(), y + 13
            if y > 780:
                page, y = pdf.new_page(width=595, height=842), 60.0
        page.insert_text((50, y), line, fontsize=10)
        y += 13
    # No creation date and no fresh file id: the same text renders to the same bytes, so regenerating the
    # dataset changes a file only when its content changed.
    pdf.set_metadata({"title": doc.title, "producer": "Veridian document control", "creationDate": "", "modDate": ""})
    out = pdf.tobytes(deflate=True, garbage=3, no_new_id=True)
    pdf.close()
    return out


def showcase_root() -> Path:
    """Where the dataset lives (`SHOWCASE_DIR` overrides it, for a copy under review)."""
    return Path(os.getenv("SHOWCASE_DIR", "/app/dataset"))


def _folder_for(doc: Doc) -> str:
    return CORPUS if doc.mime == "application/pdf" else VARIANTS


def _put(root: Path, home: tuple[str, str], text: str) -> None:
    (root / home[0]).mkdir(parents=True, exist_ok=True)
    (root / home[0] / home[1]).write_text(text)


def _csv(root: Path, home: tuple[str, str], columns: tuple[str, ...], rows: list[list]) -> None:
    (root / home[0]).mkdir(parents=True, exist_ok=True)
    with (root / home[0] / home[1]).open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        w.writerows(rows)


def write(root: Path, assets: list[Asset], docs: list[Doc], sc: Showcase, *, demo_user_placeholder: str) -> dict[str, int]:
    """Write the dataset to `root`. Touches no store. `sc` must be built at `sc.anchor` with
    `demo_user_placeholder` as the demo account's id and no document ids (so sources carry `pending_id`)."""
    for doc in docs:
        folder = root / _folder_for(doc)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / doc.file_name).write_bytes(render_document(doc))
    _csv(root, MANIFEST, MANIFEST_COLUMNS, [
        [d.file_name, f"{_folder_for(d)}/{d.file_name}", d.title, d.document_type, d.authority, d.asset_id, d.age_days, d.mime]
        for d in docs
    ])
    _csv(root, REGISTER, REGISTER_COLUMNS, [
        [a.asset_id, a.tag, a.name, a.equipment_class, a.criticality, a.site_id, a.facility_id, a.parent or "", a.unit, "|".join(a.aliases)]
        for a in [GENERAL_ASSET, *assets]
    ])
    counts = {"documents": len(docs), "assets": len(assets) + 1}
    for table, rows in sc.tables().items():
        _put(root, TABLE_HOME[table], json.dumps(rows, indent=2))
        counts[table] = len(rows)
    _put(root, LIVE_EVENTS, json.dumps([{"route": r, "body": b} for r, b in sc.live_events], indent=2))
    counts["live_events"] = len(sc.live_events)
    _put(root, META, json.dumps({"anchor": sc.anchor.isoformat(), "demo_user_placeholder": demo_user_placeholder, "counts": counts}, indent=2))
    _put(root, (REF, "SHOWCASE_README.md"), _readme(counts))
    return counts


def read(root: Path) -> Dataset:
    """Load the dataset from `root`, exactly as written."""
    meta = json.loads((root / META[0] / META[1]).read_text())
    with (root / REGISTER[0] / REGISTER[1]).open(newline="") as fh:
        assets = [Asset(asset_id=r["asset_id"], tag=r["tag_number"], name=r["name"], equipment_class=r["equipment_class"],
                        criticality=r["criticality"], site_id=r["site_id"], parent=r["parent_asset_id"] or None, unit=r["unit"],
                        aliases=tuple(filter(None, r["aliases"].split("|")))) for r in csv.DictReader(fh)]
    with (root / MANIFEST[0] / MANIFEST[1]).open(newline="") as fh:
        docs = [DocFile(file_name=r["file_name"], document_type=r["document_type"], authority=int(r["authority_level"]),
                        asset_id=r["asset_id"], age_days=int(r["age_days"]), mime=r["mime"], title=r["title"],
                        path=root / r["path"]) for r in csv.DictReader(fh)]
    anchor = datetime.fromisoformat(meta["anchor"])
    tables = {t: json.loads((root / home[0] / home[1]).read_text()) for t, home in TABLE_HOME.items()}
    live = [(e["route"], e["body"]) for e in json.loads((root / LIVE_EVENTS[0] / LIVE_EVENTS[1]).read_text())]
    sc = Showcase(assets=assets, anchor=anchor, live_events=live, **{FIELD[t]: rows for t, rows in tables.items()})
    return Dataset(anchor=anchor, demo_user_placeholder=meta["demo_user_placeholder"], assets=assets, docs=docs, showcase=sc)


def _replace(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        for old, new in mapping.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [_replace(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: _replace(v, mapping) for k, v in value.items()}
    return value


def bind(ds: Dataset, *, now: datetime, demo_user_id: str | None = None, doc_ids: dict[str, str] | None = None) -> Showcase:
    """The dataset as it is written to the stores at `now`: every time moved by the distance from the
    snapshot anchor to `now`, the demo account's real id for recipients, real document ids for sources."""
    delta = now - ds.anchor
    mapping = {pending_id(name): doc_id for name, doc_id in (doc_ids or {}).items()}
    if demo_user_id:
        mapping[ds.demo_user_placeholder] = demo_user_id
    src = ds.showcase
    tables = {t: [_replace(shift_row(t, r, delta) if t in TIME_COLUMNS else r, mapping) for r in rows]
              for t, rows in src.tables().items()}
    live = [(route, _replace({k: shift_value(v, delta) if k in LIVE_TIME_KEYS else v for k, v in body.items()}, mapping))
            for route, body in src.live_events]
    return Showcase(assets=src.assets, anchor=now, live_events=live, **{FIELD[t]: rows for t, rows in tables.items()})


def _readme(counts: dict[str, int]) -> str:
    return f"""# Showcase data (the demo login's plant)

An extension of this dataset: the same six folders, new files beside the golden ones (every data file starts
with `showcase_`). The golden files are untouched and the golden loader never reads these. The showcase is
a second, fictional plant (Veridian Petrochemicals, two sites) that the public demo login works, and **the
loader reads these files**: `make load-showcase` pushes them through the real system (assets and documents
through the API and the ingest pipeline, the rest straight into the tables). Edit a file and the next load
uses it.

| Folder | Showcase files |
|---|---|
| `00_Reference` | this file, `showcase_manifest.json` (snapshot anchor, counts), `showcase_document_manifest.csv` (every showcase document and where it lives) |
| `01_Structured_Backbone` | `showcase_asset_registry.csv` ({counts['assets']} assets with the DEMO-GENERAL placeholder), `showcase_alias_table.json`, `showcase_plant_operating_states.json` |
| `02_Document_Corpus` | the PDF documents (manuals, bulletins, procedures, inspection reports, regulation summaries), listed in the manifest |
| `03_Multiformat_Variants` | the plain-text documents (shift logs, permits), listed in the manifest |
| `04_Events_And_Quarantine` | `showcase_operational_events.json` ({counts['operational_events']} events), `showcase_live_events.json` ({counts['live_events']} sent through the event API), quarantine, knowledge conflicts |
| `05_Governance_And_Handover` | `showcase_briefs.json` and feedback, MoC, knowledge capture, off-boarding (new folder; the golden set has no governance output) |

{counts['documents']} showcase documents in all. Dates are written as at the anchor in `showcase_manifest.json`; the
loader moves them to the moment of loading and swaps in the demo account's id and each document's real id.
Every row carries a showcase marker (`DEMO-` asset or person id, or a `SITE_DEMO` site), which keeps it out of
real accounts.

Regenerate with `make generate-showcase` (writes only the showcase files). Load with `make load-showcase`
(a dry run until `APPLY=1`).
"""
