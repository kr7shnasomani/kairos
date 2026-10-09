"""Form / checklist extraction — Layer 3 → Layer 6.

The load-bearing property is the **destination**: parsed form fields go to quarantine and never
to the canonical graph. A ticked checkbox carries no authority a KNOWLEDGE_EDGE could honestly
record, and "a handwritten checkbox promoted to canonical fact" is the exact failure Layer 6
exists to prevent.

Pure logic. No stack, no secrets, no network.
"""

import inspect

from api.services.forms import combine_fields, parse_form_fields, parse_form_tables, quarantine_items_for

FORM = """
Inspection Checklist — HE-301
Inspector: R. Mehta
Date: 2026-06-12
Pressure tested: 16.2 bar
[x] Shell-side isolation verified
[ ] Tube bundle removed
(✓) Gaskets replaced
Page 1 of 2
Notes: see attached photographs for the corroded section near the inlet nozzle
"""


# =============================================================================
# The destination — the part that matters
# =============================================================================

def test_every_field_goes_to_quarantine_as_field_input():
    rows = quarantine_items_for("DOC-1", parse_form_fields(FORM))
    assert rows, "expected parsed fields"
    assert all(r["input_type"] == "field_observation" for r in rows)


def test_nothing_in_this_module_writes_a_knowledge_edge():
    """The one-way gate only holds if the parser cannot bypass it."""
    import ast

    from api.services import forms

    # AST, not a substring search: the module's prose explains *why* a form field gets no
    # authority level and cannot write a KNOWLEDGE_EDGE, so searching the raw source matches the
    # explanation instead of the behaviour. Unparsing a docstring-stripped tree leaves only code.
    tree = ast.parse(inspect.getsource(forms))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant
            ) and isinstance(body[0].value.value, str):
                body.pop(0)
    code = ast.unparse(tree)

    assert "KNOWLEDGE_EDGE" not in code
    assert "create_knowledge_edge" not in code
    assert "authority_level" not in code, "a form field has no authority level to assign"
    assert "merge_" not in code, "nothing here may MERGE a graph node"


def test_each_item_states_its_own_ceiling_to_the_reviewer():
    """A reviewer promoting an item must not have to read the module docstring to learn it is
    unverified field input."""
    rows = quarantine_items_for("DOC-1", parse_form_fields(FORM))
    note = rows[0]["session_context"]["note"]
    assert "Unverified field input" in note
    assert "no authority" in note


def test_unresolvable_asset_is_none_never_empty_string():
    """`quarantine_items.asset_id` is a FK: "" fails the constraint, None is correct."""
    rows = quarantine_items_for("DOC-1", parse_form_fields(FORM), asset_id="")
    assert rows[0]["asset_id"] is None


# =============================================================================
# Parsing
# =============================================================================

def test_labelled_fields_are_extracted():
    fields = {f["label"]: f["value"] for f in parse_form_fields(FORM) if f["kind"] == "field"}
    assert fields["Inspector"] == "R. Mehta"
    assert fields["Pressure tested"] == "16.2 bar"


def test_checkbox_state_is_captured_both_ways():
    boxes = {f["label"]: f["value"] for f in parse_form_fields(FORM) if f["kind"] == "checkbox"}
    assert boxes["Shell-side isolation verified"] is True
    assert boxes["Tube bundle removed"] is False
    assert boxes["Gaskets replaced"] is True


def test_structural_lines_are_not_mistaken_for_fields():
    labels = [f["label"] for f in parse_form_fields(FORM)]
    assert not any(l.lower().startswith("page") for l in labels)


def test_prose_containing_a_colon_is_not_a_field():
    """A sentence is not a form field. Treating it as one fills the review queue with noise,
    which trains reviewers to bulk-approve — the worst outcome for a one-way gate."""
    labels = [f["label"] for f in parse_form_fields(FORM)]
    assert "Notes" not in labels


def test_empty_input_is_handled():
    assert parse_form_fields("") == []
    assert parse_form_fields("   \n  \n") == []
    assert quarantine_items_for("DOC-1", []) == []


# =============================================================================
# Layout: table cells, as PyMuPDF returns them for the two corpus forms
# =============================================================================

CHECKLIST = [
    [
        ["", "Asset Tag\nXV-203", "Inspection Date\n12-May-2025", None, ""],
        [None, "Location\nProduction Line 3, Section 2", "Inspector\nAnanya Iyer, Reliability Engineer", None, None],
        ["Checklist Item", None, None, "Result", None],
        ["Valve operable through full stroke", None, None, "Pass", None],
        ["Corrosion / external condition of body", None, None, "Satisfactory - minor surface\ncorrosion, within tolerance", None],
    ],
    [["Inspector\nAnanya Iyer (signed 12-May-2025)", "Approved By\nVikram Desai, Shift Lead"]],
]


def _as_map(fields):
    return {f["label"]: f["value"] for f in fields}


def test_a_cell_stacking_label_over_value_is_one_field():
    got = _as_map(parse_form_tables(CHECKLIST))
    assert got["Asset Tag"] == "XV-203"  # the hyphenated tag stays whole
    assert got["Inspection Date"] == "12-May-2025"
    assert got["Approved By"] == "Vikram Desai, Shift Lead"


def test_an_item_result_grid_pairs_each_item_with_its_result_and_skips_the_header():
    got = _as_map(parse_form_tables(CHECKLIST))
    assert got["Valve operable through full stroke"] == "Pass"
    assert got["Corrosion / external condition of body"] == "Satisfactory - minor surface corrosion, within tolerance"
    assert "Checklist Item" not in got


def test_prose_in_a_cell_is_not_a_field():
    long_value = "word " * 40
    assert parse_form_tables([[["Failure Description\n" + long_value, "x" * 80 + "\nvalue"]]]) == []
    assert parse_form_tables([[["no newline, one cell"]], []]) == []


def test_the_table_reading_replaces_a_line_fragment_of_the_same_cell():
    line_fields = [
        {"label": "Record No", "value": "INSP-XV203-2025-Q2", "kind": "field"},   # outside the tables: kept
        {"label": "Satisfactory", "value": "minor surface", "kind": "field"},     # a fragment of a cell: dropped
        {"label": "asset tag", "value": "XV", "kind": "field"},                   # same label as a table field: dropped
    ]
    merged = combine_fields(parse_form_tables(CHECKLIST), line_fields, CHECKLIST)
    labels = [f["label"] for f in merged]
    assert "Record No" in labels and "Satisfactory" not in labels and "asset tag" not in labels
    assert labels[0] == "Asset Tag"  # table fields lead, in reading order


def test_without_tables_the_line_fields_pass_through_unchanged():
    fields = parse_form_fields(FORM)
    assert combine_fields([], fields, []) == fields


# =============================================================================
# The trigger: POST /documents/{id}/extract-form, a person asking for one document
# =============================================================================

class _Query:
    def __init__(self, data, count=None):
        self.data, self.count = data, count

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return self


class _FormSupabase:
    def __init__(self, doc, existing=0, link=None):
        self._tables = {
            "documents": _Query([doc] if doc else []),
            "quarantine_items": _Query([], count=existing),
            "document_asset_links": _Query([{"asset_id": link}] if link else []),
            "audit_log": _Query([]),
        }

    def table(self, name):
        return self._tables[name]


def _extract(monkeypatch, supabase, role="reliability"):
    import asyncio

    import workers.extraction as extraction
    from api.routers import documents

    calls = []

    async def fake_extract(document_id, asset_id, submitted_by="extraction_pipeline"):
        calls.append((document_id, asset_id, submitted_by))
        return {"document_id": document_id, "fields": 13, "status": "quarantined"}

    monkeypatch.setattr(extraction, "extract_form", fake_extract)
    user = {"user_id": "u-9", "role": role}
    return asyncio.run(documents.extract_form_fields("DOC-1", supabase, current_user=user)), calls


def test_extract_form_runs_once_and_names_the_person_who_asked(monkeypatch):
    out, calls = _extract(monkeypatch, _FormSupabase({"document_id": "DOC-1", "access_tags": {}}, link="XV-203"))
    assert out == {"document_id": "DOC-1", "fields": 13, "status": "quarantined"}
    assert calls == [("DOC-1", "XV-203", "u-9")]


def test_a_second_request_for_the_same_document_is_refused(monkeypatch):
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _extract(monkeypatch, _FormSupabase({"document_id": "DOC-1", "access_tags": {}}, existing=13))
    assert exc.value.status_code == 409


def test_an_unknown_document_is_a_404(monkeypatch):
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _extract(monkeypatch, _FormSupabase(None))
    assert exc.value.status_code == 404


def test_a_showcase_document_with_no_asset_gets_the_showcase_placeholder_never_null(monkeypatch):
    from api.services import tenant

    doc = {"document_id": "DOC-1", "access_tags": {"site_id": sorted(tenant.DEMO_SITES)[0]}}
    _, calls = _extract(monkeypatch, _FormSupabase(doc), role="demo")
    assert calls[0][1] == tenant.DEMO_GENERAL_ASSET
    _, real = _extract(monkeypatch, _FormSupabase({"document_id": "DOC-1", "access_tags": {}}))
    assert real[0][1] is None
