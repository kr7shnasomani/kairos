"""
Form and checklist field extraction — Layer 3 → Layer 6.

THE DESTINATION IS THE HARD PART, AND IT IS ALREADY DECIDED
  Pulling `label: value` out of a scanned checklist is the easy half. The question that kept this
  unbuilt was where a field→value pair is allowed to go, and the architecture answers it: a form
  field is **unverified field input**, so it goes to **quarantine**, never to the canonical graph.

  Nothing here writes a `KNOWLEDGE_EDGE`. That is not caution for its own sake — a ticked checkbox
  carries no authority level that would honestly describe it. There is no source to cite, no
  engineer who signed it, and no way to tell a deliberate tick from a stray pen mark. "A
  handwritten checkbox promoted to canonical fact" is the exact failure Layer 6 exists to prevent,
  and the one-way gate with human-only promotion is the mechanism for it.

  So the ceiling is deliberate: this makes form content *reviewable*, not *authoritative*.

WHY `field_observation` AND NOT A NEW `input_type`
  `quarantine_items.input_type` is a CHECK constraint, and adding a value means DROP + re-add
  (a documented pitfall). A form field IS a field observation, so the existing value is honest and
  no migration is needed. The form provenance lives in `session_context` instead.

LAYOUT
  A digital form is a ruled table, and its text comes out of a PDF as "label" on one line and
  "value" on the next, which a line parser cannot pair. `parse_form_tables` reads the table cells
  instead (PyMuPDF `find_tables`, already a dependency): a cell that stacks a label over its value,
  and an item/result grid under a header row. Measured on the two corpus forms it lifts recall from
  2 and 1 fields to 13 and 9, and drops the one junk row the line parser produced.

ponytail: deterministic, no model call. This covers digital PDFs, which is what the corpus has. A
SCANNED form has no table objects to find, so it still gets the line parser over its OCR text; cell
geometry from pixels needs a vision model and is the upgrade path. Add it when a scanned form
defeats this, not before.
"""

import re
from typing import Any

# "Pressure tested:  16.2 bar" / "Inspector - R. Mehta". Value must be non-empty.
#
# The separator is a colon, or a hyphen/dash **surrounded by whitespace**. An unspaced hyphen is
# NOT a separator: asset tags are hyphenated (`XV-203`, `EQ-101`, `FSL-2240A`) and treating them
# as fields turned every tag in a real checklist into a junk row — label "XV", value "203".
# Observed on `inspection_checklist.pdf` and `work_order_closeout_form.pdf`, which is exactly the
# review-queue noise that trains reviewers to bulk-approve a one-way gate.
#
# The label is bounded to 60 chars so a wrapped prose sentence containing a colon does not
# register as a field — a sentence is not a form field.
_FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ._/()#-]{1,59}?)\s*(?::|\s[-—]\s)\s*(\S.*?)\s*$")

# Ticked: [x] [X] [✓] (•) . Unticked: [] [ ] ( ).
_CHECKED_RE = re.compile(r"^\s*[\[(]\s*([xX✓✔])\s*[\])]\s*(.+?)\s*$")
_UNCHECKED_RE = re.compile(r"^\s*[\[(]\s{0,3}[\])]\s*(.+?)\s*$")

# Lines that look like fields but are structure, not content.
_NOISE_PREFIXES = ("page ", "figure ", "table ", "note:", "notes:", "http://", "https://")


def parse_form_fields(text: str) -> list[dict[str, Any]]:
    """Field→value pairs and checkbox states from a form's extracted text.

    Returns dicts of `{label, value, kind}` where `kind` is `field` or `checkbox`. Order is
    preserved so a reviewer sees the form in reading order rather than an arbitrary map order.
    """
    if not text:
        return []

    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(_NOISE_PREFIXES):
            continue

        m = _CHECKED_RE.match(line)
        if m:
            out.append({"label": m.group(2).strip(), "value": True, "kind": "checkbox"})
            continue

        m = _UNCHECKED_RE.match(line)
        if m:
            out.append({"label": m.group(1).strip(), "value": False, "kind": "checkbox"})
            continue

        m = _FIELD_RE.match(line)
        if m:
            label, value = m.group(1).strip(), m.group(2).strip()
            # A "value" that is itself a sentence is prose that happened to contain a colon.
            if len(value) <= 120:
                out.append({"label": label, "value": value, "kind": "field"})
    return out


_MAX_LABEL, _MAX_VALUE = 60, 120


def _clean(cell: str | None) -> str:
    return (cell or "").strip()


def parse_form_tables(tables: list[list[list[str | None]]]) -> list[dict[str, Any]]:
    """Field→value pairs from a form's table cells (one list of rows per table).

    Two layouts, both from real corpus forms:
      * a cell stacking a label over its value: ``"Asset Tag\nXV-203"``;
      * an item/result grid: a header row (``Checklist Item | Result``) then one row per item.
    Anything else is left alone. The same bounds as the line parser apply: a long "label" or a long
    "value" is prose, not a field.
    """
    out: list[dict[str, Any]] = []
    for rows in tables:
        in_grid = False
        for row in rows:
            cells = [c for c in map(_clean, row) if c]
            if len(cells) == 2 and "\n" not in cells[0]:
                # First such row is the grid's header; the rows after it are item / result.
                if in_grid:
                    _add(out, cells[0], cells[1])
                in_grid = True
                continue
            for cell in cells:
                label, _, value = cell.partition("\n")
                if value:
                    _add(out, label, value)
    return out


def _add(out: list[dict[str, Any]], label: str, value: str) -> None:
    label, value = label.strip().rstrip(":"), " ".join(value.split())
    if label and value and len(label) <= _MAX_LABEL and len(value) <= _MAX_VALUE:
        out.append({"label": label, "value": value, "kind": "field"})


def combine_fields(table_fields: list[dict[str, Any]], line_fields: list[dict[str, Any]],
                 tables: list[list[list[str | None]]]) -> list[dict[str, Any]]:
    """Table fields first, then the line-parsed fields that are not already inside a table cell.

    A line the line parser matched inside a cell is a fragment of that cell (it read
    ``Satisfactory - minor surface`` as a field), so the table's reading of it wins.
    """
    cell_text = " ".join(" ".join(_clean(c).split()) for rows in tables for row in rows for c in row).casefold()
    seen = {f["label"].casefold() for f in table_fields}
    extra = [
        f for f in line_fields
        if f["label"].casefold() not in seen and not (cell_text and str(f["value"]).casefold() in cell_text)
    ]
    return table_fields + extra


def extract_tables(pdf_bytes: bytes) -> list[list[list[str | None]]]:
    """The cell text of every table in a digital PDF. Empty for a scan or an unreadable file."""
    import fitz  # lazy: the Celery worker imports this module per task

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            return [t.extract() for page in doc for t in page.find_tables().tables]
    except Exception:  # noqa: BLE001 — a PDF the library cannot read falls back to the line parser
        return []


def quarantine_items_for(
    document_id: str,
    fields: list[dict[str, Any]],
    *,
    asset_id: str | None = None,
    submitted_by: str = "extraction_pipeline",
) -> list[dict[str, Any]]:
    """Quarantine rows for parsed form fields — the ONLY destination they are allowed.

    `asset_id` is passed through unvalidated on purpose: `quarantine_items.asset_id` is a FK, and
    an unresolvable tag must arrive as `None` rather than `""` (a documented FK-failure pitfall).
    Linking the item to an asset is part of human review, not of parsing.
    """
    rows = []
    for f in fields:
        value = f["value"]
        shown = ("checked" if value else "not checked") if f["kind"] == "checkbox" else value
        rows.append({
            "asset_id": asset_id or None,
            "content": f"{f['label']}: {shown}",
            # An existing enum value that is honest — a form field is field input. See module docstring.
            "input_type": "field_observation",
            "submitted_by": submitted_by,
            "session_context": {
                "source": "form_extraction",
                "document_id": document_id,
                "field_label": f["label"],
                "field_value": value,
                "field_kind": f["kind"],
                # States the ceiling on the item itself, so a reviewer promoting it is not relying
                # on the module docstring to know what they are looking at.
                "note": (
                    "Parsed from a form/checklist. Unverified field input: no authority level, "
                    "no signer. Promote only after checking the value against the source document."
                ),
            },
        })
    return rows
