"use client";

import Link from "next/link";
import type { Role } from "@/lib/types";
import { useRole } from "@/components/use-role";

const ACTION = "inline-flex h-9 items-center rounded-lg border border-line px-3.5 text-body font-semibold text-ink transition-colors hover:bg-surface-2";

/** Roles allowed to write asset master data — registering an asset and confirming a provisional
 *  identity or alias. Mirrors the API exactly: `POST /assets/`, `/assets/bulk` and the alias
 *  confirm/reject endpoints are all `require_role("admin", "engineer")`, and OPA grants
 *  `write_assets` to both. */
export const MDM_ROLES: Role[] = ["engineer", "admin"];

// Registering equipment and confirming a provisional identity are separate jobs on separate pages:
// /assets/register and /assets/bootstrap. Each button is hidden for roles the API would refuse, so
// no one is offered an action they cannot perform.
export function RegisterAssetAction() {
  const role = useRole();
  if (!MDM_ROLES.includes(role)) return null;
  return <Link href="/assets/register" className={ACTION}>Register asset</Link>;
}

export function IdentityConfirmAction() {
  const role = useRole();
  if (!MDM_ROLES.includes(role)) return null;
  return <Link href="/assets/bootstrap" className={ACTION}>Identity confirmation</Link>;
}
