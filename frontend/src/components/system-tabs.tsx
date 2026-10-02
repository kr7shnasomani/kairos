"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRole, ADMIN_VIEW_ROLES } from "./use-role";
import { cn } from "@/lib/utils";

/**
 * Shared sub-navigation for the system surfaces (Health, Settings), which were previously reachable
 * only as unrelated sidebar-footer links with no sense of belonging together.
 *
 * Admin-only tabs are hidden (not disabled) for non-admins — `routeAllowed` in
 * use-role.ts is still the enforcement point; this only avoids advertising a link that
 * would immediately redirect.
 */
const TABS: { href: string; label: string; adminOnly?: boolean }[] = [
  { href: "/system-health", label: "Health", adminOnly: true },
  { href: "/settings", label: "Settings" },
];

export function SystemTabs() {
  // usePathname() returns null when there is no router context (and in unit tests), so it
  // cannot be called directly — `null.startsWith` throws and takes the whole page with it.
  const pathname = usePathname() ?? "";
  const role = useRole();
  const isAdmin = ADMIN_VIEW_ROLES.includes(role);
  const tabs = TABS.filter((t) => !t.adminOnly || isAdmin);
  // A single tab is not navigation: non-admins only have Settings.
  if (tabs.length < 2) return null;

  return (
    <nav aria-label="System" className="mb-5 border-b border-line">
      <ul className="-mb-px flex gap-1 overflow-x-auto">
        {tabs.map((t) => {
          const active = pathname === t.href || pathname.startsWith(t.href + "/");
          return (
            <li key={t.href}>
              <Link
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-11 items-center whitespace-nowrap border-b-2 px-3 text-body transition-colors",
                  active
                    ? "border-accent font-medium text-ink"
                    : "border-transparent text-muted hover:border-line hover:text-ink"
                )}
              >
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
