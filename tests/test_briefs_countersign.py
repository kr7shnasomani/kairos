"""
PTW dual sign-off (Layer 8, architecture Flow B) — pure logic, no network, no Supabase.

Guards the bug this endpoint was written to fix: `ack` deliberately withholds
`acknowledged_at` for PTW briefs, so without a working countersign path a
safety-critical brief could never reach acknowledged state at all.
"""

import pytest
from fastapi import HTTPException

from api.routers.briefs import countersign_brief

ENGINEER = {"user_id": "eng-1", "role": "engineer", "site_id": "SITE_001"}
RELIABILITY = {"user_id": "rel-1", "role": "reliability", "site_id": "SITE_001"}


class _Query:
    """Chainable stand-in for the supabase-py query builder."""

    def __init__(self, table: str, rows: list[dict], sink: dict, lost_race: bool = False):
        self._table, self._rows, self._sink, self._lost_race = table, rows, sink, lost_race
        self._updating = False

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a):
        return self

    def in_(self, *_a):
        return self

    def is_(self, *_a):
        return self

    def limit(self, _n):
        return self

    def update(self, payload):
        self._sink.setdefault("updates", []).append((self._table, payload))
        self._updating = True
        return self

    def insert(self, payload):
        self._sink.setdefault("inserts", []).append((self._table, payload))
        return self

    def execute(self):
        # `lost_race`: another signer's conditional update landed first, so this one matches no row.
        rows = [] if (self._updating and self._lost_race) else self._rows
        return type("Result", (), {"data": rows})()


class FakeSupabase:
    def __init__(self, brief_row: dict | None, lost_race: bool = False):
        self._brief_row, self._lost_race = brief_row, lost_race
        self.sink: dict = {}

    def table(self, name: str):
        rows = [self._brief_row] if (name == "briefs" and self._brief_row) else []
        return _Query(name, rows, self.sink, self._lost_race)


def _brief(**overrides) -> dict:
    row = {
        "brief_id": "b-1",
        "requires_countersignature": True,
        "acknowledged_by": ENGINEER["user_id"],
        "acknowledged_at": None,
        "countersigned_by": None,
    }
    row.update(overrides)
    return row


async def test_second_authority_completes_the_signature():
    sb = FakeSupabase(_brief())
    result = await countersign_brief("b-1", sb, RELIABILITY)

    assert result["status"] == "acknowledged"
    assert result["countersigned_by"] == RELIABILITY["user_id"]
    assert result["acknowledged_by"] == ENGINEER["user_id"]

    # acknowledged_at is set HERE, not at ack time — that is the whole fix.
    table, payload = sb.sink["updates"][0]
    assert table == "briefs"
    assert payload["acknowledged_at"] is not None
    assert payload["countersigned_at"] is not None

    audit_table, audit = sb.sink["inserts"][0]
    assert audit_table == "audit_log"
    assert audit["action"] == "brief_countersigned"


async def test_acknowledger_cannot_countersign_their_own_brief():
    """Two distinct humans is the point of Flow B; one user cannot supply both."""
    sb = FakeSupabase(_brief(acknowledged_by=RELIABILITY["user_id"]))
    with pytest.raises(HTTPException) as exc:
        await countersign_brief("b-1", sb, RELIABILITY)
    assert exc.value.status_code == 403
    assert "updates" not in sb.sink


async def test_cannot_countersign_before_acknowledgement():
    sb = FakeSupabase(_brief(acknowledged_by=None))
    with pytest.raises(HTTPException) as exc:
        await countersign_brief("b-1", sb, RELIABILITY)
    assert exc.value.status_code == 409
    assert "updates" not in sb.sink


async def test_countersigning_twice_is_rejected():
    sb = FakeSupabase(_brief(countersigned_by="rel-2"))
    with pytest.raises(HTTPException) as exc:
        await countersign_brief("b-1", sb, RELIABILITY)
    assert exc.value.status_code == 409


async def test_a_concurrent_countersign_that_lost_the_race_is_409_and_unsigned():
    sb = FakeSupabase(_brief(), lost_race=True)
    with pytest.raises(HTTPException) as exc:
        await countersign_brief("b-1", sb, RELIABILITY)
    assert exc.value.status_code == 409
    assert "inserts" not in sb.sink  # no signed audit row for the loser


async def test_a_concurrent_ack_that_lost_the_race_is_409_and_unsigned():
    from api.routers.briefs import ack_brief

    sb = FakeSupabase(_brief(acknowledged_by=None), lost_race=True)
    with pytest.raises(HTTPException) as exc:
        await ack_brief("b-1", ENGINEER, sb)
    assert exc.value.status_code == 409
    assert "inserts" not in sb.sink


async def test_non_ptw_brief_has_nothing_to_countersign():
    sb = FakeSupabase(_brief(requires_countersignature=False))
    with pytest.raises(HTTPException) as exc:
        await countersign_brief("b-1", sb, RELIABILITY)
    assert exc.value.status_code == 400


async def test_unknown_brief_is_404():
    sb = FakeSupabase(None)
    with pytest.raises(HTTPException) as exc:
        await countersign_brief("nope", sb, RELIABILITY)
    assert exc.value.status_code == 404


async def test_countersigner_is_not_the_recipient_and_must_still_succeed():
    """
    Regression, found only by running the flow against a real database.

    `countersign_brief` originally scoped its read with
    `.in_("recipient_user_id", _brief_recipients(current_user))`, copying `ack`. But Flow B's
    countersigner is *by definition* someone other than the person the brief was delivered to —
    so that filter matched nothing and every real countersign returned 404. The whole feature was
    unreachable in production while these tests passed, because the fake's `.in_()` is a
    passthrough and cannot reproduce a filter whose bug is its filtering.

    Authorisation is by role, not by delivery address.
    """
    sb = FakeSupabase(_brief(acknowledged_by=ENGINEER["user_id"]))
    # Recipient is a third party entirely — neither signer.
    sb._brief_row["recipient_user_id"] = "Rohit Menon"

    result = await countersign_brief("b-1", sb, RELIABILITY)

    assert result["status"] == "acknowledged"
    assert result["countersigned_by"] == RELIABILITY["user_id"]
