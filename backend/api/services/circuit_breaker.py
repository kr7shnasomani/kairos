"""
Circuit Breaker Service — Layer 7: SPC-Based Extraction Gate.
Z-score test on the latest 7-day override count vs. a baseline of the three weeks before it.
Halts graph writes for an asset_class when z_score > 2.0.
"""

import asyncio
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_WEEKS = 4  # week 0 is the current 7 days, weeks 1 to 3 are the baseline
_FLAT_BASELINE_STD = 1.0


def _weekly_counts(timestamps: list[str], now: datetime) -> list[int]:
    """Count timestamps into `_WEEKS` strict 7-day windows, window 0 being the latest 7 days.

    Anything older than `_WEEKS * 7` days is dropped rather than folded into the last window
    (that made the oldest bucket 9 days wide). A future timestamp counts as the current week.
    """
    counts = [0] * _WEEKS
    for ts in timestamps:
        days_ago = (now - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() / 86400
        week = max(int(days_ago // 7), 0)
        if week < _WEEKS:
            counts[week] += 1
    return counts


class CircuitBreakerService:
    def __init__(self, supabase) -> None:
        self.supabase = supabase

    async def model_gate_block(self, asset_class: str) -> bool:
        """
        Whether the most recent Layer 0 model gate blocked this asset class.

        Enforcement deliberately routes through the circuit breaker rather than a parallel gate:
        the breaker is already the thing that halts extraction per asset class and is already
        consulted by the extraction path, so a second mechanism would mean two places to check and
        two ways to disagree. The gate only ever publishes `blocked_asset_classes` when
        `MODEL_GATE_ENFORCE` is on, so this is inert by default.
        """
        try:
            result = await asyncio.to_thread(
                lambda: self.supabase.table("audit_log")
                .select("details")
                .eq("action", "model_gate_result")
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — a reporting lookup must not break extraction
            log.warning("circuit_breaker.model_gate_lookup_failed", error=str(exc))
            return False
        if not result.data:
            return False
        blocked = (result.data[0].get("details") or {}).get("blocked_asset_classes") or []
        return asset_class in blocked

    async def check(self, asset_class: str) -> dict[str, Any]:
        """
        Halt decision for an asset class — two independent inputs, one mechanism.

        1. SPC: rolling Z-score over human override rates (drift during production operation).
        2. Layer 0 model gate: a model that regressed on this class at its deployment gate.

        The architecture wants both contained the same way — route new inputs of that class to
        human-only processing until the model is retrained and passes validation.
        """
        if await self.model_gate_block(asset_class):
            log.warning("circuit_breaker.halted_by_model_gate", asset_class=asset_class)
            return {
                "halted": True,
                "z_score": 0.0,
                "reason": "model_gate_regression",
                "override_count_7d": 0,
            }

        now = datetime.now(UTC)
        window_start = (now - timedelta(days=_WEEKS * 7)).isoformat()

        all_rows = await asyncio.to_thread(
            lambda: self.supabase.table("extraction_overrides")
            .select("created_at")
            .eq("asset_class", asset_class)
            .gte("created_at", window_start)
            .execute()
        )
        week_counts = _weekly_counts([r["created_at"] for r in (all_rows.data or [])], now)
        current_7d = week_counts[0]
        historical = week_counts[1:]  # the older weeks are the baseline; week 0 is the test value

        if all(c == 0 for c in historical):
            return {
                "halted": False,
                "z_score": 0.0,
                "reason": "insufficient_history",
                "override_count_7d": current_7d,
            }

        mean = statistics.mean(historical)
        # A flat baseline (e.g. [1, 1, 1]) has std 0, which made every z-score 0 and the breaker
        # unable to trip however many overrides arrived. Floor it at one override per week, so a
        # flat baseline halts when the week exceeds mean + 2 (z > 2 at unit std). One per week is
        # the smallest spread a count series can show; a smaller k would halt on ordinary noise.
        std = statistics.stdev(historical) or _FLAT_BASELINE_STD
        z_score = (current_7d - mean) / std
        halted = z_score > 2.0

        if halted:
            log.warning(
                "circuit_breaker.halted",
                asset_class=asset_class,
                z_score=z_score,
                current_7d=current_7d,
                mean=mean,
            )

        return {
            "halted": halted,
            "z_score": round(z_score, 3),
            "reason": "z_score_exceeded" if halted else "within_normal_range",
            "override_count_7d": current_7d,
        }

    async def record_override(
        self,
        asset_class: str,
        document_id: str | None,
        override_type: str,
    ) -> None:
        """Insert an extraction_overrides row for SPC tracking."""
        await asyncio.to_thread(
            lambda: self.supabase.table("extraction_overrides").insert({
                "asset_class": asset_class,
                "document_id": document_id,
                "override_type": override_type,
            }).execute()
        )
        log.info(
            "circuit_breaker.override_recorded",
            asset_class=asset_class,
            override_type=override_type,
        )

    async def get_all_states(self) -> list[dict[str, Any]]:
        """Returns current CB state per distinct asset_class that has override records."""
        result = await asyncio.to_thread(
            lambda: self.supabase.table("extraction_overrides")
            .select("asset_class")
            .execute()
        )
        classes = list({r["asset_class"] for r in (result.data or [])})
        states = []
        for ac in sorted(classes):
            state = await self.check(ac)
            state["asset_class"] = ac
            states.append(state)
        return states
