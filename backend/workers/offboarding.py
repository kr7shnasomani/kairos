"""
Off-Boarding Interview Worker — Layer 6: Retiring Expert Knowledge Transfer.
Generates graph-derived questions for each equipment family in an off-boarding programme.
"""

import asyncio
import re
import sys

sys.path.insert(0, "/app")

from datetime import UTC, datetime
from typing import Any

import structlog

from workers.celery_app import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(
    queue="elicitation",
    name="workers.offboarding.generate_offboarding_questions",
    acks_late=True,
    time_limit=300,
    soft_time_limit=270,
)
def generate_offboarding_questions(item_id: str) -> dict[str, Any]:
    return asyncio.run(_generate(item_id))


async def _generate(item_id: str) -> dict[str, Any]:
    from neo4j import AsyncGraphDatabase
    from supabase import create_client

    from api.config import Settings
    from api.services.llm import LLMService

    settings = Settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    item_result = await asyncio.to_thread(
        lambda: supabase.table("offboarding_session_items")
        .select("id, session_id, session_number, equipment_family")
        .eq("id", item_id)
        .single()
        .execute()
    )
    item = item_result.data
    equipment_family = item["equipment_family"]
    session_id = item["session_id"]

    # Query Neo4j for known vs unknown failure modes for this equipment family
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
    )
    known: list[str] = []
    unknown: list[str] = []
    now = datetime.now(UTC).isoformat()
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as neo4j_session:
            result = await neo4j_session.run(
                """
                MATCH (a:Asset)-[r]->(n)
                WHERE a.equipment_class = $equip_family
                  AND (r.valid_to IS NULL OR datetime(r.valid_to) > datetime())
                  AND r.authority_level <= 3
                  AND r.valid_from <= $as_of
                RETURN n.name AS mode,
                       r.confidence AS confidence,
                       r.verification_status AS vstatus
                ORDER BY r.confidence DESC
                LIMIT 25
                """,
                equip_family=equipment_family,
                as_of=now,
            )
            async for rec in result:
                mode = rec["mode"]
                if not mode:
                    continue
                if rec["vstatus"] == "verified" and (rec["confidence"] or 0) >= 0.7:
                    known.append(mode)
                else:
                    unknown.append(mode)
    finally:
        await driver.close()

    context_items: list[dict[str, Any]] = [
        {"text": f"Known fact: {m}", "confidence": 0.9, "authority_level": 2}
        for m in known
    ] + [
        {"text": f"Knowledge gap: {m}", "confidence": 0.4, "authority_level": 4}
        for m in unknown
    ]
    if not context_items:
        context_items = [{
            "text": f"No documented failure history for equipment family: {equipment_family}.",
            "confidence": 0.5,
            "authority_level": 3,
        }]

    llm = LLMService(settings)
    prompt = (
        f"You are interviewing a retiring expert about {equipment_family} equipment. "
        f"Known facts: {known or ['none documented']}. "
        f"Knowledge gaps: {unknown or ['none identified']}. "
        "Generate 5 questions a retiring engineer would uniquely know — focus on failure attribution accuracy, "
        "non-obvious operating conditions, and historical incidents not fully documented."
    )
    llm_result = await llm.synthesize(prompt, context_items)
    answer_text = llm_result.get("answer") or ""

    answer_match = re.search(r"ANSWER:\s*(.+?)(?:\nCONFIDENCE:|$)", answer_text, re.DOTALL | re.IGNORECASE)
    answer_block = answer_match.group(1).strip() if answer_match else answer_text

    questions: list[str] = []
    for part in re.split(r"\d+[\.\)]\s+", answer_block):
        q = part.strip()
        if q and "?" in q:
            questions.append(q)
        if len(questions) >= 5:
            break

    if not questions:
        for line in answer_text.split("\n"):
            line = line.strip().lstrip("0123456789.-) ")
            if line and "?" in line:
                questions.append(line)
            if len(questions) >= 5:
                break

    if not questions:
        # ponytail: fallback so item always reaches questions_ready even on LLM failure
        # Families are stored as class keys ("ROTATING_CENTRIFUGAL_PUMP"); an expert reads prose.
        family = equipment_family.replace("_", " ").lower()
        questions = [
            f"What are the most common {family} failure modes you have encountered?",
            f"Which {family} failure scenarios are hardest to diagnose and why?",
            f"What operating conditions are most likely to cause {family} failures?",
            f"Are there undocumented workarounds or field tricks for {family} issues?",
            f"Which historical {family} incidents should future engineers know about?",
        ]

    await asyncio.to_thread(
        lambda: supabase.table("offboarding_session_items").update({
            "questions": questions,
            "status": "questions_ready",
        }).eq("id", item_id).execute()
    )

    log.info(
        "offboarding.questions_generated",
        item_id=item_id,
        session_id=session_id,
        equipment_family=equipment_family,
        count=len(questions),
    )
    return {"item_id": item_id, "equipment_family": equipment_family, "questions": questions}
