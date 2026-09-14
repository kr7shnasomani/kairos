"""Layer 8 delay compensation — ARCHITECTURE.md §Layer 8, third normalization operation.

The architecture asks for out-of-sequence events to be "buffered and reordered before being
committed to the trigger queue", with a configurable late-arrival window.

Kairos implements this by delaying the **derived output** rather than the source of record:
events are written to `operational_events` immediately, and brief assembly is deferred by
`LATE_ARRIVAL_WINDOW_MINUTES`. A later event for the same asset revokes the pending task and
re-enqueues, so the brief waits for stragglers; assembly then reads events back ordered by
`occurred_at`, which is where the reordering happens. Nothing is ever held in a buffer that
could lose it.

The load-bearing exemption is PTW. A uniform hold would deliver a safety brief *after* the
permit was issued, so PTW is immediate AND revokes any pending delayed brief for the asset —
one brief, carrying both events' context.

Source inspection. No stack, no secrets, no network.
"""

import inspect

from api.config import Settings
from api.routers import events as events_router

SOURCE = inspect.getsource(events_router)


def test_late_arrival_window_is_configurable():
    s = Settings()
    assert s.LATE_ARRIVAL_WINDOW_MINUTES > 0
    assert "LATE_ARRIVAL_WINDOW_MINUTES * 60" in SOURCE, (
        "brief assembly must be deferred by the configured late-arrival window"
    )


def test_brief_assembly_is_deferred_not_immediate():
    """The buffer. Without `countdown`, a brief is assembled from the first event alone and a
    correlated event arriving 10 s later has nothing to attach to."""
    assert "countdown=window_secs" in SOURCE


def test_a_later_event_revokes_the_pending_brief():
    """The reorder tolerance: re-enqueuing restarts the window so the brief captures both
    events, instead of emitting one brief per event."""
    assert "control.revoke(" in SOURCE
    assert "kairos:brief_pending:" in SOURCE


def test_ptw_is_exempt_from_the_hold_and_absorbs_the_pending_brief():
    """The safety-critical exemption. A held PTW brief is worse than no buffering at all —
    the permit would already be issued by the time the brief arrived."""
    ptw = SOURCE[SOURCE.index("PTW events always trigger"):]
    ptw = ptw[: ptw.index("@router.post", 10)] if "@router.post" in ptw[10:] else ptw
    assert "countdown" not in ptw, "PTW must not be delayed by the late-arrival window"
    assert "ptw_revoked_pending_brief" in ptw, (
        "PTW must revoke a pending delayed brief so one brief carries both events' context"
    )


def test_assembly_reads_events_ordered_by_occurred_at():
    """Where the actual reordering happens: arrival order does not matter because assembly
    reads the source of record back in `occurred_at` order."""
    from api.services import brief_engine

    assert '.order("occurred_at"' in inspect.getsource(brief_engine)
