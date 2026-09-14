"""
LLM service — synthesis (Layer 11). Provider cascade: NVIDIA NIM → OpenRouter → Gemini → Ollama.
Implements the synthesis layer with mandatory source citation enforcement
and explicit refusal for safety-critical parameter queries.
"""

import asyncio
import json
import re
from collections import OrderedDict
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from api.config import Settings
from api.services.http import shared_client
from api.services.supply_chain import verify_served_model

# Transient NIM gateway errors worth one retry before the cascade hands the answer to another model.
_NIM_RETRYABLE_STATUS = frozenset({502, 503, 504})
_NIM_RETRY_DELAY_S = 1.5

log = structlog.get_logger(__name__)


class _LRU:
    """
    Bounded in-process LRU for query embeddings.

    Every search embeds its query text before touching Qdrant, so a repeated or polled
    query paid a Jina round-trip each time — the copilot, the benchmark and the graph page
    all re-issue identical queries. Embeddings are deterministic per (task, text) for a
    fixed model, so caching is safe.

    ponytail: process-local and lost on restart, which is fine for a read cache. Move to
    Redis if hit rate across replicas starts mattering — the interface is the same.
    """

    def __init__(self, maxsize: int = 512) -> None:
        self._data: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self._maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple[str, str]) -> list[float] | None:
        if key in self._data:
            self._data.move_to_end(key)
            self.hits += 1
            return self._data[key]
        self.misses += 1
        return None

    def put(self, key: tuple[str, str], value: list[float]) -> None:
        if not value:
            return  # never cache a failed embedding
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


_EMBED_CACHE = _LRU()

# Safety-critical query categories that trigger explicit refusal behavior
SAFETY_CRITICAL_CATEGORIES = {
    "max_allowable_pressure",
    "isolation_interlock_sequence",
    "torque_specification",
    "electrical_rating",
    "pressure_relief_setting",
    "safety_shutdown_setpoint",
}

# Query → safety-critical category patterns, most specific first. Order matters:
# "pressure relief setting" must not be swallowed by the generic pressure rule.
# ponytail: keyword classifier, deterministic and testable. Swap for an LLM
# classifier only if real queries start missing — every miss here silently
# disables the safety gate, so a miss must be cheap to reproduce in a test.
# "max/maximum <up to 3 words> pressure" — survives an inserted adjective ("allowable operating").
# Bounded to 3 words so it cannot span a sentence boundary and over-refuse unrelated queries.
_MAWP_RE = re.compile(r"max(?:imum)?\s+(?:\w+\s+){0,3}pressure")

# "rated for/to/at <up to 3 words> pressure" — comparative rating questions.
_PRESSURE_RATED_RE = re.compile(r"rated\s+(?:for|to|at)\s+(?:\w+\s+){0,3}pressure")

# Asset tags as they appear in a question ("HE-302", "XV-203", "FSL-2240A"). Same shape as the
# NER regex; kept local so the safety gate does not depend on the extraction service.
_ASSET_TAG_IN_QUERY_RE = re.compile(r"\b([A-Z]{1,4}-\d{2,4}[A-Z]?)\b")

# Family/series references — "HE-3xx series", "P-10x". These name no single asset, so no document
# can be same-asset evidence for them, and the anchor below correctly yields zero vouchers.
#
# Why that matters (S13): "hydrotest pressure for the HE-3xx series" matched no specific tag, so
# the anchor never engaged, the gate fell back to the top-relevance document — an OEM bulletin for
# HE-301 — and the model answered "17.82 bar, as calculated", deriving 110% x 16.2 for a series no
# source states it for. Asking about a family and answering from one member is precisely the
# extrapolation the gate exists to prevent.
_ASSET_SERIES_IN_QUERY_RE = re.compile(r"\b([A-Z]{1,4}-\d{1,3}X{1,3})\b")

_CATEGORY_PATTERNS: list[tuple[str, tuple[Any, ...]]] = [
    ("pressure_relief_setting", (
        "relief valve", "relief setting", "relief set", "psv", " prv", "rupture disc",
        "safety valve", "set pressure", "popping pressure",
    )),
    ("safety_shutdown_setpoint", (
        "shutdown setpoint", "shutdown set point", "trip setpoint", "trip set point",
        "trip point", "emergency shutdown", "esd setpoint", "sis setpoint", "safety setpoint",
    )),
    # NOTE: bare "isolation" is deliberately absent. It matches the *equipment name* in
    # questions like "when was isolation valve XV-203 last inspected?", which is a date
    # lookup, not a safety-parameter query — refusing it is a false positive that hides a
    # fact the vault holds. Patterns must express isolation *intent*, not just the word.
    ("isolation_interlock_sequence", (
        "isolation boundary", "isolation point", "isolation sequence", "isolation procedure",
        "isolation requirement", "safety isolation", "isolate", "interlock", "lockout",
        "lock out", "tag-out", "tagout", "tag out", "double block", "blind list",
        "permit to work sequence",
    )),
    ("torque_specification", ("torque", "tightening spec", "bolt load", "preload")),
    ("electrical_rating", (
        "electrical rating", "voltage rating", "insulation class", "insulation rating",
        "amperage", "current rating", "kv rating", "motor rating", "hazardous area classification",
    )),
    ("max_allowable_pressure", (
        "max allowable pressure", "maximum allowable pressure", "mawp", "max working pressure",
        "maximum working pressure", "max operating pressure", "maximum operating pressure",
        "design pressure", "pressure limit", "pressure rating", "max pressure", "maximum pressure",
        # Substring matching missed "maximum allowable OPERATING pressure" — the most natural
        # industry phrasing of a MAWP query — because an inserted adjective breaks every literal
        # above. A missed classification does not produce a wrong answer; it produces NO GATE,
        # silently. Found by benchmark/safety_questions.json S01.
        _MAWP_RE,
        # Hydrotest/proof pressure is a safety-critical parameter in its own right, and it was
        # ungated: S13 answered "17.82 bar, as calculated" — the system DERIVED a pressure
        # (110% x 16.2) for a series no source states it for. Computing a safety value is worse
        # than quoting one, because there is no passage a technician can go and verify.
        "hydrotest", "hydro test", "hydrostatic test", "test pressure", "proof pressure",
        # "is XV-204 rated for the same pressure as XV-203?" (S14) was ungated and answered
        # honestly only by luck — nothing in the corpus rates either device. A comparative
        # rating question is a pressure question.
        _PRESSURE_RATED_RE,
    )),
]

# Authority levels 1–3 are regulatory / engineering / OEM sources. A safety-critical
# parameter answered only from level 4–5 (site procedure, field observation) is exactly
# the case the refusal gate exists for.
AUTHORITATIVE_LEVEL = 3

# How many of the most-relevant context items may vouch for a safety-critical answer.
_AUTHORITY_TOP_K = 3


def query_asset_tags(query: str) -> set[str]:
    """
    Asset tags named in the question itself (e.g. "HE-302" in "MAWP for HE-302?").

    Derived server-side for the same reason `classify_query_category` is: no caller was ever
    setting it, so anchoring on it has to be automatic or it does not happen at all.
    """
    upper = query.upper()
    return (
        {m.group(1) for m in _ASSET_TAG_IN_QUERY_RE.finditer(upper)}
        | {m.group(1) for m in _ASSET_SERIES_IN_QUERY_RE.finditer(upper)}
    )


def _authority_candidates(
    context: list[dict[str, Any]],
    query_assets: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    The context items permitted to clear the safety gate.

    The gate used to take `min(authority_level)` over the **whole** retrieved context, making it a
    property of the context *set* rather than of the evidence supporting the answer: one unrelated
    authoritative document anywhere in the context cleared it, and in the live copilot that was the
    normal case, so the gate almost never fired.

    Two filters, both derived from measured behaviour on the real corpus
    (query: "Which valves make up the isolation boundary for V-247?"):

      1. **Most relevant only.** Ranked by `relevance_score` (the RRF fusion score), NOT by
         position — `SearchService` sorts by `(authority_level, -rrf)`, so the most authoritative
         document is always first and a top-K-by-position filter would be a no-op. This drops the
         generic L1 "Applicable Standards and Statutory Provisions" list, which measured as the
         *least* relevant hit (rrf 0.0156) yet was clearing every safety refusal.

      2. **Same asset as the best evidence.** Relevance alone was not enough: two Fischer OEM
         bulletins (L3, rrf ~0.031) about `EQ-101` centrifugal-pump seals still ranked inside the
         top 3 for a question about a `V-247` valve, and an OEM bulletin for different equipment
         cannot vouch for this one. The target asset is taken from the highest-relevance item.

    Deliberately conservative in both directions: a document with no `asset_id` never vouches when
    a target asset is known, and when nothing carries a `relevance_score` the whole context is
    returned — i.e. previous behaviour — because callers that assemble context by hand (graph
    facts, elicitation) never knew to send these fields, and silently re-scoping their refusals
    would change safety behaviour based on a field they do not set.
    """
    scored = [r for r in context if r.get("relevance_score") is not None]
    if not scored:
        return list(context)

    ranked = sorted(scored, key=lambda r: r.get("relevance_score") or 0.0, reverse=True)
    top = ranked[:_AUTHORITY_TOP_K]

    # Anchor on the asset the QUESTION names, when it names one.
    #
    # This filter previously anchored on `ranked[0]`'s asset — the top-retrieved document — which
    # compares evidence to evidence rather than evidence to the question. Measured failure
    # (safety_questions.json S01): "maximum allowable operating pressure for HE-302" retrieved the
    # L3 OEM bulletin for **HE-301**, that bulletin became its own anchor, the gate cleared on
    # authority 3, and the answer stated HE-301's 16.2 bar as HE-302's limit — extrapolating a
    # pressure limit onto an asset no source covers.
    #
    # When the question names an asset and nothing retrieved covers it, the correct result is an
    # EMPTY candidate list: no document may vouch, so the gate refuses. That is why the
    # `or [ranked[0]]` fallback below is not applied on this branch — that fallback is what let
    # S01 through.
    if query_assets:
        # Scan the WHOLE ranked context, not just the top-K window. The top-K existed to stop an
        # unrelated document vouching; when the question names an asset, the asset match is a
        # strictly better precision mechanism, and stacking both was over-restrictive — an
        # authority-3 bulletin for the very asset asked about could sit at rank 4 and be ignored,
        # refusing a question the vault genuinely answers (measured: S10, HE-301 MAWP).
        return [r for r in ranked if (r.get("asset_id") or "").upper() in query_assets]

    target_asset = ranked[0].get("asset_id")
    if not target_asset:
        return top
    return [r for r in top if r.get("asset_id") == target_asset] or [ranked[0]]


class LLMService:
    """
    Synthesis layer — assembles retrieved knowledge into provenance-backed answers.
    NEVER originates knowledge. Only assembles what exists in the vault/graph/quarantine.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._nim_client: httpx.AsyncClient | None = None
        self._ollama_client: httpx.AsyncClient | None = None

    @staticmethod
    def classify_query_category(query: str) -> str | None:
        """
        Maps a free-text query onto a safety-critical category key, or None.

        Callers may pass an explicit query_category; when they don't, the synthesis
        endpoint derives it here. Without this the safety-critical refusal gate is
        unreachable — no caller in the system was ever setting the category.
        """
        q = f" {query.lower()} "
        for category, patterns in _CATEGORY_PATTERNS:
            # Patterns are substrings, except where a compiled regex is needed to survive an
            # adjective being inserted mid-phrase (see _MAWP_RE).
            if any(p.search(q) if hasattr(p, "search") else p in q for p in patterns):
                return category
        return None

    @property
    def nim_available(self) -> bool:
        return bool(self.settings.NVIDIA_NIM_API_KEY)

    @property
    def ollama_available(self) -> bool:
        return bool(self.settings.OLLAMA_BASE_URL)

    @property
    def gemini_available(self) -> bool:
        return bool(self.settings.GEMINI_API_KEY)

    @property
    def openrouter_available(self) -> bool:
        return bool(self.settings.OPENROUTER_API_KEY)

    async def synthesize(
        self,
        query: str,
        retrieved_context: list[dict[str, Any]],
        query_category: str | None = None,
        confidence_threshold: float = 0.7,
    ) -> dict[str, Any]:
        """
        Synthesizes an answer from retrieved context with mandatory source citations.

        For safety-critical parameter categories, applies explicit refusal when
        evidence confidence is below threshold — returns source documents directly
        rather than a hedged partial answer.
        """
        refusal = self.evidence_gate(query, retrieved_context, query_category, confidence_threshold)
        if refusal is not None:
            return refusal

        if not retrieved_context:
            return {
                "answer": None,
                "sources": [],
                "confidence": 0.0,
                "uncertainty": "No relevant evidence found in the knowledge base.",
            }

        # Build synthesis prompt
        context_block = self._format_context(retrieved_context)
        prompt = self._build_synthesis_prompt(query, context_block)

        # Provider cascade: NIM → OpenRouter → Gemini → Ollama
        result = await self._synthesize_cascade(prompt, retrieved_context)

        # ---------------------------------------------------------------------
        # Post-synthesis safety gate.
        #
        # The pre-gate above inspects the *evidence* and clears on `authority <= 3`. That is
        # correct as far as it goes, but it cannot know whether the model actually found the
        # parameter. Observed live: a torque-spec query for a non-existent asset retrieved an
        # unrelated L3 OEM bulletin, cleared the pre-gate on authority, and the model then
        # honestly answered "not specified in the provided source documents" — which the UI
        # rendered as a *hedged low-confidence answer*.
        #
        # For a safety-critical parameter that is precisely the outcome the architecture forbids:
        # "a hedged partial answer in a safety-critical context is more dangerous than no answer,
        # because a technician under time pressure will treat ambiguity as confirmation."
        #
        # So the gate is applied twice: once to the evidence, once to the result.
        # ---------------------------------------------------------------------
        post_refusal = self.result_gate(result, retrieved_context, query_category, confidence_threshold)
        if post_refusal is not None:
            return post_refusal

        return result

    async def synthesize_stream(
        self,
        query: str,
        retrieved_context: list[dict[str, Any]],
        query_category: str | None = None,
        confidence_threshold: float = 0.7,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yields `(event, payload)` for the SSE endpoint. Terminal event is always `done`.

        p95 synthesis is ~65 s against NVIDIA's shared endpoint and that tail cannot be tuned
        away, so progressive render is the only remaining lever on *perceived* latency.

        **Safety-critical categories deliberately do not stream answer text.** `CONFIDENCE:`
        arrives after `ANSWER:` in the response contract, and `result_gate` can retract the whole
        answer based on it — so streaming the text would show an operator words that are about to
        be replaced by a refusal. They stream progress instead: the user learns work is happening
        without being shown an ungated claim. Everything else streams `ANSWER:` as it arrives.

        Both gates are the same methods `synthesize()` calls. Nothing about the refusal rules is
        re-implemented here; only *when the text reaches the screen* differs.
        """
        yield "status", {"stage": "gating", "query_category": query_category}

        refusal = self.evidence_gate(query, retrieved_context, query_category, confidence_threshold)
        if refusal is not None:
            # Refused on the evidence — no provider call is made at all.
            yield "done", refusal
            return

        if not retrieved_context:
            yield "done", {
                "answer": None,
                "sources": [],
                "confidence": 0.0,
                "uncertainty": "No relevant evidence found in the knowledge base.",
            }
            return

        prompt = self._build_synthesis_prompt(query, self._format_context(retrieved_context))
        safety_critical = query_category in SAFETY_CRITICAL_CATEGORIES

        yield "status", {
            "stage": "synthesizing",
            "streaming_text": not safety_critical,
            # Told to the client rather than inferred, so the UI can say *why* it is showing a
            # spinner instead of text on exactly the queries where that matters most.
            "reason": (
                "Safety-critical category — the answer is withheld until the post-synthesis "
                "gate has cleared it."
            ) if safety_critical else None,
        }

        if safety_critical:
            # Non-streamed on purpose. Reuses the full cascade so a safety answer keeps every
            # provider fallback the non-streaming endpoint has.
            result = await self._synthesize_cascade(prompt, retrieved_context)
            post = self.result_gate(result, retrieved_context, query_category, confidence_threshold)
            yield "done", post if post is not None else result
            return

        # Stream tier 1 only. A mid-stream provider failure falls back to the ordinary cascade
        # and is delivered as a single `done` — reimplementing streaming for all four providers
        # would fork the cascade's "which model answered" guarantee for no user-visible gain.
        streamed = ""
        stream_failed = False
        if self.nim_available:
            try:
                async for delta in self._stream_nim(prompt):
                    streamed += delta
                    yield "delta", {"text": delta}
            except Exception as exc:  # noqa: BLE001 — fall back, never fail the request
                log.warning("synthesis.stream_failed", error=str(exc), exc_type=type(exc).__name__)
                stream_failed = True
        else:
            stream_failed = True

        if stream_failed or not streamed.strip():
            result = await self._synthesize_cascade(prompt, retrieved_context)
            # `restart` tells the client to discard any deltas already painted: the fallback answer
            # came from a different call and concatenating the two would fabricate a hybrid answer.
            yield "restart", {"reason": "stream unavailable — answer re-synthesized via the provider cascade"}
            post = self.result_gate(result, retrieved_context, query_category, confidence_threshold)
            yield "done", post if post is not None else result
            return

        result = {
            "answer": streamed,
            "sources": retrieved_context,
            # Provider key, like every cascade tier returns ("nim", "openrouter", …) — the UI renders it
            # as the "answered by" badge, and the raw model id here printed a 34-character string there.
            "model": "nim",
            "served_model": self.settings.NVIDIA_NIM_MODEL,
        }
        # Runs even for non-safety categories: `result_gate` no-ops unless the category is
        # safety-critical, and calling it unconditionally means a category added to
        # SAFETY_CRITICAL_CATEGORIES later is covered here without a second edit.
        post = self.result_gate(result, retrieved_context, query_category, confidence_threshold)
        yield "done", post if post is not None else result

    async def _stream_nim(self, prompt: str) -> AsyncIterator[str]:
        """Yields text deltas from NIM's OpenAI-compatible SSE stream."""
        client = shared_client(self.settings.NVIDIA_NIM_TIMEOUT)
        async with client.stream(
            "POST",
            f"{self.settings.NVIDIA_NIM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.NVIDIA_NIM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={**self._nim_payload(prompt), "stream": True},
            timeout=self.settings.NVIDIA_NIM_TIMEOUT,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue  # keep-alive or partial frame — not fatal
                for choice in chunk.get("choices") or []:
                    delta = (choice.get("delta") or {}).get("content")
                    if delta:
                        yield delta

    # =========================================================================
    # The two safety gates, extracted so the streaming path calls the SAME code.
    #
    # These were inline in `synthesize()`. The streaming endpoint has to run both, and a second
    # copy of a refusal rule is the one duplication this codebase cannot afford — the two would
    # drift and whichever the operator hit would be the wrong one. Pure and side-effect free
    # apart from logging, so both are directly testable without a provider.
    # =========================================================================

    def evidence_gate(
        self,
        query: str,
        retrieved_context: list[dict[str, Any]],
        query_category: str | None,
        confidence_threshold: float = 0.7,
    ) -> dict[str, Any] | None:
        """Pre-synthesis gate: judges the *evidence*. Returns a refusal, or None to proceed.

        Two independent ways to clear it: an explicit per-source confidence at/above threshold,
        OR at least one regulatory/engineering/OEM-authority source. Retrieval paths that carry
        `authority_level` but no confidence (hybrid search, graph facts) would otherwise read as
        confidence 0.0 and refuse every safety query.
        """
        if query_category not in SAFETY_CRITICAL_CATEGORIES:
            return None

        max_confidence = max((r.get("confidence") or 0.0 for r in retrieved_context), default=0.0)
        gate_context = _authority_candidates(retrieved_context, query_asset_tags(query))
        best_authority = min((r.get("authority_level") or 5 for r in gate_context), default=5)
        if max_confidence >= confidence_threshold or best_authority <= AUTHORITATIVE_LEVEL:
            return None

        log.info(
            "synthesis.safety_critical_refusal",
            query_category=query_category,
            max_confidence=max_confidence,
            best_authority=best_authority,
        )
        return {
            "answer": None,
            "refused": True,
            "refusal_reason": (
                f"Safety-critical parameter query for '{query_category}' — the retrieved evidence is "
                f"neither high-confidence (best {max_confidence:.2f}, threshold {confidence_threshold}) "
                f"nor from an authoritative source (best authority level {best_authority}; "
                f"level {AUTHORITATIVE_LEVEL} or better required). "
                "Verify directly against the source documents and consult the responsible engineering authority."
            ),
            "sources": retrieved_context,
            "confidence": max_confidence,
        }

    def result_gate(
        self,
        result: dict[str, Any],
        retrieved_context: list[dict[str, Any]],
        query_category: str | None,
        confidence_threshold: float = 0.7,
    ) -> dict[str, Any] | None:
        """Post-synthesis gate: judges the *result*. Returns a refusal, or None to keep it.

        The evidence gate clears on `authority <= 3`, which cannot know whether the model actually
        found the parameter. Observed live: a torque-spec query for a non-existent asset retrieved
        an unrelated L3 OEM bulletin, cleared the evidence gate on authority, and the model then
        honestly answered "not specified in the provided source documents" — which the UI rendered
        as a *hedged low-confidence answer*. For a safety-critical parameter that is exactly the
        outcome the architecture forbids: "a hedged partial answer in a safety-critical context is
        more dangerous than no answer, because a technician under time pressure will treat
        ambiguity as confirmation."

        **This is why a safety-critical answer cannot be streamed to the screen token by token.**
        `CONFIDENCE:` arrives *after* `ANSWER:` in the response contract, so the value that decides
        refusal is the second-to-last thing the model emits. Streaming the answer would show the
        operator text this gate is about to retract.
        """
        if query_category not in SAFETY_CRITICAL_CATEGORIES or not result.get("answer"):
            return None

        parsed = self.parse_synthesis_response(result["answer"])
        answer_confidence = parsed.get("confidence")
        cited = parsed.get("sources_used") or []
        # Only judge a response that actually followed the contract. A bare answer with no markers
        # carries no self-assessment, and treating that as "zero sources cited" would refuse every
        # well-formed answer that simply omitted the scaffolding — a false refusal is its own
        # safety failure, because it trains operators to route around the gate. Refuse on an
        # *explicit* low self-confidence only.
        if answer_confidence is None or answer_confidence >= confidence_threshold:
            return None

        log.info(
            "synthesis.safety_critical_refusal_post",
            query_category=query_category,
            answer_confidence=answer_confidence,
            sources_cited=len(cited),
        )
        return {
            "answer": None,
            "refused": True,
            "refusal_reason": (
                f"Safety-critical parameter query for '{query_category}' — synthesis could not "
                f"support an answer from the retrieved evidence "
                f"(self-reported confidence {answer_confidence if answer_confidence is not None else 'none'}, "
                f"{len(cited)} source(s) cited). "
                "Kairos does not hedge on safety-critical parameters. Verify directly against the "
                "source documents below and consult the responsible engineering authority."
            ),
            "sources": retrieved_context,
            "confidence": answer_confidence or 0.0,
            "model": result.get("model"),
        }

    def _format_context(self, context: list[dict[str, Any]]) -> str:
        """Formats retrieved chunks into a structured context block."""
        blocks = []
        for i, chunk in enumerate(context, 1):
            authority = chunk.get("authority_level", "unknown")
            doc_id = chunk.get("document_id", "unknown")
            text = chunk.get("text") or chunk.get("snippet", "")
            blocks.append(f"[Source {i} | Authority Level {authority} | Document: {doc_id}]\n{text}")
        return "\n\n---\n\n".join(blocks)

    def _build_synthesis_prompt(self, query: str, context: str) -> str:
        return f"""You are the Kairos synthesis engine for an industrial operational intelligence platform.

Your task is to answer the following query using ONLY the provided source documents.
- NEVER invent or infer information not present in the sources.
- ALWAYS cite the specific source(s) you are drawing from.
- If evidence is incomplete or conflicting, explicitly state what is known and what is not known.
- Do NOT present a confident answer when the evidence is insufficient.

QUERY: {query}

SOURCE DOCUMENTS:
{context}

Provide your answer with mandatory source citations. Format:
ANSWER: [your answer, citing source numbers]
CONFIDENCE: [0.0-1.0]
UNCERTAINTY: [anything you are not certain about]
SOURCES_USED: [comma-separated source numbers]"""

    def _nim_payload(self, prompt: str) -> dict[str, Any]:
        """Chat-completions body shared by the blocking and streaming NIM calls."""
        body: dict[str, Any] = {
            "model": self.settings.NVIDIA_NIM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.settings.NVIDIA_NIM_MAX_TOKENS,
            "temperature": self.settings.NVIDIA_NIM_TEMPERATURE,
        }
        if self.settings.NVIDIA_NIM_DISABLE_THINKING:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return body

    async def _synthesize_nim(self, prompt: str, context: list[dict[str, Any]]) -> dict[str, Any]:
        """Calls NVIDIA NIM (OpenAI-compatible API).

        A 502/503/504 is retried once. The hosted endpoint returns short bursts of 503 under load
        (five in 13 minutes on 2026-09-13), and falling straight through hands the answer to a
        *different model* — the user sees a Llama answer, and a benchmark run turns SUSPECT. A
        timeout is not retried: a second full `NVIDIA_NIM_TIMEOUT` would overrun the frontend's
        90 s synthesis budget.
        """
        try:
            client = shared_client(self.settings.NVIDIA_NIM_TIMEOUT)
            for attempt in (1, 2):
                response = await client.post(
                    f"{self.settings.NVIDIA_NIM_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.NVIDIA_NIM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=self._nim_payload(prompt),
                    timeout=self.settings.NVIDIA_NIM_TIMEOUT,
                )
                if attempt == 1 and response.status_code in _NIM_RETRYABLE_STATUS:
                    log.warning("nim.synthesis_retry", status=response.status_code)
                    await asyncio.sleep(_NIM_RETRY_DELAY_S)
                    continue
                break
            response.raise_for_status()
            data = response.json()
            answer_text = data["choices"][0]["message"]["content"]
            # ARCHITECTURE.md §8 mitigation 1, in the form that applies to a hosted model: verify
            # the provider ran the model that was pinned. Nothing checked this before, yet every
            # benchmark figure is attributed to a named model and status.md's "a fallthrough does
            # not change which model answered" rests on it being true.
            mismatch = verify_served_model(self.settings.NVIDIA_NIM_MODEL, data)
            return {
                "answer": answer_text,
                "sources": context,
                "model": "nim",
                "served_model": data.get("model"),
                "model_mismatch": mismatch,
                "raw": data,
            }
        except Exception as e:
            rate_limited = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
            log.error("nim.synthesis_failed", error=str(e), exc_type=type(e).__name__, rate_limited=rate_limited)
            return {"answer": None, "error": str(e), "sources": context, "rate_limited": rate_limited, "failed_provider": "nim"}

    async def _synthesize_ollama(self, prompt: str, context: list[dict[str, Any]]) -> dict[str, Any]:
        """Calls local Ollama (fallback for offline/air-gapped deployments)."""
        try:
            client = shared_client(60.0)
            response = await client.post(
                f"{self.settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": self.settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            return {"answer": data.get("response"), "sources": context, "model": "ollama"}
        except Exception as e:
            rate_limited = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
            log.error("ollama.synthesis_failed", error=str(e), rate_limited=rate_limited)
            return {"answer": None, "error": str(e), "sources": context, "rate_limited": rate_limited, "failed_provider": "ollama"}

    async def _synthesize_cascade(self, prompt: str, context: list[dict[str, Any]]) -> dict[str, Any]:
        """Provider cascade: NIM → OpenRouter → Gemini → Ollama. Each tier is tried only if
        configured; on failure (answer is None) it falls through to the next. With
        only NVIDIA_NIM_API_KEY set, this is NIM-only — same behaviour as before.

        Every tier below NIM serves a different model from the pinned NIM one (tier 1 moved to
        Nemotron when NVIDIA retired llama-3.1-70b), so any fallthrough makes a run's
        answer-quality figure a blend of models — the benchmark flags that as SUSPECT."""
        result: dict[str, Any] | None = None
        attempts: dict[str, dict[str, Any]] = {}
        if self.nim_available:
            result = await self._synthesize_nim(prompt, context)
            attempts["nim"] = result
        if (result is None or result.get("answer") is None) and self.openrouter_available:
            result = await self._synthesize_openrouter(prompt, context)
            attempts["openrouter"] = result
        if (result is None or result.get("answer") is None) and self.gemini_available:
            result = await self._synthesize_gemini(prompt, context)
            attempts["gemini"] = result
        if (result is None or result.get("answer") is None) and self.ollama_available:
            result = await self._synthesize_ollama(prompt, context)
            attempts["ollama"] = result
        if result is None:
            return {
                "answer": None,
                "sources": context,
                "confidence": None,
                "message": ("No LLM configured. Set NVIDIA_NIM_API_KEY, OPENROUTER_API_KEY, "
                            "GEMINI_API_KEY, or OLLAMA_BASE_URL."),
            }

        # Every tier failed. Say *why* — a provider that returned 429 is an exhausted quota,
        # which is an operational problem with a fix, not the model being wrong. Left
        # unlabelled these are indistinguishable: the benchmark scores both as a miss and the
        # UI shows both as "no answer", so a dead free tier looks like poor answer quality.
        if result.get("answer") is None:
            limited = [p for p in ("nim", "openrouter", "gemini", "ollama")
                       if attempts.get(p, {}).get("rate_limited")]
            if limited:
                result["rate_limited"] = True
                result["message"] = (
                    f"Synthesis provider quota exhausted ({', '.join(limited)} returned HTTP 429). "
                    "This is a provider limit, not a knowledge gap — retry after the quota resets."
                )
                log.warning("synthesis.all_providers_rate_limited", providers=limited)
        return result

    async def _synthesize_openrouter(self, prompt: str, context: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Calls OpenRouter — tier 2, tried before Gemini. Serves meta-llama/llama-3.1-70b-instruct,
        which is not the tier-1 model, so an answer from here counts as a fallback.
        """
        try:
            client = shared_client(self.settings.OPENROUTER_TIMEOUT)
            response = await client.post(
                f"{self.settings.OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": self.settings.NVIDIA_NIM_MAX_TOKENS,
                    "temperature": self.settings.NVIDIA_NIM_TEMPERATURE,
                },
                timeout=self.settings.OPENROUTER_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            answer_text = data["choices"][0]["message"]["content"]
            return {"answer": answer_text, "sources": context, "model": "openrouter", "raw": data}
        except Exception as e:
            rate_limited = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
            log.error("openrouter.synthesis_failed", error=str(e), exc_type=type(e).__name__, rate_limited=rate_limited)
            return {"answer": None, "error": str(e), "sources": context, "rate_limited": rate_limited,
                    "failed_provider": "openrouter"}

    async def _synthesize_gemini(self, prompt: str, context: list[dict[str, Any]]) -> dict[str, Any]:
        """Calls Gemini via Google's OpenAI-compatible endpoint — fallback when NIM fails."""
        try:
            client = shared_client(90.0)
            response = await client.post(
                f"{self.settings.GEMINI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.GEMINI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.GEMINI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": self.settings.NVIDIA_NIM_MAX_TOKENS,
                    "temperature": self.settings.NVIDIA_NIM_TEMPERATURE,
                },
                timeout=90.0,
            )
            response.raise_for_status()
            data = response.json()
            answer_text = data["choices"][0]["message"]["content"]
            return {"answer": answer_text, "sources": context, "model": "gemini", "raw": data}
        except Exception as e:
            rate_limited = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
            log.error("gemini.synthesis_failed", error=str(e), exc_type=type(e).__name__, rate_limited=rate_limited)
            return {"answer": None, "error": str(e), "sources": context, "rate_limited": rate_limited, "failed_provider": "gemini"}

    @staticmethod
    def parse_synthesis_response(text: str) -> dict[str, Any]:
        """
        Extracts structured fields from the synthesis prompt output.
        Expected format (from _build_synthesis_prompt):
          ANSWER: ...
          CONFIDENCE: 0.0-1.0
          UNCERTAINTY: ...
          SOURCES_USED: 1, 2, 3
        """
        out: dict[str, Any] = {"answer": None, "confidence": None, "uncertainty": None, "sources_used": []}

        # Markers are matched **anywhere**, not just at line start. Models routinely emit the whole
        # contract on a single line — "…not in the sources. CONFIDENCE: 0.0 UNCERTAINTY: … " — and
        # the previous `^KEY:` (MULTILINE) anchor then matched nothing at all: confidence,
        # uncertainty and sources_used all came back empty. Two consequences, both observed live on
        # a safety-critical query: the raw contract leaked to the user as the answer, and the
        # post-synthesis safety gate never fired because it had no confidence to judge.
        _MARKERS = ("ANSWER", "CONFIDENCE", "UNCERTAINTY", "SOURCES_USED")
        _next_marker = r"(?=\s*(?:" + "|".join(_MARKERS) + r"):|$)"
        for key, field in [
            ("ANSWER", "answer"),
            ("CONFIDENCE", "confidence"),
            ("UNCERTAINTY", "uncertainty"),
            ("SOURCES_USED", "sources_used"),
        ]:
            m = re.search(rf"\b{key}:\s*(.+?){_next_marker}", text, re.DOTALL)
            if m:
                out[field] = m.group(1).strip()
        # Models frequently omit the leading `ANSWER:` marker and start with the prose, then emit
        # the remaining markers. `out["answer"]` then stays None, the caller falls back to the raw
        # text, and the user is shown the parse contract itself —
        # "…CONFIDENCE: 0.0 UNCERTAINTY: … SOURCES_USED: None" — as if it were the answer.
        # Observed live on a safety-critical query. Recover the prose that precedes the first
        # marker instead.
        if out["answer"] is None:
            head = re.split(r"\b(?:CONFIDENCE|UNCERTAINTY|SOURCES_USED):", text, maxsplit=1)[0]
            head = head.strip()
            if head:
                out["answer"] = head

        try:
            out["confidence"] = float(out["confidence"]) if out["confidence"] else None
        except (ValueError, TypeError):
            out["confidence"] = None
        raw_sources = out.get("sources_used") or ""
        out["sources_used"] = [int(x.strip()) for x in str(raw_sources).split(",") if x.strip().isdigit()]
        return out

    async def rca_synthesize(
        self,
        failure_code: str,
        timeline: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Generates an RCA pack via NIM/Ollama.
        Returns raw LLM answer dict; caller parses hypotheses via parse_rca_response().
        Falls back gracefully when no LLM is configured.
        """
        timeline_text = "\n".join(
            f"- [{e.get('occurred_at', '')}] {e.get('event_type', 'event')}: {e.get('description', '')}"
            for e in timeline
        ) or "No events found in the 90-day window."

        evidence_text = self._format_context(evidence) if evidence else "No evidence documents found."

        prompt = f"""You are the Kairos RCA engine for an industrial operational intelligence platform.

Generate a Root Cause Analysis (RCA) pack for failure code: {failure_code}

FAILURE TIMELINE (chronological):
{timeline_text}

EVIDENCE DOCUMENTS:
{evidence_text}

Instructions:
- Rank failure mode hypotheses by evidence weight (1.0 = fully supported, 0.0 = speculative).
- Cite every hypothesis to the specific source document_id(s) from the evidence above.
- NEVER invent information not present in the sources.

Respond in this exact format:
HYPOTHESES:
1. [hypothesis text] | evidence_weight: [0.0-1.0] | sources: [document_id, document_id]
2. [hypothesis text] | evidence_weight: [0.0-1.0] | sources: [document_id]

CONFIDENCE: [0.0-1.0]
UNCERTAINTY: [what is not yet known or requires further investigation]"""

        return await self._synthesize_cascade(prompt, evidence)

    @staticmethod
    def parse_rca_response(text: str) -> dict[str, Any]:
        """
        Parses LLM RCA output into structured hypotheses list.
        Expected format from rca_synthesize prompt:
          HYPOTHESES:
          1. text | evidence_weight: 0.8 | sources: DOC-A, DOC-B
          CONFIDENCE: 0.75
        """
        hypotheses: list[dict[str, Any]] = []

        hyp_match = re.search(r"HYPOTHESES:\n(.*?)(?=\n[A-Z]+:|$)", text, re.DOTALL)
        if hyp_match:
            for line in hyp_match.group(1).strip().splitlines():
                line = line.strip()
                if not line or not re.match(r"^\d+\.", line):
                    continue
                parts = [p.strip() for p in line.split("|")]
                hyp_text = re.sub(r"^\d+\.\s*", "", parts[0]).strip()
                weight = 0.5
                sources: list[str] = []
                for part in parts[1:]:
                    if "evidence_weight" in part:
                        m = re.search(r"[\d.]+", part.split(":", 1)[-1])
                        if m:
                            try:
                                weight = float(m.group())
                            except ValueError:
                                pass
                    elif "sources" in part:
                        raw = part.split(":", 1)[-1].strip()
                        # Drop the model's own "no sources" placeholders. Taken literally they
                        # became a source id — RCA rendered three hypotheses each citing a
                        # document called "None", which is worse than citing nothing: it is a
                        # fabricated provenance chip on a page whose rule is that no claim
                        # appears without provenance.
                        # A source must look like a *document id*, not prose. The model does not
                        # reliably leave the field empty when it has no citation — it writes
                        # "None", or a sentence like "[No specific document_id, inferred from
                        # work_order_created: …]", which comma-splits into several fake ids.
                        # Rendered, each became a provenance chip on a surface whose rule is that
                        # no claim appears without provenance. Citing nothing is honest; citing an
                        # invented id is not.
                        # Must additionally contain a digit or a hyphen. Every document id in this
                        # corpus does (DOC-…, EQ-101, FP-MAN-EQ1XX-SEAL); a bare English word like
                        # "speculative" or "unknown" does not, and those are what the model reaches
                        # for when it has no citation to give.
                        sources = [
                            tok for tok in (s.strip().strip("[]").strip() for s in raw.split(","))
                            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{2,}", tok or "")
                            and re.search(r"[\d\-]", tok or "")
                            and (tok or "").lower() not in {"none", "null", "n/a"}
                        ]
                if hyp_text:
                    hypotheses.append({"hypothesis": hyp_text, "evidence_weight": weight, "sources": sources})

        conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", text)
        confidence = float(conf_match.group(1)) if conf_match else None

        return {"hypotheses": hypotheses, "confidence": confidence}

    @property
    def jina_available(self) -> bool:
        return bool(self.settings.JINA_API_KEY)

    async def embed(self, text: str, task: str = "retrieval.passage") -> list[float]:
        """
        Generates text embeddings (1024-dim, jina-embeddings-v3).
        Primary: Jina AI — keeps NIM key reserved for LLM synthesis.
        Fallback: Ollama nomic-embed-text (local, air-gapped deployments).
        task: "retrieval.passage" for indexing, "retrieval.query" for search queries.
        """
        if self.jina_available:
            return await self._embed_jina(text, task)
        return await self._embed_ollama(text)

    async def _embed_jina(self, text: str, task: str) -> list[float]:
        cache_key = (task, text)
        cached = _EMBED_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            client = shared_client(30.0)
            response = await client.post(
                self.settings.JINA_EMBED_URL,
                headers={"Authorization": f"Bearer {self.settings.JINA_API_KEY}"},
                json={
                "model": self.settings.JINA_EMBED_MODEL,
                "input": [text],
                "task": task,
                "dimensions": self.settings.EMBEDDING_DIMENSION,
                "embedding_type": "float",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
        except Exception as e:
            log.error("embed.jina_failed", error=str(e))
            return await self._embed_ollama(text)

        _EMBED_CACHE.put(cache_key, vector)
        return vector

    async def _embed_ollama(self, text: str) -> list[float]:
        try:
            client = shared_client(30.0)
            response = await client.post(
                f"{self.settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": self.settings.OLLAMA_EMBED_MODEL, "prompt": text},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            log.error("embed.ollama_failed", error=str(e))
            return []
