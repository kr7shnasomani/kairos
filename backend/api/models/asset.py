"""
Pydantic models — Asset (Layer 1: MDM Backbone)
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Asset(BaseModel):
    asset_id: str = Field(..., description="Canonical asset ID from EAM/ERP golden record")
    tag_number: str
    name: str
    equipment_class: str
    criticality: str = Field(..., description="safety_critical, critical, non_critical")
    site_id: str
    facility_id: str
    parent_asset_id: str | None = None
    status: str = Field(default="active", description="active, decommissioned, under_review")
    eam_source: str = Field(..., description="SAP_PM, Maximo, Infor_EAM, manual")
    identity_confirmed_by: str | None = None
    identity_confirmed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssetCreate(BaseModel):
    asset_id: str | None = Field(None, description="Canonical ID from EAM — auto-generated if not provided")
    tag_number: str
    name: str
    equipment_class: str
    criticality: str = Field(..., pattern="^(safety_critical|critical|non_critical)$")
    site_id: str
    facility_id: str
    parent_asset_id: str | None = None
    eam_source: str = "manual"
    confirmed_by_user_id: str = Field(..., min_length=1, description="Human authority confirming this identity — required, no AI-inferred identities")


class AssetImportRow(BaseModel):
    """One row of an EAM golden-record import.

    Deliberately has no `confirmed_by_user_id`, unlike `AssetCreate`. On a bulk import the
    confirming authority is the person uploading the record, taken from the verified token —
    asking them to repeat their own id on all 5,000 rows invites a caller to put someone
    else's id there. Layer 1's per-asset human bootstrap is for assets *missing* from the
    golden record; the golden record itself is a deterministic import.
    """

    asset_id: str | None = Field(None, description="Canonical ID from EAM — auto-generated if absent")
    tag_number: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    equipment_class: str = Field(..., min_length=1)
    criticality: str = Field(..., pattern="^(safety_critical|critical|non_critical)$")
    site_id: str = Field(..., min_length=1)
    facility_id: str = Field(..., min_length=1)
    parent_asset_id: str | None = None
    eam_source: str = Field(default="manual", description="SAP_PM, Maximo, Infor_EAM, manual")


class AssetBulkImport(BaseModel):
    """Layer 1 golden-record bootstrap: the bulk half of the MDM import.

    `max_length` is a guard, not a target — an import larger than this should be split, so a
    single failed request never costs a caller a whole plant's worth of work.
    """

    assets: list[AssetImportRow] = Field(..., min_length=1, max_length=5000)
