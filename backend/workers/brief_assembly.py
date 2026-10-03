"""
Brief Assembly Worker — Layer 8: Delayed brief generation for late-arrival compensation.
Fires after LATE_ARRIVAL_WINDOW_MINUTES countdown, allowing correlated events for the
same asset to be batched into a single contextual brief.
"""

import sys

sys.path.insert(0, "/app")

import structlog

from workers.celery_app import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(
    name="workers.brief_assembly.assemble_brief",
    queue="ingestion",
    acks_late=True,
    time_limit=120,
    soft_time_limit=90,
)
def assemble_brief(event_type: str, event_dict: dict) -> str:
    """
    Assembles and delivers a contextual brief after the late-arrival window expires.
    By the time this fires, any correlated events for the same asset are already
    in operational_events, so BriefEngine's context queries pick them up naturally.
    """
    from api.services.http import run_with_client
    return run_with_client(_assemble(event_type, event_dict))


async def _assemble(event_type: str, event_dict: dict) -> str:
    import redis.asyncio as aioredis
    from elasticsearch import AsyncElasticsearch
    from neo4j import AsyncGraphDatabase
    from qdrant_client import AsyncQdrantClient
    from supabase import create_client

    from api.config import Settings
    from api.models.event import PTWEvent, ShiftHandoverEvent, WorkOrderEvent
    from api.services.brief_engine import BriefEngine

    settings = Settings()

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
    )
    qdrant = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)

    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)

    redis_client = aioredis.from_url(settings.REDIS_URL)

    try:
        engine = BriefEngine(driver, qdrant, es, supabase, settings)

        if event_type == "work_order_created":
            brief = await engine.assemble_work_order_brief(WorkOrderEvent(**event_dict))
        elif event_type == "ptw_generated":
            brief = await engine.assemble_ptw_brief(PTWEvent(**event_dict))
        elif event_type == "shift_handover":
            brief = await engine.assemble_shift_handover_brief(ShiftHandoverEvent(**event_dict))
        elif event_type == "recurring_failure_detected":
            brief = await engine.assemble_recurring_failure_brief(event_dict)
        elif event_type == "equipment_tag_out":
            brief = await engine.assemble_tag_out_brief(event_dict)
        elif event_type == "inspection_complete":
            brief = await engine.assemble_inspection_brief(event_dict)
        else:
            log.warning("brief_assembly.unknown_event_type", event_type=event_type)
            return ""

        brief_id = await engine.deliver(brief, redis_client)
        log.info("brief_assembly.complete", event_type=event_type, brief_id=brief_id)
        return brief_id
    except Exception as exc:
        log.error("brief_assembly.failed", event_type=event_type, error=str(exc))
        raise
    finally:
        await driver.close()
        await es.close()
        await redis_client.aclose()
