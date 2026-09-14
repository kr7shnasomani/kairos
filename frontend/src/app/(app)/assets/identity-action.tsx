"use client";

import Link from "next/link";
import type { Role } from "@/lib/types";
import { useRole, ADMIN_ROLES } from "@/components/use-role";

const ACTION = "inline-flex h-9 items-center rounded-lg border border-line px-3.5 text-body font-semibold text-ink transition-colors hover:bg-surface-2";

/** Roles allowed to register assets — mirrors `POST /assets/` and `/assets/bulk`
 *  (`require_role("admin", "engineer")`). */
export const REGISTER_ROLES: Role[] = ["engineer", "admin"];

// Registering equipment and confirming a provisional identity are separate jobs on separate pages:
// /assets/register (engineer, admin) and /assets/bootstrap (admin). Each button is hidden for roles
// the API would refuse, so no one is offered an action they cannot perform.
export function RegisterAssetAction() {
  const role = useRole();
  if (!REGISTER_ROLES.includes(role)) return null;
  return <Link href="/assets/register" className={ACTION}>Register asset</Link>;
}

export function IdentityConfirmAction() {
  const role = useRole();
  if (!ADMIN_ROLES.includes(role)) return null;
  return <Link href="/assets/bootstrap" className={ACTION}>Identity confirmation</Link>;
}
