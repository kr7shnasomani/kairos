"""
Event bus service — Redis Streams producer/consumer (Layer 8).
Implements EEMUA 191 push governor logic.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
import structlog

from api.config import Settings
from api.services.metrics import governor_suppressed

log = structlog.get_logger(__name__)


class EventBusService:
    """
    Publishes events to Redis Streams and manages the EEMUA 191 push governor.
    Governor enforces ≤6 push events per operator per hour in normal operation.
    """

    def __init__(self, redis: aioredis.Redis, settings: Settings):
        self.redis = redis
        self.settings = settings

    # -------------------------------------------------------------------------
    # Publishing
    # -------------------------------------------------------------------------

    async def publish(self, stream: str, event: dict[str, Any]) -> str:
        """Publishes an event to a Redis Stream. Returns the stream entry ID."""
        # Serialize to flat dict (Redis Streams don't support nested structures)
        flat_event = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in event.items()}
        flat_event["published_at"] = datetime.utcnow().isoformat()
        entry_id = await self.redis.xadd(stream, flat_event, maxlen=1000)
        log.info("event_bus.published", stream=stream, event_id=flat_event.get("event_id"), entry_id=entry_id)
        return entry_id

    async def publish_work_order(self, event: dict[str, Any]) -> str:
        return await self.publish(self.settings.REDIS_STREAM_WORK_ORDERS, event)

    async def publish_ptw(self, event: dict[str, Any]) -> str:
        return await self.publish(self.settings.REDIS_STREAM_PTW, event)

    async def publish_shift_handover(self, event: dict[str, Any]) -> str:
        return await self.publish(self.settings.REDIS_STREAM_SHIFT_HANDOVER, event)

    # -------------------------------------------------------------------------
    # EEMUA 191 Push Governor (Layer 8 — Trigger Governance Subsystem)
    # -------------------------------------------------------------------------

    def _governor_key(self, user_id: str) -> str:
        # Sorted-set key. Each member is a brief_id (dedup); score is the UNIX timestamp
        # of the push. Members older than 3600 s are pruned before every read.
        return f"kairos:governor:{user_id}:pushes"

    async def check_governor(
        self,
        user_id: str,
        priority: str = "normal",
        site_id: str = "",
        supabase=None,
    ) -> bool:
        """
        Returns True if a brief can be delivered to this user, False if suppressed.
        PTW briefs (priority='critical') are NEVER suppressed — always returns True.
        Checks plant operating state first: turnaround/shutdown/emergency suppresses
        all non-critical briefs regardless of hourly count.
        """
        if priority == "critical":
            return True  # PTW briefs are never suppressed (EEMUA 191 compliance)

        # Plant state gate — checked before hourly count
        if site_id and supabase:
            plant_state = await self.get_plant_state(site_id, supabase)
            if plant_state in ("turnaround", "shutdown", "emergency"):
                log.info(
                    "governor.plant_state_suppression",
                    user_id=user_id,
                    site_id=site_id,
                    plant_state=plant_state,
                    reason="plant_state_suppression",
                )
                return False

        count_key = self._governor_key(user_id)
        now_ts = datetime.now(UTC).timestamp()
        cutoff = now_ts - 3600
        # Atomically prune expired pushes, then count the remaining ones.
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(count_key, "-inf", cutoff)
        pipe.zcard(count_key)
        _, current_count = await pipe.execute()

        ceiling = self.settings.MAX_PUSH_PER_USER_PER_HOUR
        if current_count >= ceiling:
            governor_suppressed.add(1, {"user_id": user_id})
            log.info("governor.suppressed", user_id=user_id, count=current_count, ceiling=ceiling)
            return False
        return True

    async def get_plant_state(self, site_id: str, supabase) -> str:
        """Returns the current plant operating state for a site (defaults to PLANT_STATE_DEFAULT)."""
        if not site_id:
            return self.settings.PLANT_STATE_DEFAULT
        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("plant_operating_states")
                .select("state, expires_at")
                .eq("site_id", site_id)
                .order("set_at", desc=True)
                .limit(1)
                .execute()
            )
            if not result.data:
                return self.settings.PLANT_STATE_DEFAULT
            row = result.data[0]
            if row.get("expires_at"):
                expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
                if expires < datetime.now(UTC):
                    return self.settings.PLANT_STATE_DEFAULT
            return row.get("state", self.settings.PLANT_STATE_DEFAULT)
        except Exception as exc:
            log.warning("event_bus.plant_state_lookup_failed", site_id=site_id, error=str(exc))
            return self.settings.PLANT_STATE_DEFAULT

    async def record_push(self, user_id: str, brief_id: str) -> int:
        """Records a governor push for `brief_id` in the sliding window sorted set.

        Each member is the brief_id (dedup within the window); score is the current
        Unix timestamp so `ZREMRANGEBYSCORE` can prune members older than 3600 s.

        B9a: replaces the `incr` / `expire` pipeline. The old `expire` reset the TTL
        on every push, so a user who pushed every 50 minutes reached ceiling ~6 after
        5 hours — a 1-hour window was effectively infinite. A sorted set gives a true
        sliding window: only pushes in the last 3600 s count.
        """
        count_key = self._governor_key(user_id)
        now_ts = datetime.now(UTC).timestamp()
        cutoff = now_ts - 3600
        pipe = self.redis.pipeline()
        pipe.zadd(count_key, {brief_id: now_ts}, nx=True)  # nx=True: record each brief once
        pipe.zremrangebyscore(count_key, "-inf", cutoff)
        pipe.zcard(count_key)
        # Keep the sorted set alive for 2 hours so an idle user's key cleans up.
        pipe.expire(count_key, 7200)
        results = await pipe.execute()
        new_count = results[2]  # zcard result
        log.info("governor.push_recorded", user_id=user_id, brief_id=brief_id, count=new_count)
        return new_count

    async def record_push_once(self, user_id: str, brief_id: str) -> bool:
        """
        Records a governor push for a brief at most once per rolling hour.

        B9a: the sorted set uses `zadd nx=True` internally, so a brief_id already in
        the window is not re-added. This method now just delegates to record_push and
        returns True if the count changed (i.e. the brief was new to the window).
        Returns True if this call counted a new push, False if already counted.
        """
        count_key = self._governor_key(user_id)
        # Check whether this brief is already in the window before adding.
        already = bool(await self.redis.zscore(count_key, brief_id))
        if not already:
            await self.record_push(user_id, brief_id)
        return not already

    async def get_governor_state(self, user_id: str) -> dict[str, Any]:
        count_key = self._governor_key(user_id)
        now_ts = datetime.now(UTC).timestamp()
        cutoff = now_ts - 3600
        # Prune old entries then count — same logic as check_governor and record_push.
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(count_key, "-inf", cutoff)
        pipe.zcard(count_key)
        _, current_count = await pipe.execute()

        ceiling = self.settings.MAX_PUSH_PER_USER_PER_HOUR
        suppressed = current_count >= ceiling
        # Remaining budget: how many more briefs may be delivered this hour.
        remaining = max(0, ceiling - current_count)
        return {
            "user_id": user_id,
            "push_count_last_hour": current_count,
            "ceiling": ceiling,
            "remaining_budget": remaining,
            "state": "suppressed" if suppressed else "normal",
        }

    # -------------------------------------------------------------------------
    # Deduplication (canonical event normalization)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Event Correlation — Compound Events (Layer 8)
    # -------------------------------------------------------------------------

    async def correlate_events(
        self,
        asset_id: str,
        event_id: str,
        occurred_at: datetime,
        supabase,
    ) -> str | None:
        """
        Groups events for the same asset within DEDUP_WINDOW_MINUTES into a compound event.
        Updates all correlated rows in operational_events with a shared compound_event_id.
        Returns the compound_event_id if correlation happened, else None.
        """
        window = timedelta(minutes=self.settings.DEDUP_WINDOW_MINUTES)
        window_start = (occurred_at - window).isoformat()
        window_end = (occurred_at + window).isoformat()

        result = await asyncio.to_thread(
            lambda: supabase.table("operational_events")
            .select("event_id, compound_event_id")
            .eq("asset_id", asset_id)
            .neq("event_id", str(event_id))
            .gte("occurred_at", window_start)
            .lte("occurred_at", window_end)
            .execute()
        )
        if not result.data:
            return None

        existing_compound_id = next(
            (r["compound_event_id"] for r in result.data if r.get("compound_event_id")),
            None,
        )
        compound_id = existing_compound_id or str(uuid.uuid4())

        all_ids = [r["event_id"] for r in result.data] + [str(event_id)]
        await asyncio.to_thread(
            lambda: supabase.table("operational_events")
            .update({"compound_event_id": compound_id})
            .in_("event_id", all_ids)
            .execute()
        )
        log.info("event_bus.compound_event_linked", compound_event_id=compound_id, event_ids=all_ids)

        # Layer 4 timestamp alignment. This is the right hook: a compound event is by definition
        # the same physical action reported by more than one source system, which is exactly the
        # comparison the architecture asks for. Report-only by default, and never allowed to
        # block correlation — a data-quality check must not drop operational events.
        try:
            from api.services.timestamp_alignment import TimestampAlignmentService

            await TimestampAlignmentService(supabase, self.settings).check_compound_event(
                compound_id, asset_id=asset_id
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("event_bus.timestamp_alignment_failed", error=str(exc))

        return compound_id

    def _dedup_key(self, asset_id: str, event_type: str, business_id: str | None) -> str:
        return f"kairos:dedup:{event_type}:{business_id or asset_id}"

    async def is_duplicate(
        self,
        asset_id: str,
        event_type: str,
        business_id: str | None = None,
    ) -> bool:
        """
        True if a semantically identical event finished ingesting inside the dedup window
        (DEDUP_WINDOW_MINUTES, default 10). Read-only: a caller records the event with `mark_seen`
        once it has succeeded.

        `business_id` (work_order_id, ptw_id) scopes the key when the event carries one. The
        architecture asks dedup to collapse "the same real-world event arriving from multiple
        source systems" — keying on (asset, type) alone instead collapses *two different permits
        on one asset* into one, and the second technician never receives a brief. On a turnaround,
        two permits for the same asset inside ten minutes is routine, not a duplicate.
        """
        return bool(await self.redis.exists(self._dedup_key(asset_id, event_type, business_id)))

    async def mark_seen(self, asset_id: str, event_type: str, business_id: str | None = None) -> None:
        """Records an event as ingested. Called last, so a failed ingest stays retryable: marking
        at check time turned a connector's retry after a 500 into "deduplicated" and lost the
        event, and with it a critical PTW brief.

        ponytail: two identical events racing inside one request's runtime can both run. The
        insert is idempotent on event_id and the brief cool-down absorbs the twin; a per-event
        lock is the upgrade if a duplicate critical brief ever matters.
        """
        ttl = self.settings.DEDUP_WINDOW_MINUTES * 60
        await self.redis.set(self._dedup_key(asset_id, event_type, business_id), "1", ex=ttl)
