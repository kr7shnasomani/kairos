"""
Kairos — Application Configuration
All settings are read from environment variables (via .env file in development).
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # App
    # -------------------------------------------------------------------------
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_VERSION: str = "0.1.0"
    APP_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Abuse guards for the public API
    MAX_UPLOAD_MB: int = 25                 # reject document uploads larger than this
    RATE_LIMIT_PER_MINUTE: int = 120        # per-client-IP request cap (0 = disabled)

    @property
    def dev_bypass_allowed(self) -> bool:
        """Single definition of "a bypass of the trust boundary is permitted here".

        Two bypasses read it: the unauthenticated mock user (`dependencies.get_current_user`)
        and the OPA middleware's no-token pass-through + unreachable-OPA fallback. Both used to
        key off `APP_DEBUG` alone, so a deployment that forgot `APP_ENV=production` got the
        dev bypass *and* skipped the `_no_insecure_defaults_in_prod` guardrail that is supposed
        to catch exactly that. Requiring both means the guardrail is no longer the only thing
        standing between a mis-set env and an open API.
        """
        return self.APP_DEBUG and self.APP_ENV != "production"

    # -------------------------------------------------------------------------
    # Supabase (cloud — filled in later)
    # -------------------------------------------------------------------------
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_STORAGE_BUCKET: str = "kairos-vault"

    # -------------------------------------------------------------------------
    # Neo4j (local Docker)
    # -------------------------------------------------------------------------
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "kairos_dev_password"
    NEO4J_DATABASE: str = "neo4j"

    # -------------------------------------------------------------------------
    # Qdrant (local Docker)
    # -------------------------------------------------------------------------
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_KNOWLEDGE: str = "kairos_knowledge"
    QDRANT_COLLECTION_DOCUMENTS: str = "kairos_documents"

    # -------------------------------------------------------------------------
    # Elasticsearch (local Docker)
    # -------------------------------------------------------------------------
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_USERNAME: str = ""
    ELASTICSEARCH_PASSWORD: str = ""
    ELASTICSEARCH_INDEX_ASSETS: str = "kairos_assets"
    ELASTICSEARCH_INDEX_DOCUMENTS: str = "kairos_documents"
    ELASTICSEARCH_INDEX_EVENTS: str = "kairos_events"

    # -------------------------------------------------------------------------
    # Redis (local Docker)
    # -------------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_PASSWORD: str = ""
    REDIS_DB_CACHE: int = 0
    REDIS_DB_CELERY: int = 1
    REDIS_DB_STREAMS: int = 2
    REDIS_STREAM_WORK_ORDERS: str = "kairos:events:work_orders"
    REDIS_STREAM_PTW: str = "kairos:events:ptw"
    REDIS_STREAM_SHIFT_HANDOVER: str = "kairos:events:shift_handover"
    REDIS_STREAM_ALARMS: str = "kairos:events:alarms"
    REDIS_STREAM_BRIEFS: str = "kairos:events:briefs"
    REDIS_STREAM_TAG_OUT: str = "kairos:events:tag_out"
    REDIS_STREAM_INSPECTIONS: str = "kairos:events:inspections"

    # -------------------------------------------------------------------------
    # NVIDIA NIM (cloud, key provided later)
    # -------------------------------------------------------------------------
    NVIDIA_NIM_API_KEY: str = ""
    NVIDIA_NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    # meta/llama-3.1-70b-instruct was retired by NVIDIA (410 Gone, 2026-09-13). Of the chat models
    # the account still lists, this one answered in the ANSWER/CONFIDENCE contract at ~2.5 s with
    # thinking off; several other listed models 404 or hang. Probe before switching again.
    NVIDIA_NIM_MODEL: str = "nvidia/nemotron-3-super-120b-a12b"
    # Nemotron 3 reasons before answering by default, spending the token budget on hidden
    # reasoning (an answer came back truncated to 5 words) and never streaming `content` deltas.
    # Sent as `chat_template_kwargs.enable_thinking=false`; set False for a model that rejects it.
    NVIDIA_NIM_DISABLE_THINKING: bool = True
    NVIDIA_NIM_MAX_TOKENS: int = 4096
    NVIDIA_NIM_TEMPERATURE: float = 0.1
    # Per-call cap; on timeout the cascade falls through to Gemini. MUST leave headroom under the
    # frontend's 90 s budget for POST /search/synthesize (frontend/src/lib/api.ts), because a
    # fallthrough costs cap + Gemini (observed up to +11.6 s): at a 90 s cap the fallbacks landed at
    # 92-102 s and aborted in the browser. Measured over 23 NIM calls: 60 s keeps 86% of answers on
    # NIM with a worst-case fallthrough of ~72 s. Raise the frontend budget first if you raise this.
    NVIDIA_NIM_TIMEOUT: float = 60.0
    # Vision-language model for P&ID topology extraction (Layer 3, Path B)
    NVIDIA_NIM_VISION_MODEL: str = "meta/llama-3.2-11b-vision-instruct"

    # -------------------------------------------------------------------------
    # OpenRouter — tier 2, ahead of Gemini ON PURPOSE.
    #
    # It served the same llama-3.1-70b as tier 1 until NVIDIA retired that model (2026-09-13); tier 1
    # is now Nemotron, so an OpenRouter answer IS a different model and the benchmark counts it as a
    # fallback, like Gemini. Empty key = tier skipped.
    # -------------------------------------------------------------------------
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "meta-llama/llama-3.1-70b-instruct"
    # Its own cap rather than reusing NVIDIA_NIM_TIMEOUT: that setting is named for, and tuned to,
    # NVIDIA's latency tail, and sharing it means tuning one provider silently retimes the other.
    # Measured ~1.4 s here, so this is generous headroom, not a target.
    OPENROUTER_TIMEOUT: float = 60.0

    # -------------------------------------------------------------------------
    # Gemini — optional LLM fallback via Google's OpenAI-compatible endpoint.
    # Empty key = disabled; the cascade then stays on NIM (→ Ollama if configured).
    # Fill GEMINI_API_KEY to enable NIM → Gemini → Ollama. (Any OpenAI-compatible
    # provider works — just change GEMINI_BASE_URL + GEMINI_MODEL.)
    # -------------------------------------------------------------------------
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"

    # -------------------------------------------------------------------------
    # Jina AI (embeddings — keeps NIM key free for synthesis/LLM tasks)
    # -------------------------------------------------------------------------
    JINA_API_KEY: str = ""
    JINA_EMBED_MODEL: str = "jina-embeddings-v3"
    JINA_EMBED_URL: str = "https://api.jina.ai/v1/embeddings"

    # -------------------------------------------------------------------------
    # Ollama (local, fallback)
    # -------------------------------------------------------------------------
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:14b"
    OLLAMA_NER_MODEL: str = "llama3.1:8b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # -------------------------------------------------------------------------
    # Embeddings
    # -------------------------------------------------------------------------
    EMBEDDING_DIMENSION: int = 1024  # jina-embeddings-v3 output dim

    # -------------------------------------------------------------------------
    # Celery
    # -------------------------------------------------------------------------
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # -------------------------------------------------------------------------
    # Temporal
    # -------------------------------------------------------------------------
    TEMPORAL_ADDRESS: str = "localhost:7233"
    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "kairos-ingestion"
    TEMPORAL_TASK_QUEUE_ELICITATION: str = "kairos-elicitation"

    # -------------------------------------------------------------------------
    # OPA
    # -------------------------------------------------------------------------
    OPA_URL: str = "http://kairos-opa:8181"

    # -------------------------------------------------------------------------
    # OpenTelemetry
    # -------------------------------------------------------------------------
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "kairos-api"
    OTEL_SERVICE_VERSION: str = "0.1.0"

    # -------------------------------------------------------------------------
    # EEMUA 191 Push Governor
    # -------------------------------------------------------------------------
    MAX_PUSH_PER_USER_PER_HOUR: int = 6
    BRIEF_COOLDOWN_HOURS: int = 4
    DEDUP_WINDOW_MINUTES: int = 10
    LATE_ARRIVAL_WINDOW_MINUTES: int = 5
    PLANT_STATE_DEFAULT: str = "normal"

    # -------------------------------------------------------------------------
    # Layer 12: phased trust architecture
    #
    # The architecture treats the deployment phases as *release gates embedded in the software*,
    # not a label:
    #   1 — Shadow / retrieval only: no synthesis, no proactive briefs.
    #   2 — Human-in-the-loop assist: synthesis on, proactive delivery still off.
    #   3 — Governed proactive: everything on.
    #
    # Defaults to 3 so behaviour is unchanged unless a deployment deliberately steps back.
    # -------------------------------------------------------------------------
    KAIROS_PHASE: int = 3

    # -------------------------------------------------------------------------
    # Layer 4: timestamp alignment across source systems
    #
    # Brownfield plants run EAM, DMS, SCADA and email archives whose clocks are not on a common
    # NTP source. Unreconciled, that corrupts temporal ordering and therefore time-travel RCA.
    #
    # This compares the *same correlated event as reported by different source systems* — never
    # occurred_at against ingested_at, which legitimately differ by months for historical
    # documents and would flag the entire corpus.
    #
    # Ships report-only: drift is logged and surfaced, but no conflict row is opened until
    # TIMESTAMP_DRIFT_ENFORCE is turned on deliberately.
    # -------------------------------------------------------------------------
    # The tolerance itself is declared once under "Ingestion pipeline" below — both the
    # cross-source check (services/timestamp_alignment.py) and the pipeline's own check read
    # the same field. It used to be declared here as well; Pydantic keeps the last definition,
    # so editing this copy silently did nothing.
    TIMESTAMP_DRIFT_ENFORCE: bool = False

    # -------------------------------------------------------------------------
    # Layer 0: model gate enforcement
    #
    # The architecture wants a model that passes globally but regresses on a specific asset class
    # blocked *for that class* until retrained. Enforcement runs through the circuit breaker that
    # already halts extraction per asset class — one mechanism, not two.
    #
    # Ships OFF: on a small corpus a single class can fail on noise, and an enforcing gate would
    # halt extraction for that class mid-demo. Turn on deliberately once the corpus is large
    # enough for per-class scores to be stable.
    # -------------------------------------------------------------------------
    MODEL_GATE_ENFORCE: bool = False

    # -------------------------------------------------------------------------
    # Go Connector
    # -------------------------------------------------------------------------
    GO_CONNECTOR_PORT: int = 8090
    HISTORIAN_QUERY_TIMEOUT_SECONDS: int = 30
    INTERNAL_API_KEY: str = "kairos-internal-dev-key"
    # Cache verified JWTs for this many seconds to skip the per-request Supabase
    # Auth round-trip. Revocation staleness is bounded to this value. Set 0 to
    # disable (verify every request — strictest, slowest).
    AUTH_CACHE_TTL_SECONDS: int = 60

    # HMAC-SHA256 shared secret for the inbound MoC resolution webhook
    # (POST /governance/moc/webhook). ARCHITECTURE.md requires the plant's MoC system to sign
    # resolutions before Kairos updates the canonical graph. `routers/governance.py` read this via
    # getattr() long before the field existed, so the check silently never ran whatever .env said.
    # None = unsigned webhooks accepted (dev default). Once set, requests MUST carry a valid
    # X-Webhook-Signature — a missing header is rejected, not waved through.
    MOC_WEBHOOK_SECRET: str | None = None

    # -------------------------------------------------------------------------
    # Groq — Voice Transcription (Whisper-large-v3 via API)
    # -------------------------------------------------------------------------
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"

    # -------------------------------------------------------------------------
    # NVIDIA NIM — OCR (Nemotron-OCR-v2)
    # -------------------------------------------------------------------------
    NVIDIA_NIM_OCR_MODEL: str = "nvidia/nemotron-ocr-v2"
    NVIDIA_NIM_NER_MODEL: str = "meta/llama-3.2-11b-vision-instruct"
    # NER runs in background ingestion, so it is not bound by the 90 s synthesis budget that caps
    # NVIDIA_NIM_TIMEOUT. The hosted NER model answers a 2,000-character document in 60–180 s under load.
    NVIDIA_NIM_NER_TIMEOUT: float = 120.0

    # -------------------------------------------------------------------------
    # Ingestion pipeline
    # -------------------------------------------------------------------------
    # Two consumers: workflows/document_pipeline.py (occurred_at vs ingested_at) and
    # services/timestamp_alignment.py (same event across source systems). Sole declaration —
    # see the note beside TIMESTAMP_DRIFT_ENFORCE above.
    TIMESTAMP_DRIFT_TOLERANCE_MINUTES: int = 60

    @model_validator(mode="after")
    def _no_insecure_defaults_in_prod(self) -> "Settings":
        """Fail-closed: refuse to boot in production while any secret that protects the live
        system is still its dev default. Dev/test are untouched. Set these in the environment.
        INTERNAL_API_KEY is the critical one — its default is an admin auth-bypass (dependencies.py)."""
        if self.APP_ENV != "production":
            return self
        bad: list[str] = []
        if self.INTERNAL_API_KEY == "kairos-internal-dev-key":
            bad.append("INTERNAL_API_KEY (default grants admin — critical)")
        if self.APP_SECRET_KEY == "CHANGE_ME_IN_PRODUCTION":
            bad.append("APP_SECRET_KEY")
        if self.NEO4J_PASSWORD == "kairos_dev_password":
            bad.append("NEO4J_PASSWORD")
        if not self.SUPABASE_SERVICE_ROLE_KEY:
            bad.append("SUPABASE_SERVICE_ROLE_KEY")
        if not self.SUPABASE_JWT_SECRET:
            bad.append("SUPABASE_JWT_SECRET")
        if self.APP_DEBUG:
            bad.append("APP_DEBUG must be false in production (leaks tracebacks + bypasses OPA authz)")
        if bad:
            raise ValueError(
                "APP_ENV=production but insecure defaults remain: " + "; ".join(bad)
                + ". Set them in the environment before deploying."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
