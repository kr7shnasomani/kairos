"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { BrandLink } from "./brand-link";
import { AppHeader } from "./app-header";
import { MobileAppHeader } from "./mobile-app-header";
import { CommandPalette, ShortcutsHelp, type PaletteItem } from "./command-palette";
import { getMe, logout } from "@/lib/auth";
import { getToken, getGovernorState, getPlantState, isStrictAuth } from "@/lib/api";
import { flushQueue } from "@/lib/idb";
import { getUserInitials } from "@/lib/user-initials";
import { ADMIN_ROLES, routeAllowed, roleHome } from "./use-role";
import type { Role, User, GovernorEventState, PlantState } from "@/lib/types";
import { capitalize, cn } from "@/lib/utils";
import { ThemeToggle } from "./theme-toggle";
import { PageSkeleton } from "./skeleton";
import { Modal } from "./ui";

// Staff surfaces (Assure group + RCA) are hidden from field workers. Dev-bypass (no session)
// defaults to engineer, so an unauthenticated demo still sees everything.
const STAFF: Role[] = ["engineer", "reliability", "admin"];
/** Staff plus the read-only compliance auditor — mirrors STAFF_AND_COMPLIANCE in use-role.ts. */
const STAFF_AND_COMPLIANCE: Role[] = [...STAFF, "compliance"];

type IconName =
  | "briefs" | "copilot" | "assets" | "rca" | "compliance"
  | "management" | "governance" | "documents" | "search" | "menu" | "close" | "graph" | "audit"
  | "events" | "offboarding" | "projects" | "voice" | "chevron" | "settings" | "health" | "info" | "alert"
  | "chart";

function Icon({ name, className = "size-[18px]" }: { name: IconName; className?: string }) {
  const paths: Record<IconName, React.ReactNode> = {
    briefs: <path d="M4 6h16M4 12h16M4 18h10" />,
    copilot: <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />,
    assets: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></>,
    rca: <path d="M22 12h-4l-3 9L9 3l-3 9H2" />,
    compliance: <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />,
    management: <><path d="M3 3v16a2 2 0 0 0 2 2h16" /><path d="M18 17V9M13 17V5M8 17v-3" /></>,
    governance: <><path d="M12 3v18M7 21h10" /><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" /><path d="m5 7-3 8c.87.65 1.92 1 3 1s2.13-.35 3-1L5 7zM19 7l-3 8c.87.65 1.92 1 3 1s2.13-.35 3-1l-3-8z" /></>,
    documents: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="M6 6l12 12M18 6L6 18" />,
    graph: <><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="m8.59 13.51 6.83 3.98M15.41 6.51l-6.82 3.98" /></>,
    audit: <><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="M12 11h4M12 16h4M8 11h.01M8 16h.01" /></>,
    events: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></>,
    offboarding: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="m17 8 5 5m0-5-5 5" /></>,
    projects: <><path d="M3 7l9-4 9 4-9 4-9-4z" /><path d="M3 12l9 4 9-4M3 17l9 4 9-4" /></>,
    voice: <><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><path d="M12 19v4M8 23h8" /></>,
    chevron: <path d="M9 6l6 6-6 6" />,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /></>,
    health: <path d="M22 12h-4l-3 9L9 3l-3 9H2" />,
    info: <><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></>,
    alert: <><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
    chart: <><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></>,
  };
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

type NavItem = { href: string; label: string; icon: IconName; roles?: Role[] };

// group: "" renders ungrouped at the top (no header, no collapse).
const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "",
    items: [{ href: "/management", label: "Overview", icon: "management", roles: STAFF }],
  },
  {
    group: "Operate",
    items: [
      { href: "/briefs", label: "Briefs", icon: "briefs" },
      { href: "/copilot", label: "Copilot", icon: "copilot" },
      { href: "/assets", label: "Assets", icon: "assets" },
      { href: "/events", label: "Events", icon: "events", roles: STAFF },
      { href: "/field/voice", label: "Voice", icon: "voice", roles: ["field_worker", "admin"] },
      { href: "/field/deviation", label: "Deviation", icon: "alert", roles: ["field_worker", "admin"] },
    ],
  },
  {
    group: "Analyze",
    items: [
      { href: "/rca", label: "RCA", icon: "rca", roles: STAFF },
      { href: "/graph", label: "Graph", icon: "graph", roles: STAFF },
      { href: "/management/coverage", label: "Coverage", icon: "chart", roles: STAFF },
    ],
  },
  {
    group: "Assure",
    items: [
      // The compliance auditor sees exactly these two and nothing else in the sidebar —
      // matching `read_compliance` / `read_audit` in kairos.rego and ROUTE_ACCESS.
      { href: "/compliance", label: "Compliance", icon: "compliance", roles: STAFF_AND_COMPLIANCE },
      { href: "/governance", label: "Governance", icon: "governance", roles: STAFF },
      { href: "/audit", label: "Audit Trail", icon: "audit", roles: STAFF_AND_COMPLIANCE },
    ],
  },
  {
    group: "Knowledge",
    items: [
      { href: "/documents", label: "Documents", icon: "documents", roles: STAFF },
      { href: "/projects", label: "Projects", icon: "projects", roles: STAFF },
      { href: "/offboarding", label: "Off-Boarding", icon: "offboarding", roles: STAFF },
    ],
  },
];

function GovernorPill({ userId }: { userId: string }) {
  const [gov, setGov] = useState<GovernorEventState | null>(null);
  useEffect(() => {
    let alive = true;
    getGovernorState(userId).then((r) => { if (alive && r.data) setGov(r.data); });
    return () => { alive = false; };
  }, [userId]);
  if (!gov) return null;
  const suppressed = gov.state === "suppressed";
  return (
    <div
      title={`Governor: ${gov.push_count_last_hour}/${gov.ceiling} briefs/hr`}
      className={cn(
        "rail-link mx-3 my-1 flex items-center justify-between rounded-lg px-2.5 py-1.5 text-label",
        suppressed
          ? "bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] text-danger"
          : "bg-surface-2 text-muted",
      )}
    >
      {/* Collapsed the wording goes, the count stays — the ratio is the signal,
          and `title` above still carries the full sentence. */}
      <span className="rail-label font-semibold">{suppressed ? "Governor · suppressed" : "Governor · active"}</span>
      <span className="tabular font-medium">{gov.push_count_last_hour}/{gov.ceiling}</span>
    </div>
  );
}

/** Rail collapse (review item 2). `<html data-nav>` is the single source of truth,
 *  set before paint in layout.tsx so a collapsed rail never flashes wide. React
 *  only *observes* it — the width itself is pure CSS.
 *
 *  useSyncExternalStore rather than useState+useEffect: the attribute is external
 *  state, and the server snapshot lets React render `false` on the server without
 *  a hydration mismatch. The effect version had to setState synchronously on mount
 *  to catch up, which is a cascading render (react-hooks/set-state-in-effect) and
 *  briefly rendered the wrong label. */
const subscribeToNav = (onChange: () => void) => {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributeFilter: ["data-nav"] });
  return () => observer.disconnect();
};
const navIsCollapsed = () => document.documentElement.getAttribute("data-nav") === "collapsed";
const navServerSnapshot = () => false;

function useRailCollapsed(): [boolean, () => void] {
  const collapsed = useSyncExternalStore(subscribeToNav, navIsCollapsed, navServerSnapshot);
  // Writes the attribute only; the observer above turns that into a re-render.
  const toggle = () => {
    const next = !navIsCollapsed();
    const el = document.documentElement;
    if (next) el.setAttribute("data-nav", "collapsed");
    else el.removeAttribute("data-nav");
    try {
      localStorage.setItem("kairos-nav", next ? "collapsed" : "expanded");
    } catch {
      // Private mode / storage disabled: the rail still toggles for this session.
    }
  };
  return [collapsed, toggle];
}

export function SidebarContent({ onNavigate, role, user, collapsible = false }: { onNavigate?: () => void; role: Role; user: User | null; collapsible?: boolean }) {
  const pathname = usePathname();
  const [railCollapsed, toggleRail] = useRailCollapsed();
  const homeHref = role === "field_worker" ? "/briefs" : "/management";
  // Collapse is per-group, default open, session-local (persistence = hydration churn for nothing).
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const sections = NAV
    .map((s) => ({ ...s, items: s.items.filter((it) => !it.roles || it.roles.includes(role)) }))
    .filter((s) => s.items.length > 0);

  return (
    <div className="flex h-full flex-col">
      {/* Layout here is CSS, not `railCollapsed` — state is false on the first
          client render, so a state-driven row would paint the expanded layout
          inside a 68px rail for one frame on every load. */}
      <div className="rail-brand-row flex items-center justify-between gap-2 px-5 py-6">
        <BrandLink href={homeHref} />
        {/* Exactly one toggle in the DOM. Collapsed it sits under the mark — beside
            it there is no room. Placing it with state rather than CSS is what keeps
            a second, hidden copy from shadowing it in the accessibility tree. */}
        {collapsible && (
          <button
            type="button"
            onClick={toggleRail}
            aria-expanded={!railCollapsed}
            aria-label={railCollapsed ? "Expand navigation" : "Collapse navigation"}
            title={railCollapsed ? "Expand navigation" : "Collapse navigation"}
            className="grid size-8 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <Icon name="chevron" className={cn("size-4 transition-transform duration-200 motion-reduce:transition-none", !railCollapsed && "rotate-180")} />
          </button>
        )}
      </div>

      <nav className="rail-nav flex-1 space-y-[var(--rail-section-gap,1.25rem)] overflow-y-auto px-3 py-2 scrollbar-none">
        {sections.map((section) => {
          const isOpen = !collapsed[section.group];
          const list = (
            <ul id={`nav-${section.group || "top"}`} className="space-y-0.5">
              {section.items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(item.href + "/");
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-label={item.label}
                      title={item.label}
                      className={cn(
                        "rail-link flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-body transition-colors",
                        active
                          ? "bg-accent-soft font-semibold text-accent"
                          : "text-muted hover:bg-surface-2 hover:text-ink",
                      )}
                    >
                      <Icon name={item.icon} />
                      <span className="rail-label">{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          );
          if (!section.group) return <div key="top">{list}</div>;
          return (
            <div key={section.group}>
              <button
                type="button"
                aria-expanded={isOpen}
                aria-controls={`nav-${section.group}`}
                onClick={() => setCollapsed((c) => ({ ...c, [section.group]: !c[section.group] }))}
                className="rail-group-header flex w-full items-center gap-1 rounded px-2 pb-1.5 text-micro font-bold uppercase tracking-[0.1em] text-muted transition-colors hover:text-ink"
              >
                <Icon
                  name="chevron"
                  className={cn("size-3 transition-transform duration-150 ease-out", isOpen && "rotate-90")}
                />
                {section.group}
              </button>
              {isOpen && list}
            </div>
          );
        })}

      </nav>

      {user && <GovernorPill userId={user.user_id} />}

      <div className="mx-3 mb-4 mt-2 space-y-0.5 border-t border-line pt-3">
        <Link href="/system-information" onClick={onNavigate} className="rail-link flex items-center gap-2 rounded-lg px-2 py-1.5 text-body text-muted transition-colors hover:bg-surface-2 hover:text-ink">
          <Icon name="info" className="size-[18px]" /><span className="rail-label">System Information</span>
        </Link>
        {ADMIN_ROLES.includes(role) && (
          <>
            <Link href="/system-health" onClick={onNavigate} className="rail-link flex items-center gap-2 rounded-lg px-2 py-1.5 text-body text-muted transition-colors hover:bg-surface-2 hover:text-ink">
              <Icon name="health" className="size-[18px]" /><span className="rail-label">System Health</span>
            </Link>
            <Link href="/system-benchmarks" onClick={onNavigate} className="rail-link flex items-center gap-2 rounded-lg px-2 py-1.5 text-body text-muted transition-colors hover:bg-surface-2 hover:text-ink">
              <Icon name="chart" className="size-[18px]" /><span className="rail-label">System Benchmarks</span>
            </Link>
          </>
        )}
        <Link href="/settings" onClick={onNavigate} className="rail-link flex items-center gap-2 rounded-lg px-2 py-1.5 text-body text-muted transition-colors hover:bg-surface-2 hover:text-ink"><Icon name="settings" className="size-[18px]" /><span className="rail-label">System Settings</span></Link>
      </div>

    </div>
  );
}

/** Bottom tab bar for all roles on mobile — thumb-reachable, ≥44px targets.
    Field workers keep Voice + Me (sign-out); staff get Overview + More (nav sheet). */
function AccountMenu({ open, onClose, name, role, onSignOut }: { open: boolean; onClose: () => void; name: string; role: string; onSignOut: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-label="User menu">
      <button className="absolute inset-0" aria-label="Close user menu" onClick={onClose} />
      <div className="sidebar-scope absolute right-4 top-16 w-64 rounded-xl border border-line p-2 shadow-xl animate-[overlay-in_150ms_ease-out]">
        <div className="flex items-start justify-between gap-3 px-3 py-2"><div className="min-w-0"><p className="truncate text-sm font-semibold">{name}</p><p className="text-caption text-muted">{role.replace(/_/g, " ")}</p></div><ThemeToggle className="-mr-1 -mt-1 shrink-0" /></div>
        <Link href="/settings" onClick={onClose} className="flex rounded-lg px-3 py-2 text-sm transition-colors hover:bg-surface-2">System Settings</Link>
        <button type="button" onClick={onSignOut} className="flex w-full rounded-lg px-3 py-2 text-left text-sm text-danger transition-colors hover:bg-surface-2">Sign out</button>
      </div>
    </div>
  );
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function MiniCalendar({ onClose }: { onClose: () => void }) {
  const [today] = useState(() => new Date());
  const year = today.getFullYear();
  const month = today.getMonth();
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const totalCells = Math.ceil((firstWeekday + daysInMonth) / WEEKDAYS.length) * WEEKDAYS.length;
  const monthLabel = today.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <Modal title="Calendar" onClose={onClose}>
      <table aria-label={`Calendar for ${monthLabel}`} className="w-full table-fixed border-collapse text-center">
        <caption className="mb-3 text-left text-subtitle font-semibold text-ink">{monthLabel}</caption>
        <thead>
          <tr className="text-label font-semibold text-muted">
            {WEEKDAYS.map((weekday) => <th key={weekday} scope="col" className="pb-2">{weekday}</th>)}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: totalCells / WEEKDAYS.length }, (_, week) => (
            <tr key={week}>
              {Array.from({ length: WEEKDAYS.length }, (_, weekday) => {
                const day = week * WEEKDAYS.length + weekday - firstWeekday + 1;
                if (day < 1 || day > daysInMonth) return <td key={`${week}-${weekday}`} className="h-9" />;
                const isToday = day === today.getDate();
                const dateTime = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                return (
                  <td key={dateTime} className="h-9">
                    <time
                      dateTime={dateTime}
                      aria-current={isToday ? "date" : undefined}
                      className={cn(
                        "inline-grid size-7 place-items-center rounded-full text-caption",
                        isToday ? "bg-accent-soft font-semibold text-accent" : "text-ink",
                      )}
                    >
                      {day}
                    </time>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [palette, setPalette] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const goSeqRef = useRef<number | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [plantState, setPlantState] = useState<PlantState | null>(null);
  const moreTriggerRef = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const pathname = usePathname();


  // Central role guard: no staff/admin page is reachable by URL without the right role.
  // Only enforced once a real user is resolved (anonymous dev sessions = backend engineer default).
  useEffect(() => {
    if (user && !routeAllowed(pathname, user.role)) {
      router.replace(roleHome(user.role));
    }
  }, [pathname, user, router]);

  useEffect(() => {
    let alive = true;
    async function authorize() {
      const token = getToken();
      if (isStrictAuth()) {
        if (!token) {
          router.replace("/login");
          return;
        }
        const profile = await getMe();
        if (!alive) return;
        if (!profile) {
          logout();
          router.replace("/login");
          return;
        }
        setUser(profile);
      } else if (token) {
        const profile = await getMe();
        if (!alive) return;
        if (!profile) {
          // A token exists but is stale/expired (e.g. Supabase JWT past its 1h TTL).
          // Don't silently fall back to the engineer dev-default — that reads as a
          // surprise account switch (field_worker → engineer) and hides field nav.
          // Re-authenticate instead; the anonymous no-token demo bypass is untouched.
          logout();
          router.replace("/login");
          return;
        }
        setUser(profile);
      }
      if (alive) setAuthed(true);
    }
    void authorize();
    // Service worker: production only. In dev it caches the app shell and fights
    // HMR — stale chunk hashes trigger a hard reload that re-serves the stale
    // cache, an infinite refresh loop. Unregister any stale SW so dev self-heals.
    if ("serviceWorker" in navigator) {
      if (process.env.NODE_ENV === "production") {
        navigator.serviceWorker.register("/sw.js").catch(() => {});
      } else {
        navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister()));
      }
    }
    // Flush write queue on reconnect
    async function onOnline() {
      await flushQueue();
    }
    window.addEventListener("online", onOnline);
    return () => {
      alive = false;
      window.removeEventListener("online", onOnline);
    };
  }, [router]);

  useEffect(() => {
    if (!user?.site_id) return;
    let alive = true;
    getPlantState(user.site_id).then((r) => {
      if (!alive) return;
      if (r.data && r.data.state !== "normal") setPlantState(r.data);
      else setPlantState(null);
    });
    return () => { alive = false; };
  }, [user]);

  // Focus trap for the mobile "More" nav sheet; focus returns to its trigger on close.
  useEffect(() => {
    if (!moreOpen) return;
    const trigger = moreTriggerRef.current;
    sheetRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMoreOpen(false);
      if (event.key === "Tab" && sheetRef.current) {
        const focusable = sheetRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first || !last) {
          event.preventDefault();
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      trigger?.focus();
    };
  }, [moreOpen]);

  const role: Role = user?.role ?? "engineer";

  const paletteItems = useMemo<PaletteItem[]>(() => {
    const nav = NAV.flatMap((g) =>
      g.items
        .filter((i) => !i.roles || i.roles.includes(role))
        .map((i) => ({ group: g.group || "Go to", label: i.label, href: i.href })),
    );
    return [
      ...nav,
      {
        group: "Actions",
        label: "Toggle dark mode",
        action: () => {
          const root = document.documentElement;
          const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
          root.setAttribute("data-theme", next);
          try { localStorage.setItem("kairos-theme", next); } catch {}
        },
      },
      { group: "Actions", label: "System Settings", href: "/settings" },
      { group: "Actions", label: "Keyboard shortcuts", hint: "?", action: () => setHelpOpen(true) },
    ];
  }, [role]);

  // Global keys: ⌘K palette, ? help, g-then-letter navigation. Ignored while typing.
  useEffect(() => {
    const GO: Record<string, string> = {
      b: "/briefs", c: "/copilot", a: "/assets", e: "/events", g: "/graph",
      d: "/documents", q: "/governance/quarantine", v: "/governance", m: "/management",
    };
    const isTyping = (t: EventTarget | null) =>
      t instanceof HTMLElement &&
      (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
        return;
      }
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "?") { setHelpOpen(true); return; }
      const now = Date.now();
      if (goSeqRef.current && now - goSeqRef.current < 1500) {
        goSeqRef.current = null;
        const href = GO[e.key.toLowerCase()];
        if (href) { e.preventDefault(); router.push(href); }
        return;
      }
      if (e.key.toLowerCase() === "g") goSeqRef.current = now;
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  function signOut() {
    logout();
    setUser(null);
    router.replace("/login");
  }

// Auth gate: never blank. Show shell chrome + skeleton until token resolves.
  if (authed !== true) {
    return (
      <div className="flex min-h-dvh">
        <aside data-rail className="sidebar-scope hidden w-[var(--rail-w)] shrink-0 border-r border-line transition-[width] duration-200 motion-reduce:transition-none lg:block" aria-hidden="true">
          <div className="sticky top-0 h-dvh px-4 py-4">
            <BrandLink href="/management" />
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <main id="main" className="min-w-0 flex-1" aria-busy="true">
            <PageSkeleton />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-body focus:font-semibold focus:text-ink focus:shadow-lg focus:outline-none focus-visible:outline-2 focus-visible:outline-accent"
      >
        Skip to content
      </a>

      <CommandPalette open={palette} onClose={() => setPalette(false)} items={paletteItems} />
      <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      {calendarOpen && <MiniCalendar onClose={() => setCalendarOpen(false)} />}

      {/* Desktop sidebar — all roles; sidebar-scope remaps tokens to the dark rail palette */}
      <aside data-rail className="sidebar-scope hidden w-[var(--rail-w)] shrink-0 border-r border-line transition-[width] duration-200 motion-reduce:transition-none lg:block print:hidden">
        <div className="sticky top-0 h-dvh">
          <SidebarContent role={role} user={user} collapsible />
        </div>
      </aside>

      {mobileDrawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <button className="absolute inset-0 animate-[overlay-in_150ms_ease-out] bg-[var(--scrim)]" aria-label="Close menu" onClick={() => setMobileDrawerOpen(false)} />
          <div className="sidebar-scope absolute inset-y-0 left-0 w-[316px] max-w-[86vw] overflow-y-auto border-r border-line outline-none animate-[drawer-in_250ms_ease-out]">
            <SidebarContent onNavigate={() => setMobileDrawerOpen(false)} role={role} user={user} />
          </div>
        </div>
      )}

      {/* Mobile "More" nav sheet — full grouped nav, same dark rail palette */}
      {moreOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <button
            className="absolute inset-0 animate-[overlay-in_150ms_ease-out] bg-[var(--scrim)]"
            aria-label="Close menu"
            onClick={() => setMoreOpen(false)}
          />
          <div
            ref={sheetRef}
            tabIndex={-1}
            className="sidebar-scope absolute inset-x-0 bottom-0 max-h-[80dvh] overflow-y-auto rounded-t-2xl border-t border-line pb-[env(safe-area-inset-bottom)] outline-none animate-[sheet-in_250ms_ease-out]"
          >
            <SidebarContent
              onNavigate={() => setMoreOpen(false)}
              role={role}
              user={user}
            />
          </div>
        </div>
      )}

      {/* Mobile: 56px bottom tabs + safe-area for all roles; content padding clears them */}
      {/* inert while the sheet dialog is open so screen readers can't wander behind it */}
      <div
        inert={moreOpen || mobileDrawerOpen || calendarOpen || undefined}
        className="flex min-w-0 flex-1 flex-col pb-[calc(56px+env(safe-area-inset-bottom))] lg:pb-0 print:pb-0"
      >
        <AppHeader
          name={user?.email ?? "Kairos user"}
          role={role}
          onOpenSearch={() => setPalette(true)}
          onOpenCalendar={() => setCalendarOpen((open) => !open)}
          calendarOpen={calendarOpen}
          onCreate={() => router.push("/documents/ingest")}
          onOpenBriefs={() => router.push("/briefs")}
          onOpenUser={() => setAccountOpen((open) => !open)}
          userInitial={getUserInitials(user?.email)}
        />
        <MobileAppHeader
          onOpenMenu={() => setMobileDrawerOpen(true)}
          onOpenSearch={() => setPalette(true)}
          onOpenCalendar={() => setCalendarOpen((open) => !open)}
          calendarOpen={calendarOpen}
          onCreate={() => router.push("/documents/ingest")}
          onOpenBriefs={() => router.push("/briefs")}
          onOpenUser={() => setAccountOpen((open) => !open)}
          userInitial={getUserInitials(user?.email)}
        />

        {/* Plant operating state banner */}
        {plantState && (
          <div
            role="alert"
            className={cn(
              "flex items-center gap-3 px-5 py-2.5 text-body font-semibold",
              plantState.state === "emergency"
                ? "bg-danger text-white"
                : "bg-[color-mix(in_srgb,var(--caution)_18%,var(--surface))] text-caution",
            )}
          >
            <span className="size-2 shrink-0 animate-pulse rounded-full bg-current" aria-hidden="true" />
            {capitalize(plantState.state)} mode active
            {" — only critical briefs are being delivered"}
          </div>
        )}
        {/* Shell owns page padding; /copilot opts out (full-bleed sticky composer). */}
        <main
          id="main"
          className={cn(
            "min-w-0 flex-1",
            pathname !== "/copilot" && "px-5 py-8 sm:px-8 sm:py-10 print:p-0",
          )}
        >
          <div key={pathname} className="app-route">{children}</div>
        </main>
      </div>

      {/* No mobile bottom tab bar. `BottomTabs` was deleted on 2026-08-15 — it had been
          commented out since the mobile UX was deferred, so it was neither shipped nor
          removed. Mobile navigates via the hamburger sidebar; recover from git if revived. */}
      <AccountMenu open={accountOpen} onClose={() => setAccountOpen(false)} name={user?.email ?? "Kairos user"} role={role} onSignOut={signOut} />
    </div>
  );
}
