"""
Pydantic models — Events (Layer 8: Operational Event Subscription)
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


def _gen_event_id() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=_gen_event_id)
    source_system: str = Field(..., description="SAP_PM, Maximo, DCS, PTW_system, manual")
    site_id: str
    occurred_at: datetime = Field(default_factory=_utc_now)
    received_at: datetime = Field(default_factory=_utc_now)

    @field_validator("occurred_at", "received_at")
    @classmethod
    def _assume_utc(cls, value: datetime) -> datetime:
        # A naive timestamp was stored as-is in the Event node while Postgres read it as UTC, so the
        # RCA timeline showed one work order at two different times. Naive input is UTC by contract.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class WorkOrderEvent(BaseEvent):
    work_order_id: str
    asset_id: str
    failure_code: str
    description: str
    assigned_technician_id: str | None = None
    priority: str = Field(default="normal", description="critical, high, normal, low")
    planned_start: datetime | None = None
    close_notes: str | None = None  # CMMS work order closeout notes — used by attribution worker
    event_type: str = "work_order_created"


class PTWEvent(BaseEvent):
    ptw_id: str
    work_area: str
    asset_ids: list[str] = Field(..., description="All assets within the isolation boundary")
    ptw_type: str = Field(..., description="isolation, hot_work, confined_space, high_pressure_line")
    issuing_engineer_id: str
    event_type: str = "ptw_generated"


class ShiftHandoverEvent(BaseEvent):
    outgoing_shift_lead_id: str
    incoming_shift_lead_id: str
    handover_time: datetime
    event_type: str = "shift_handover"


class AlarmEvent(BaseEvent):
    alarm_id: str
    asset_id: str
    alarm_tag: str
    alarm_description: str
    severity: str = Field(..., description="critical, high, medium, low")
    acknowledged_by: str
    event_type: str = "alarm_acknowledged"


class EventAck(BaseModel):
    user_id: str
    role: str
    acknowledged_at: datetime = Field(default_factory=_utc_now)
    signature: str | None = None  # Cryptographic signature for audit trail
    notes: str | None = None


class DeviationFlagEvent(BaseModel):
    asset_id: str
    description: str
    reported_by: str | None = None
    affected_topology_path: str | None = None


class DeviationFlagResolveRequest(BaseModel):
    resolution: str = Field(..., description="'promoted' or 'disputed'")
    moc_warranted: bool = False
    notes: str | None = None


class PlantStateEvent(BaseModel):
    site_id: str
    state: str = Field(..., description="normal, turnaround, shutdown, emergency")
    expires_at: datetime | None = None


class TagOutEvent(BaseEvent):
    asset_id: str
    tag_out_reason: str
    performed_by: str
    expected_return_date: datetime | None = None
    event_type: str = "equipment_tag_out"


class InspectionCompleteEvent(BaseEvent):
    asset_id: str
    inspection_type: str
    result: str = Field(..., description="passed, failed, conditional")
    performed_by: str
    findings: str = ""
    document_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    event_type: str = "inspection_complete"
