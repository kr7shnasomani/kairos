"""RCA timeline assembly — one entry per event, on one clock."""

from datetime import UTC, datetime
from typing import Any

_EPOCH = datetime.min.replace(tzinfo=UTC)


def as_utc(value: Any) -> datetime | None:
    """Parse an event timestamp as an aware UTC datetime. A naive value is taken to be UTC."""
    if not value:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def merge_timeline(*sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge event lists from several stores into one chronological timeline.

    The same work order is recorded in Supabase `operational_events` and as a Neo4j `Event` node, so
    concatenating the two drew every event twice. The copies also disagreed on the clock — one
    `+00:00`, one `+05:30` or naive — and a string sort mixed them out of order. Entries sharing an
    `event_id` collapse into the first source's copy, which gains any description or document the
    later copy carries. Pass the richer store first.
    """
    merged: dict[str, dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []
    for events in sources:
        for event in events:
            at = as_utc(event.get("occurred_at"))
            item = {**event, "occurred_at": at.isoformat() if at else (event.get("occurred_at") or "")}
            key = item.get("event_id")
            if not key:
                unkeyed.append(item)
            elif key not in merged:
                merged[key] = item
            else:
                kept = merged[key]
                for field in ("description", "document_id"):
                    if not kept.get(field) and item.get(field):
                        kept[field] = item[field]
    timeline = [*merged.values(), *unkeyed]
    timeline.sort(key=lambda e: as_utc(e.get("occurred_at")) or _EPOCH)
    return timeline
