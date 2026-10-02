"""
Celery application — async task queue configuration.
Brokers: Redis (dev). Workers: ingestion, extraction, attribution.
"""

import os

from celery import Celery
from celery.signals import worker_process_init

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "kairos",
    broker=broker_url,
    backend=result_backend,
    include=[
        "workers.extraction",
        "workers.attribution",
        "workers.voice_transcription",
        "workers.brief_assembly",
        "workers.model_validation",
        "workers.offboarding",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "workers.extraction.*": {"queue": "extraction"},
        "workers.attribution.*": {"queue": "attribution"},
        "workers.voice_transcription.*": {"queue": "transcription"},
        "workers.brief_assembly.*": {"queue": "ingestion"},
        "workers.model_validation.*": {"queue": "validation"},
        "workers.offboarding.*": {"queue": "elicitation"},
    },
    task_track_started=True,
    task_acks_late=True,  # Ensure tasks aren't lost if worker crashes
    worker_prefetch_multiplier=1,  # One task at a time for ML-heavy jobs
    # Perf/reliability wins (celery-expert skill):
    result_expires=3600,  # expire results so the Redis backend can't grow unbounded
    broker_connection_retry_on_startup=True,  # don't crash if Redis lags at startup (Celery 6 default=False)
    worker_max_tasks_per_child=200,  # recycle workers to cap memory creep on long-lived pools
)


@worker_process_init.connect
def _init_telemetry(**_kwargs) -> None:
    """
    Give each worker process its own MeterProvider.

    Without this the worker had none, so `briefs_delivered` and `governor_suppressed` — both
    recorded inside Celery tasks — were permanent no-ops and never reached Grafana. The
    dashboards' brief/governor panels could not have shown data under any amount of real traffic.

    Wired to `worker_process_init` rather than module import on purpose: Celery's default pool
    forks, and an exporter's background thread does not survive a fork. Each child must build its
    own provider. `setup_telemetry` is already fail-soft, so a missing OTEL endpoint stays a
    warning rather than killing the worker.
    """
    from api.middleware.telemetry import setup_telemetry

    setup_telemetry()
