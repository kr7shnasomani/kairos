"""
Pydantic models — Document (Layer 2: Immutable Vault, Layer 3: Extraction)
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field


class SynthesizeRequest(BaseModel):
    query: str
    context: list[dict[str, Any]] = Field(default_factory=list, description="Retrieved SearchResult dicts")
    query_category: str | None = Field(None, description="Safety-critical category key if applicable")


class SynthesizeResponse(BaseModel):
    answer: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    refused: bool = False
    refusal_reason: str | None = None
    safety_critical: bool = False
    sources_used: list[int] = Field(default_factory=list)
    uncertainty: str | None = None
    model: str | None = None
    message: str | None = None
    # True when every synthesis provider returned HTTP 429. Without this the caller cannot tell an
    # exhausted quota from a model that had nothing to say — they look identical (answer=None), and
    # a benchmark scores the difference as poor answer quality. `LLMService` has always set this on
    # its result dict; the response model simply dropped it on the way out.
    rate_limited: bool = False
    # Open engineering-track conflicts awaiting MoC resolution that touch an asset cited in this
    # answer. ARCHITECTURE.md Layer 7 / Flow C: "every query touching that fact displays an
    # explicit warning banner identifying the pending MoC by number" — the graph is not updated
    # until the MoC is signed, so an answer drawn from that asset must say the value is contested.
    pending_moc: list[dict[str, Any]] = Field(default_factory=list)


class AnswerFeedbackRequest(BaseModel):
    """Phase-2 single-tap rating on a synthesized answer (Layer 12 trust loop)."""

    query: str
    rating: str = Field(..., pattern="^(accurate|missing_context|incorrect)$")
    note: str | None = None
    sources_used: list[int] = Field(default_factory=list)
    model: str | None = None


class RCAPackRequest(BaseModel):
    asset_id: str
    incident_date: datetime
    failure_code: str
    include_quarantine: bool = False


class RCAPackResponse(BaseModel):
    asset_id: str
    incident_date: str
    failure_code: str
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    supporting_documents: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    refused: bool = False
    synthesis_available: bool = False
    # Same Layer-7 disclosure as SearchResponse/SynthesizeResponse — an RCA hypothesis built on an
    # asset whose parameters are under MoC dispute must say so.
    pending_moc: list[dict[str, Any]] = Field(default_factory=list)


class VaultDocument(BaseModel):
    document_id: str
    sha256_hash: str
    file_name: str
    file_size_bytes: int
    mime_type: str
    document_type: str
    authority_level: int = Field(..., ge=1, le=5)
    source_system: str
    vault_url: str | None = Field(None, description="Authenticated Supabase Storage URL for direct retrieval")
    ingested_at: datetime
    ingested_by: str
    ingested_by_name: str | None = Field(None, description="Display name (or email) of the uploader, when resolvable")
    status: str = Field(..., description="active, superseded, archived, disputed")
    version_chain: str | None = Field(None, description="document_id this supersedes (new version → old version pointer)")
    asset_links: list[str] = Field(default_factory=list, description="Linked canonical asset IDs")
    # Layer 2 IAM-derived permission tags, stamped at ingestion (migration 017). Declared as a
    # `list[str]` before it was ever populated, which could not carry the structured tags the
    # spec describes: {site_id, required_action, classification, ingested_by, derived_from}.
    access_tags: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def extraction_path(self) -> str:
        """Whether this document's text was read off an image or parsed from digital structure."""
        return "ocr" if self.mime_type.startswith("image/") else "native"

    @computed_field
    @property
    def handwriting_suspect(self) -> bool:
        """
        Layer 3: image-path documents are where handwriting lives — field inspection forms and
        shift logs. Derived here rather than in the frontend so the rule has one definition, and
        surfaced as a *flag* rather than a confidence penalty: lowering the score would push these
        under the 0.7 quarantine threshold and quietly drop real facts out of the canonical graph.

        Engineering drawings are excluded. A P&ID is an image and goes through the vision path,
        but it carries no handwriting — flagging it would put a "handwriting suspect" caution on
        every drawing in the vault and teach reviewers to ignore the badge.
        """
        return self.mime_type.startswith("image/") and self.document_type != "pid_drawing"


class DocumentStatus(BaseModel):
    document_id: str
    pipeline_stage: str = Field(
        ...,
        description="queued, ocr_running, ner_running, graph_linking, vector_indexing, review_required, rejected, complete, failed"
    )
    progress_percent: int = Field(..., ge=0, le=100)
    ocr_confidence: float | None = None
    ner_entity_count: int | None = None
    graph_edges_created: int | None = None
    review_items_pending: int = 0
    error: str | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ExtractedEntity(BaseModel):
    entity_type: str = Field(..., description="asset_tag, process_parameter, material, person, date, regulation, failure_mode")
    value: str
    normalized_value: str | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    span_start: int | None = None
    span_end: int | None = None
    linked_asset_id: str | None = None
    requires_review: bool = False


class ExtractionResult(BaseModel):
    document_id: str
    extraction_model: str
    entities: list[ExtractedEntity] = Field(default_factory=list)
    graph_edges_created: int = 0
    vector_chunks_indexed: int = 0
    review_items: list[dict[str, Any]] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    # Layer 3: whether the text was read off an image or parsed from a digital document.
    # Handwriting only occurs on the image path, and the architecture asks for it to be
    # "flagged explicitly in the extraction output" — as a marker, not a confidence penalty.
    extraction_path: str = "unknown"
    handwriting_suspect: bool = False


class SearchResult(BaseModel):
    document_id: str
    asset_id: str | None = None
    document_type: str
    title: str
    snippet: str
    authority_level: int
    status: str
    relevance_score: float
    retrieval_method: str = Field(..., description="exact, semantic, graph")
    is_quarantine: bool = False
    vault_url: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    synthesis: None = None
    retrieval_methods: list[str] = Field(default_factory=list)
    # Layer 7: assets cited here that sit under an unresolved engineering-track conflict. The
    # canonical graph is deliberately not updated while a MoC is open, so results drawn from
    # such an asset are reporting a value under formal dispute. Previously only synthesized
    # answers carried this, so the same asset was flagged on one surface and silent on another.
    pending_moc: list[dict[str, Any]] = Field(default_factory=list)


class ConflictItem(BaseModel):
    conflict_id: str
    track: str = Field(..., description="administrative, engineering")
    asset_id: str | None = None
    parameter: str
    source_a: dict[str, Any]
    source_b: dict[str, Any]
    authority_a: int
    authority_b: int
    severity: str
    status: str = Field(..., description="open, pending_moc, resolved")
    sla_deadline: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QuarantineItem(BaseModel):
    item_id: str
    asset_id: str | None = None
    content: str
    input_type: str = Field(..., description="field_observation, voice_note, elicitation_response, deviation_flag")
    submitted_by: str
    submitted_at: datetime
    reviewer_id: str | None = None
    review_status: str = Field(default="pending", description="pending, promoted, disputed, archived")
    linked_work_order_id: str | None = None


class PromoteQuarantineRequest(BaseModel):
    authority_level: int = Field(..., ge=1, le=5, description="1=Regulatory 2=Engineering 3=OEM 4=Procedure 5=Field")
    relationship_type: str = Field(..., description="Neo4j relationship type for the promoted edge, e.g. DOCUMENTED_BY")
    # Defaults to `field_observation`, not `procedure`: quarantine holds field inputs, and a promoted
    # one typed as a procedure satisfied every clause requiring a documented procedure.
    document_type: str = Field("field_observation", description="Type of document for the promoted edge: field_observation, inspection_report, procedure, …")
    notes: str | None = None


class RequestQuarantineInfoRequest(BaseModel):
    """A durable, reviewer-authored follow-up request for a pending item."""

    note: str = Field(..., min_length=1, max_length=2000)
