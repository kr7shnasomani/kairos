"""
PII detection and redaction — DPDP Act 2023 boundary control.

Redaction runs at *export* boundaries only, never at ingestion. Operational
knowledge legitimately contains personnel names — "which technician signed off
the EQ-101 seal repair" is a real maintenance question the vault must answer.
Stripping names on the way in would destroy that; stripping them on the way out
is what the DPDP obligation actually requires.

Detection is regex for structured identifiers (no model needed, no false negatives
on format) plus caller-supplied PERSON names, which come from the existing NER
service rather than a second name model, plus context patterns for names the model never saw.
"""

import re
from collections.abc import Iterable
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Structured identifier patterns. Ordered most-specific first so a PAN is not
# partially consumed by a looser numeric rule.
# ponytail: over-redaction is the safe direction for a privacy control — a false
# positive costs one masked token, a false negative is a DPDP breach. Tighten only
# with a test that pins the value that was wrongly masked.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    # Aadhaar is printed as 1234 5678 9012, 1234-5678-9012 or unspaced.
    ("AADHAAR", re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
    ("EMPLOYEE_ID", re.compile(r"\bEMP[-/ ]?\d{3,6}\b", re.IGNORECASE)),
    ("SHIFT_ID", re.compile(r"\b(?:SHIFT|SH)[-/ ]?(?:ID[-/ ]?)?\d{2,6}\b", re.IGNORECASE)),
    # Indian mobile: optional +91 / (+91) / 91 / 0 prefix, then 10 digits starting 6-9, optionally
    # split 5+5 ("+91 98765 43210"). Guarded on both sides so equipment tags and part numbers
    # (EQ-101, MS-4471-B) never match.
    ("PHONE", re.compile(r"(?<![\w-])(?:\(?\+91\)?[-\s]?|91[-\s]|0)?[6-9]\d{4}[-\s]?\d{5}(?![\w-])")),
]

# Names that no model saw. NER reads only the first part of a document, so a person first named
# deeper in the text is not in the caller's list. These catch the two shapes plant paperwork uses:
# an honorific, or a sign-off label. The name is the capture group, so the label stays readable.
_NAME = r"[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){0,2}"
_NAME_CONTEXT = re.compile(
    rf"\b(?:Mr|Mrs|Ms|Miss|Dr|Shri|Smt|Sri|Er)\.?\s+(?P<name>{_NAME})"
    rf"|\b(?:Operator|Technician|Engineer|Supervisor|Inspector|Fitter|Prepared by|Reviewed by|Approved by|"
    rf"Signed by|Witnessed by|Issued by|Authorised by|Authorized by|Performed by|Name)(?:\s*:\s*|\s+-\s+)(?P<name2>{_NAME})"
)


class PIIService:
    """Detects and masks personal identifiers in free text."""

    def detect(self, text: str, person_names: Iterable[str] = ()) -> list[dict[str, Any]]:
        """
        Returns non-overlapping PII spans, ordered by position.
        `person_names` are treated as PERSON matches (whole-word, case-insensitive).
        """
        if not text:
            return []

        spans: list[dict[str, Any]] = []

        for name in {n.strip() for n in person_names if n and len(n.strip()) > 2}:
            for m in re.finditer(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
                spans.append({"text": m.group(0), "pii_type": "PERSON", "start": m.start(), "end": m.end()})

        for pii_type, pattern in _PATTERNS:
            for m in pattern.finditer(text):
                spans.append({"text": m.group(0), "pii_type": pii_type, "start": m.start(), "end": m.end()})

        for m in _NAME_CONTEXT.finditer(text):
            group = "name" if m.group("name") else "name2"
            spans.append({"text": m.group(group), "pii_type": "PERSON", "start": m.start(group), "end": m.end(group)})

        # Resolve overlaps: earliest start wins, longest match breaks ties.
        spans.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))
        deduped: list[dict[str, Any]] = []
        last_end = -1
        for s in spans:
            if s["start"] >= last_end:
                deduped.append(s)
                last_end = s["end"]
        return deduped

    def redact(self, text: str, person_names: Iterable[str] = ()) -> dict[str, Any]:
        """
        Masks every detected identifier with a stable pseudonym (`[PERSON_1]`).

        Pseudonyms are consistent within a document, so "Ravi Kumar" is always
        `[PERSON_1]` — cross-references in the text survive redaction, which a
        blanket `[REDACTED]` would destroy.
        """
        spans = self.detect(text, person_names)
        if not spans:
            return {"redacted_text": text, "spans": [], "counts": {}, "pii_found": False}

        aliases: dict[tuple[str, str], str] = {}
        counters: dict[str, int] = {}
        out: list[str] = []
        cursor = 0

        for s in spans:
            key = (s["pii_type"], s["text"].lower())
            if key not in aliases:
                counters[s["pii_type"]] = counters.get(s["pii_type"], 0) + 1
                aliases[key] = f"[{s['pii_type']}_{counters[s['pii_type']]}]"
            out.append(text[cursor : s["start"]])
            out.append(aliases[key])
            cursor = s["end"]
        out.append(text[cursor:])

        counts: dict[str, int] = {}
        for s in spans:
            counts[s["pii_type"]] = counts.get(s["pii_type"], 0) + 1

        log.info("pii.redacted", span_count=len(spans), types=sorted(counts))
        return {
            "redacted_text": "".join(out),
            # Offsets refer to the ORIGINAL text; the masked output has different lengths.
            "spans": [{"pii_type": s["pii_type"], "start": s["start"], "end": s["end"]} for s in spans],
            "counts": counts,
            "pii_found": True,
        }
