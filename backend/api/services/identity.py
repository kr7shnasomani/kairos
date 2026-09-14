"""Readable names for user ids stored on records (uploader, plant-state setter, reviewer)."""

import asyncio
import re

import structlog

log = structlog.get_logger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
# ponytail: process-lifetime cache — a user's display name effectively never changes mid-demo; restart
# the API to pick up a rename.
_name_cache: dict[str, str | None] = {}


async def display_names(supabase, user_ids) -> dict[str, str]:
    """`{user_id: name}` for the auth users among `user_ids`, for list views that show many rows.

    Only UUID-shaped ids are looked up: queues and logs also carry service names ("extraction_pipeline")
    and people named by a source system ("Suresh Yadav"), which already read correctly as they are.
    """
    names: dict[str, str] = {}
    for uid in {u for u in user_ids if u and _UUID_RE.match(u)}:
        if uid not in _name_cache:
            _name_cache[uid] = await display_name(supabase, uid)
        if _name_cache[uid]:
            names[uid] = _name_cache[uid]
    return names


async def display_name(supabase, user_id: str | None) -> str | None:
    """Auth user's `name` metadata, else email; `None` when the id is not an auth user.

    Loaders and connectors write non-UUID ids ("demo-loader", "eam-sync-service"), so a failed lookup
    is normal and must never fail the read that asked for it.
    """
    if not user_id:
        return None
    try:
        user = await asyncio.to_thread(lambda: supabase.auth.admin.get_user_by_id(user_id).user)
    except Exception:  # noqa: BLE001 — display nicety only
        return None
    meta = user.user_metadata or {}
    return meta.get("name") or user.email
