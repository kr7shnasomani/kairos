"""
NER service — Layer 3: Named Entity Recognition.
Primary: NVIDIA NIM mistral-14b via JSON prompt.
Fallback: Ollama llama3.1:8b (local).
"""

import asyncio
import json
import os
import re
from collections import Counter
from typing import Any

import httpx
import structlog

from api.services.http import shared_client

log = structlog.get_logger(__name__)

_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# NIM queues concurrent calls per key. A 21-document reload fired ~18 extractions at once; the
# last 4 waited past the 60 s cap and fell to the regex path, which only finds ASSET_TAG
# (2026-09-13). Waiting for a slot costs latency; the timeout only starts once a call is sent.
# ponytail: fixed cap per event loop — raise it if NVIDIA lifts the per-key concurrency.
_NIM_NER_CONCURRENCY = 4
# Transient NIM failures (timeout / 5xx) get 3 attempts, backing off 2 s then 4 s.
_NIM_NER_ATTEMPTS = 3
_NIM_NER_BACKOFF_S = 2.0
# Characters of a document sent to NER, and the chunk size they are split into (see _extract_via_nim).
_NER_TEXT_BUDGET = 2000
_NER_CHUNK_CHARS = 700


def _chunk_text(text: str, size: int) -> list[str]:
    """Split at the last newline or space before `size`, so an entity is never cut in half."""
    chunks: list[str] = []
    rest = text
    while len(rest) > size:
        cut = max(rest.rfind("\n", 0, size), rest.rfind(" ", 0, size))
        if cut <= size // 2:
            cut = size  # no usable boundary — a hard cut beats an unbounded chunk
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip()
    if rest.strip() or not chunks:
        chunks.append(rest)
    return chunks


def _merge_chunk_results(results: list[dict[str, Any]], failed_chunks: int) -> dict[str, Any]:
    """Concatenate per-chunk NER results. Repeated mentions stay separate, as in a single-call result,
    so `_with_spans` still places each on its own occurrence. A failed chunk makes recall a floor."""
    entities = [entity for result in results for entity in result["entities"]]
    low_confidence = [entity for entity in entities if entity["requires_review"]]
    return {
        "entities": entities,
        "low_confidence_spans": low_confidence,
        "requires_annotation": bool(low_confidence),
        "total_entities": len(entities),
        "model": results[0]["model"],
        "parse_recovered": failed_chunks > 0 or any(r.get("parse_recovered") for r in results),
    }
_nim_slots: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Semaphore]] = {}


def _nim_slot() -> asyncio.Semaphore:
    """Concurrency gate for NIM NER calls, one per event loop (a semaphore binds to its loop)."""
    loop = asyncio.get_running_loop()
    entry = _nim_slots.get(id(loop))
    if entry is None or entry[0] is not loop:
        entry = (loop, asyncio.Semaphore(_NIM_NER_CONCURRENCY))
        _nim_slots[id(loop)] = entry
    return entry[1]

_ASSET_TAG_RE = re.compile(r'\b([A-Z]{1,4}-\d{2,4}[A-Z]?)\b')

# Tag-shaped strings that name no equipment. The model labels them ASSET_TAG because they share the
# PREFIX-NUMBER shape: dates ("JAN-2025"), year-stamped references ("SB-2025"), record and document
# numbers ("WO-2026-0714", "SOP-HE-301-04"), and family references ("HE-3xx").
_MONTH_YEAR_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEPT?|OCT|NOV|DEC)-\d{2,4}$")
# A four-digit year as its own segment, anywhere: "SB-2025", "MHT-ENG-2026-03". Real tags never carry one.
_YEAR_STAMPED_RE = re.compile(r"-(19|20)\d{2}(-|$)")
_DOCUMENT_REF_RE = re.compile(
    r"^(WO|PTW|SOP|INSP|MOC|NCR|CAPA|SB|PB|MP|GEN|QI|FP-SB|MHT-PB|ISO|OISD|PESO|API|ASME|IEC)-"
)
_SERIES_RE = re.compile(r"\d+X{1,3}\b")

# The label space this extractor can actually produce. Must stay in lockstep with the taxonomy
# listed in `_NER_PROMPT` below — `test_ner_taxonomy_matches_the_prompt` fails if they drift.
#
# Exported because the model gate needs it: ground-truth labels outside this set are unscoreable
# by construction, and scoring them anyway is not a measurement of the model. The corpus carried
# 12 `COMPONENT` labels — a type the prompt never requests — which read as 23% of the corpus
# failing, and each one *also* booked a false positive against whatever type the model did assign
# to the same span. One taxonomy mismatch, counted twice against the score.
NER_ENTITY_TYPES = frozenset({
    "ASSET_TAG",
    "PROCESS_PARAMETER",
    "FAILURE_MODE",
    "REGULATION",
    "ACTION_VERB",
    "MATERIAL",
    "PERSON",
    "LOCATION",
    "DATE",
    "ORGANIZATION",
})

_NER_PROMPT = """Extract named entities from the industrial text below. Return ONLY a valid JSON array, no other text.

Entity types:
- ASSET_TAG: Equipment tag numbers (P-101, V-247, FV-1234A, HX-301)
- PROCESS_PARAMETER: Measurements with values/units (pressure, temperature, flow rate)
- FAILURE_MODE: Failure descriptions (bearing wear, seal failure, corrosion)
- REGULATION: Standards and regulatory references (OISD-117, ISO 45001, CEA Reg 4.2)
- ACTION_VERB: Maintenance actions (replaced, inspected, calibrated)
- MATERIAL: Material grades or part numbers
- PERSON: Personnel names or roles
- LOCATION: Plant areas, sections, units
- DATE: Dates and time references
- ORGANIZATION: Vendors, contractors, regulatory bodies

Output format:
[{{"text": "P-101", "entity_type": "ASSET_TAG", "confidence": 0.95}}, ...]

Text: {text}"""



class FallbackCountingNER:
    """Delegates to a real `NERService` and tallies which path produced each extraction.

    Both model-gate entry points need this: a gate that cannot tell "the model scored 0.73"
    from "the model was unreachable and regex scored 0.73" reports the fallback's output as
    the model's. Observed 2026-08-22 — 52 of 55 extractions returned 429/500 and the run was
    still written to history as `passed: true`.

    Wraps cleanly because `evaluate()` types its `ner` argument as `Any` and calls only
    `extract_entities`; the result dict already self-reports its path as `model`
    ("nim" / "ollama" / "regex"), so this only counts what is already there.
    """

    def __init__(self, inner: "NERService") -> None:
        self._inner = inner
        self.paths: Counter = Counter()

    async def extract_entities(self, text, *args, **kwargs):
        result = await self._inner.extract_entities(text, *args, **kwargs)
        self.paths[(result or {}).get("model") or "none"] += 1
        return result

    @property
    def fallback_count(self) -> int:
        """Extractions that did NOT come from the model under test."""
        return sum(n for path, n in self.paths.items() if path not in ("nim", "ollama"))

    @property
    def validity(self) -> str:
        """A fallback contributes regex output (ASSET_TAG only) to a model-attributed score,
        so any fallback makes the run's F1 a CEILING rather than a measurement."""
        return "SUSPECT" if self.fallback_count else "VALID"

class NERService:
    def __init__(self, model: str | None = None):
        """
        `model` overrides NVIDIA_NIM_NER_MODEL for this instance.

        The Layer-0 model gate exists to score a *candidate* model, so it must be able to
        pick one. Without this parameter the gate always called whatever the env var held
        and merely labelled the result with the requested name — producing an
        authoritative-looking F1 attributed to a model that was never invoked (and, when
        the configured model is unreachable, scoring the regex fallback instead).
        """
        self._nim_key = os.getenv("NVIDIA_NIM_API_KEY", "")
        self._nim_model = model or os.getenv("NVIDIA_NIM_NER_MODEL", "meta/llama-3.2-11b-vision-instruct")
        self._ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_ner_model = os.getenv("OLLAMA_NER_MODEL", "llama3.1:8b")
        # Its own cap (config.py NVIDIA_NIM_NER_TIMEOUT), not the synthesis one. A short cap drops a
        # document to `_regex_fallback`, which only matches ASSET_TAG: 30 s lost 2 of 5 extractions
        # (2026-08-15), and the shared 60 s lost a 2,000-character document three attempts running on
        # 2026-09-13. Every caller is async (document_pipeline, voice_transcription, model_validation)
        # and the one request-path caller, GET /documents/{id}/redacted, has no frontend consumer, so
        # no UI budget applies — unlike NVIDIA_NIM_TIMEOUT, which must stay under synthesis's 90 s.
        self._timeout = float(os.getenv("NVIDIA_NIM_NER_TIMEOUT", "120"))

    async def extract_entities(
        self,
        text: str,
        language_hint: str | None = None,
        confidence_threshold: float = 0.5,
    ) -> dict[str, Any]:
        if self._nim_key:
            result = await self._extract_via_nim(text)
            if result is not None:
                return self._with_spans(result, text)

        # An empty OLLAMA_BASE_URL (how compose ships it) means "no local model": calling it built the
        # relative URL "/api/chat" and logged a spurious failure on every NIM miss.
        if self._ollama_url:
            result = await self._extract_via_ollama(text)
            if result is not None:
                return self._with_spans(result, text)

        return self._regex_fallback(text)

    async def _extract_via_nim(self, text: str) -> dict[str, Any] | None:
        """NER over the first `_NER_TEXT_BUDGET` characters, in chunks merged into one result.

        The hosted NER model generates slowly, and a dense document needs a long entity list: on
        2026-09-13 a 2,000-character work-order CSV timed out at 120 s on three attempts running, while
        its two halves answered in ~40 s each and found more entities between them. Chunks run
        concurrently, capped by `_nim_slot`. Only when every chunk fails does the caller fall back to regex.
        """
        chunks = _chunk_text(text[:_NER_TEXT_BUDGET], _NER_CHUNK_CHARS)
        results = await asyncio.gather(*(self._extract_chunk_via_nim(chunk) for chunk in chunks))
        succeeded = [result for result in results if result is not None]
        if not succeeded:
            return None
        if len(chunks) > 1:
            log.info("ner.chunked", chunks=len(chunks), failed=len(chunks) - len(succeeded))
        return _merge_chunk_results(succeeded, failed_chunks=len(chunks) - len(succeeded))

    async def _extract_chunk_via_nim(self, text: str) -> dict[str, Any] | None:
        # Retry transient failures: a timeout, or a 5xx from the hosted endpoint. A miss drops the
        # document to regex (ASSET_TAG only — no people, organisations or relationships). Timeouts cost
        # 2 of 21 documents on one reload; on 2026-09-13 a burst of 500s cost 17 of 18. A 4xx is a
        # request problem, not load, and fails straight to the fallback.
        for attempt in range(1, _NIM_NER_ATTEMPTS + 1):
            try:
                return await self._nim_request(text)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                transient = isinstance(exc, httpx.TimeoutException) or exc.response.status_code >= 500
                log.warning("ner.nim_failed", error=str(exc), exc_type=type(exc).__name__, attempt=attempt)
                if not transient:
                    return None
                if attempt < _NIM_NER_ATTEMPTS:
                    await asyncio.sleep(_NIM_NER_BACKOFF_S * attempt)
            except Exception as exc:
                # exc_type matters: httpx timeout exceptions stringify to "", so this logged a bare
                # `ner.nim_failed error=` and the 30 s cap above went undiagnosed for weeks.
                log.warning("ner.nim_failed", error=str(exc), exc_type=type(exc).__name__)
                return None
        return None

    async def _nim_request(self, text: str) -> dict[str, Any] | None:
        client = shared_client(self._timeout)
        async with _nim_slot():
            resp = await client.post(
                _NIM_URL,
                headers={"Authorization": f"Bearer {self._nim_key}"},
                json={
                    "model": self._nim_model,
                    "messages": [{"role": "user", "content": _NER_PROMPT.format(text=text[:2000])}],
                    "max_tokens": 1024,
                    "temperature": 0.0,
                },
                timeout=self._timeout,
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        return self._parse_response(content, source="nim")

    async def _extract_via_ollama(self, text: str) -> dict[str, Any] | None:
        try:
            client = shared_client(self._timeout)
            resp = await client.post(
                f"{self._ollama_url}/api/chat",
                json={
                    "model": self._ollama_ner_model,
                    "messages": [{"role": "user", "content": _NER_PROMPT.format(text=text[:2000])}],
                    "stream": False,
                    "options": {"temperature": 0.0},
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"].strip()
            return self._parse_response(content, source="ollama")
        except Exception as exc:
            log.warning("ner.ollama_failed", error=str(exc), exc_type=type(exc).__name__)
            return None

    @staticmethod
    def _salvage_objects(content: str) -> list[dict[str, Any]]:
        """
        Recover the complete `{...}` objects from a truncated or trailing-garbage JSON array.

        `max_tokens` is 1024, so an entity-dense document runs out of budget mid-array and the
        response ends part-way through an object. `json.loads` then rejects the **entire**
        response, and a document the model had almost finished extracting fell through to the
        regex last resort — which matches `ASSET_TAG` only, so PERSON/ORGANIZATION silently
        vanish from that document. Observed 2026-08-16: 1 of 15 corpus documents failed exactly
        this way (`Expecting value: line 38 column 77 (char 2893)`), and it is what kept the
        Layer-0 F1 flagged `SUSPECT` after the timeout cause was fixed.

        Salvaging beats raising `max_tokens`: a bigger budget only moves the cliff, while this
        degrades proportionally at any limit. The partial result is flagged, never passed off as
        a complete extraction.

        ponytail: a depth counter, not a JSON parser. It only has to find object boundaries in a
        flat array of flat objects, which is the shape the prompt pins.
        """
        objects: list[dict[str, Any]] = []
        depth = 0
        start = -1
        in_string = False
        escaped = False
        for i, ch in enumerate(content):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        obj = json.loads(content[start : i + 1])
                    except json.JSONDecodeError:
                        pass
                    else:
                        if isinstance(obj, dict):
                            objects.append(obj)
                    start = -1
                elif depth < 0:      # stray closer — resynchronise
                    depth = 0
                    start = -1
        return objects

    def _parse_response(self, content: str, source: str) -> dict[str, Any] | None:
        recovered = False
        try:
            # Strip markdown code fences if present
            content = re.sub(r"```(?:json)?|```", "", content).strip()
            raw = json.loads(content)
            if not isinstance(raw, list):
                return None
        except (json.JSONDecodeError, ValueError) as exc:
            raw = self._salvage_objects(content)
            if not raw:
                log.warning("ner.parse_failed", source=source, error=str(exc))
                return None
            recovered = True
            log.warning(
                "ner.parse_recovered",
                source=source,
                error=str(exc),
                salvaged_objects=len(raw),
            )

        try:
            entities = []
            low_confidence = []
            for item in raw:
                if not isinstance(item, dict) or "text" not in item or "entity_type" not in item:
                    continue
                confidence = float(item.get("confidence", 0.85))
                entity = {
                    "text": item["text"],
                    "entity_type": item["entity_type"],
                    "confidence": round(confidence, 4),
                    "start": None,
                    "end": None,
                    "requires_review": confidence < 0.7,
                }
                entities.append(entity)
                if confidence < 0.7:
                    low_confidence.append(entity)

            log.info("ner.complete", source=source, entity_count=len(entities), recovered=recovered)
            return {
                "entities": entities,
                "low_confidence_spans": low_confidence,
                "requires_annotation": len(low_confidence) > 0,
                "total_entities": len(entities),
                "model": source,
                # True when the response was truncated and only the complete objects were kept,
                # so recall for this document is a floor. `model` still names the real source —
                # the model did produce these entities — but a consumer reporting extraction
                # quality must not treat a recovered document as a clean one.
                "parse_recovered": recovered,
            }
        except ValueError as exc:
            log.warning("ner.parse_failed", source=source, error=str(exc))
            return None

    @staticmethod
    def _with_spans(result: dict[str, Any], text: str) -> dict[str, Any]:
        """
        Recovers character offsets for LLM-extracted entities.

        The model returns entity *text* with no positions, so start/end came back as None —
        which left the annotation UI unable to highlight an entity in its source document
        and made the `low_confidence_spans` field a misnomer. Offsets are recovered by
        locating each entity in the original text.

        Note this does not affect the Layer-0 F1 metric: workers/model_validation.py matches
        on surface-form overlap (`_span_match`), never on offsets.

        A per-value cursor means a repeated entity gets successive positions rather than
        every mention collapsing onto the first.
        """
        cursors: dict[str, int] = {}
        lowered = text.lower()

        for entity in result.get("entities", []):
            value = entity.get("text") or ""
            if not value:
                continue
            key = value.lower()
            begin = cursors.get(key, 0)

            index = text.find(value, begin)
            if index == -1:
                # The model often normalises case ("eq-101" -> "EQ-101").
                index = lowered.find(key, begin)
            if index == -1:
                continue  # paraphrased or inferred — leave unlocated rather than guess

            entity["start"] = index
            entity["end"] = index + len(value)
            cursors[key] = index + len(value)

        return result

    def _regex_fallback(self, text: str) -> dict[str, Any]:
        entities = []
        for match in _ASSET_TAG_RE.finditer(text.upper()):
            entities.append({
                "text": match.group(1),
                "entity_type": "ASSET_TAG",
                "confidence": 0.9,
                "start": match.start(),
                "end": match.end(),
                "requires_review": False,
            })
        log.info("ner.regex_fallback", entity_count=len(entities))
        return {
            "entities": entities,
            "low_confidence_spans": [],
            "requires_annotation": False,
            "total_entities": len(entities),
            "model": "regex",
        }

    def resolve_asset_tag(self, raw_tag: str, alias_map: dict[str, str]) -> str | None:
        normalized = raw_tag.strip().upper().replace(" ", "")
        hit = alias_map.get(normalized) or alias_map.get(raw_tag.strip())
        if hit:
            return hit
        # "HE-301 Shell and Tube Heat Exchanger": the model labels the tag together with its
        # description. The whole span never resolves; the leading tag does.
        lead = _ASSET_TAG_RE.match(raw_tag.strip().upper())
        if lead and lead.group(1) != normalized:
            return alias_map.get(lead.group(1))
        return None

    @staticmethod
    def is_reference_identifier(raw_tag: str) -> bool:
        """True for tag-shaped strings that are dates, document/record numbers or family references.

        Only consulted for tags that did not resolve: a real asset always wins through the alias map
        first. These used to become alias candidates and quarantine items — 29 of 32 review items on
        the 2026-09-13 reload were "Unresolved asset tag: 'JAN-2025'" and the like.
        """
        tag = raw_tag.strip().upper()
        # No digit, no equipment: every asset tag carries a number (EQ-101, P-101, HX-14B). When the
        # LLM extractor answers instead of the regex fallback, it labels phrases and codes ASSET_TAG
        # too — "heat exchangers", "tubesheet", "MECH-SEAL-FAIL" filled 13 of 17 review items on the
        # 2026-09-13 reload.
        if not any(ch.isdigit() for ch in tag):
            return True
        return bool(
            _MONTH_YEAR_RE.match(tag)
            or _YEAR_STAMPED_RE.search(tag)
            or _DOCUMENT_REF_RE.match(tag)
            or _SERIES_RE.search(tag)
        )
