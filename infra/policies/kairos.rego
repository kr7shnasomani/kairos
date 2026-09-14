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
# admin          — full access
# compliance     — read-only access to compliance cockpit, non-conformance and audit trail
#
# The read_* grants mirror the frontend route table (`components/use-role.ts`) — each role holds
# exactly the actions its permitted routes actually call. Keep the two in step: a route that a
# role can open but whose API calls it cannot make is a broken page, not a closed boundary.
#
# read_nonconformance is narrower than read_governance on purpose: /compliance/nonconformance
# reads conflicts + quarantine, so the compliance auditor needs those two /governance children
# without reaching the model gate, MoC approvals or the circuit breaker.
# =============================================================================

roles := {
    "field_worker":  {"read_search", "read_briefs", "ack_brief"},
    "engineer":      {"read_search", "read_briefs", "ack_brief", "ingest_document", "read_governance", "read_nonconformance", "read_compliance", "read_audit", "read_documents", "read_events", "resolve_admin_conflict", "read_assets", "write_assets"},
    "reliability":   {"read_search", "read_briefs", "ingest_document", "read_governance", "read_nonconformance", "read_compliance", "read_audit", "read_documents", "read_events", "promote_quarantine", "countersign_brief", "resolve_admin_conflict", "read_assets"},
    "compliance":    {"read_search", "read_compliance", "read_audit", "read_nonconformance", "read_events"},
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
# The three `read_*` actions MUST stay in this set. They are granted per-role in the table
# above, and the catch-all would otherwise hand every one of them to every authenticated role —
# which is the same hole as not enforcing reads at all.
# =============================================================================

_sensitive_actions := {
    "promote_quarantine", "countersign_brief", "resolve_admin_conflict", "write_assets",
    "ingest_document", "read_audit", "read_compliance", "read_governance",
    "read_nonconformance", "read_documents", "read_events",
}

allow if {
    input.user.role in {"field_worker", "engineer", "reliability", "admin", "compliance"}
    not input.action in _sensitive_actions
}
