"use client";

import { useEffect, useState } from "react";
import { getMe } from "@/lib/auth";
import type { Role, User } from "@/lib/types";

// Dev-bypass default: with no token the backend treats the caller as an engineer,
// so an unauthenticated demo session still sees engineer-level actions.
export function useRole(): Role {
  const [role, setRole] = useState<Role>("engineer");
  useEffect(() => {
    getMe().then((u) => {
      if (u?.role) setRole(u.role);
    });
  }, []);
  return role;
}

/** The full authenticated user. Needed where identity matters and not just role — e.g. a PTW
 *  countersignature must come from a *different* person than the one who acknowledged, so the
 *  UI has to compare user ids, not just check a role. Null until the fetch resolves. */
export function useMe(): User | null {
  const [me, setMe] = useState<User | null>(null);
  useEffect(() => {
    getMe().then(setMe);
  }, []);
  return me;
}

/** Roles allowed to promote a quarantine item. Matches OPA (`can_promote_quarantine`):
 *  reliability + admin only — engineers resolve conflicts but do not promote. */
export const PROMOTE_ROLES: Role[] = ["reliability", "admin"];
/** Roles allowed to resolve conflicts and deviation flags. */
export const RESOLVE_ROLES: Role[] = ["engineer", "reliability", "admin"];
/** Roles allowed to assert authority levels 1 to 3 at ingest. Matches `AUTHORITY_ASSERT_ROLES` in
 *  backend `routers/documents.py`; any other role is capped to level 4 server side. */
export const AUTHORITY_ASSERT_ROLES: Role[] = ["reliability", "admin"];
/** Roles with admin-level access (model gate, plant state, MDM bootstrap). */
export const ADMIN_ROLES: Role[] = ["admin"];
/** Field worker personas — mobile-first, read-only on staff surfaces. */
export const FIELD_ROLES: Role[] = ["field_worker"];

/** Read-only roles: the public demo identity. Every write control is gated by an allow list that
 *  omits these roles, so they see none; this list only drives the "read-only demo" indicator. */
export const READ_ONLY_ROLES: Role[] = ["demo"];

/** Staff surfaces (engineers, reliability, admin) — field workers are excluded. */
const STAFF_ONLY: Role[] = ["engineer", "reliability", "admin"];

/** Staff plus the read-only compliance auditor. Used for the two surfaces OPA grants it
 *  (`read_compliance`, `read_audit`). Compliance is deliberately NOT in STAFF_ONLY: it must not
 *  reach governance, events, RCA, graph, documents, projects or off-boarding. */
const STAFF_AND_COMPLIANCE: Role[] = [...STAFF_ONLY, "compliance"];

// Path-prefix access rules. First match wins; unlisted paths (e.g. /briefs, /copilot,
// /assets, /field, /settings) are open to any authenticated role. Enforced centrally in
// the app shell so no page can be reached by URL without the right role.
const ROUTE_ACCESS: ReadonlyArray<{ prefix: string; roles: Role[] }> = [
  { prefix: "/system-health", roles: ADMIN_ROLES },
  { prefix: "/management", roles: STAFF_ONLY },
  { prefix: "/events", roles: STAFF_ONLY },
  { prefix: "/rca", roles: STAFF_ONLY },
  { prefix: "/graph", roles: STAFF_ONLY },
  { prefix: "/compliance", roles: STAFF_AND_COMPLIANCE },
  { prefix: "/governance", roles: STAFF_ONLY },
  { prefix: "/audit", roles: STAFF_AND_COMPLIANCE },
  { prefix: "/documents", roles: STAFF_ONLY },
  { prefix: "/projects", roles: STAFF_ONLY },
  { prefix: "/offboarding", roles: STAFF_ONLY },
];

// The `demo` role is deny-by-default here too: it may open only these roots (the Copilot and
// read-only views of the data the policy grants it), minus the pages that exist to write.
// Mirrors the `demo` allow list in infra/policies/kairos.rego.
const DEMO_ROUTES = ["/copilot", "/briefs", "/assets", "/documents", "/compliance", "/graph", "/settings"];
const DEMO_BLOCKED = ["/assets/register", "/assets/bootstrap", "/documents/ingest"];

const under = (path: string, prefix: string) => path === prefix || path.startsWith(prefix + "/");

/** Is `role` allowed to view `path`? Unlisted paths are open to all authenticated roles, except
 *  for `demo`, which gets only DEMO_ROUTES. */
export function routeAllowed(path: string, role: Role): boolean {
  if (role === "demo") {
    return DEMO_ROUTES.some((p) => under(path, p)) && !DEMO_BLOCKED.some((p) => under(path, p));
  }
  const rule = ROUTE_ACCESS.find((r) => path === r.prefix || path.startsWith(r.prefix + "/"));
  return !rule || rule.roles.includes(role);
}

/** The landing surface for a role — where an unauthorized redirect sends them.
 *  Must be a route the role can actually view, or the shell's guard bounces them straight
 *  back and the user redirect-loops: `/management` is STAFF_ONLY, so compliance needs its own
 *  home rather than the default. */
export function roleHome(role: Role): string {
  if (role === "field_worker") return "/briefs";
  if (role === "compliance") return "/compliance";
  if (role === "demo") return "/copilot";
  return "/management";
}
