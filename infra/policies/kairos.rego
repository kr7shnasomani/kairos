package kairos.authz

import rego.v1

# =============================================================================
# Kairos — Open Policy Agent Governance Rules
# Enforces: RBAC, authority hierarchy, asset-level access control
# =============================================================================

# Default deny
default allow := false

# =============================================================================
# Role definitions
# field_worker   — read access to briefs and search; cannot access governance
# engineer       — full read + governance operations; cannot modify MDM without authority
# reliability    — can promote quarantine items, resolve admin conflicts
# admin          — full access (the Go connector's internal key resolves to admin)
# compliance     — read-only access to compliance cockpit, non-conformance and audit trail
# demo           — the public one-click demo identity: sees everything an admin sees (every read_*
#                  action, including audit, governance and events) and works the showcase plant.
#                  It holds the write actions below, but policy is only the coarse layer: the API
#                  refuses a demo write that is not on a route in `tenant.DEMO_WRITE_ALLOWED`
#                  (`dependencies.demo_write_fence`), and each of those handlers refuses a target that
#                  is not a showcase row (`services/tenant.py` guard_*). The cloud stores have no
#                  backup, so real data is protected by those guards, not by this table alone, and a
#                  test fails when an allowed route has no guard. Admin-only routes (the model gate,
#                  provider probes) stay closed to it: it satisfies a role gate that names engineer
#                  or reliability, never one that names only admin.
#
# The read_* grants mirror the frontend route table (`components/use-role.ts`) — each role holds
# exactly the actions its permitted routes actually call. Keep the two in step: a route that a
# role can open but whose API calls it cannot make is a broken page, not a closed boundary.
#
# ingest_event gates the operational-event feed (work orders, permits, alarms, tag-outs, shift
# handovers, inspections). Those routes create critical-priority briefs and compliance evidence, so
# they belong to staff and the connector, not to field_worker or compliance. Field-worker event
# flows (deviation flags, acknowledgements) stay on write_api.
#
# read_nonconformance is narrower than read_governance on purpose: /compliance/nonconformance
# reads conflicts + quarantine, so the compliance auditor needs those two /governance children
# without reaching the model gate, MoC approvals or the circuit breaker.
# =============================================================================

roles := {
    "field_worker":  {"read_search", "read_briefs", "ack_brief"},
    "engineer":      {"read_search", "read_briefs", "ack_brief", "ingest_document", "ingest_event", "read_governance", "read_nonconformance", "read_compliance", "read_audit", "read_documents", "read_events", "resolve_admin_conflict", "read_assets", "write_assets"},
    "reliability":   {"read_search", "read_briefs", "ingest_document", "ingest_event", "read_governance", "read_nonconformance", "read_compliance", "read_audit", "read_documents", "read_events", "promote_quarantine", "countersign_brief", "resolve_admin_conflict", "read_assets"},
    "compliance":    {"read_search", "read_compliance", "read_audit", "read_nonconformance", "read_events"},
    "demo":          {"read_search", "read_briefs", "read_assets", "read_documents", "read_events", "read_compliance", "read_nonconformance", "read_audit", "read_governance", "read_other", "synthesize", "rca_pack", "answer_feedback", "write_api", "ingest_document", "ingest_event", "write_assets", "promote_quarantine", "resolve_admin_conflict"},
    "admin":         {"*"},
}

user_role := input.user.role

user_permissions := roles[user_role]

allow if {
    user_permissions[_] == "*"
}

allow if {
    user_permissions[_] == input.action
}

# =============================================================================
# Authority hierarchy enforcement
# Level 1 (Regulatory) cannot be overridden by Level 4-5 sources
# =============================================================================

valid_authority_override if {
    input.action == "create_knowledge_edge"
    input.new_authority_level <= input.existing_authority_level
}

valid_authority_override if {
    input.action == "create_knowledge_edge"
    input.user.role == "admin"
}

# =============================================================================
# Asset-level access control (site isolation)
# Users can only access assets from their assigned site(s)
# =============================================================================

asset_accessible if {
    input.asset.site_id == input.user.site_id
}

asset_accessible if {
    input.user.role == "admin"
}

asset_accessible if {
    input.user.role == "reliability"
    input.asset.site_id == input.user.site_id
}

# =============================================================================
# MoC resolution — only engineering authority can approve
# =============================================================================

can_resolve_moc if {
    input.action == "resolve_moc"
    input.user.role in {"engineer", "admin"}
}

# =============================================================================
# Quarantine promotion — requires reliability or admin role
# =============================================================================

can_promote_quarantine if {
    input.action == "promote_quarantine"
    input.user.role in {"reliability", "admin"}
}

# =============================================================================
# PTW brief countersignature — the second of two required signatures.
# Architecture Flow B: the issuing engineer acknowledges, a second authority
# countersigns. Engineers deliberately cannot countersign, so the two signatures
# cannot both come from the issuing role.
# =============================================================================

can_countersign_brief if {
    input.action == "countersign_brief"
    input.user.role in {"reliability", "admin"}
}

# =============================================================================
# Catch-all: non-sensitive writes allowed for any authenticated role.
# Sensitive actions are blocked above for insufficient roles; everything else
# (events, briefs, search, compliance reads via POST) passes through.
#
# Every `read_*` action and `ingest_event` MUST stay in this set. They are granted per-role in the table
# above, and the catch-all would otherwise hand every one of them to every authenticated role —
# which is the same hole as not enforcing reads at all.
#
# `synthesize`, `rca_pack` and `answer_feedback` stay OUT of the set on purpose: the five staff roles
# keep them through this catch-all, and demo gets them only by name in the table.
# =============================================================================

_sensitive_actions := {
    "promote_quarantine", "countersign_brief", "resolve_admin_conflict", "write_assets",
    "ingest_document", "ingest_event", "read_audit", "read_compliance", "read_governance",
    "read_nonconformance", "read_documents", "read_events",
    # Asked only for the demo role (see middleware/opa.py `_DEMO_READ_ACTION_MAP`), granted to it
    # by name. In the set so a future enforcement for every role cannot hand them out by default.
    "read_search", "read_briefs", "read_assets", "read_other",
}

allow if {
    input.user.role in {"field_worker", "engineer", "reliability", "admin", "compliance"}
    not input.action in _sensitive_actions
}
