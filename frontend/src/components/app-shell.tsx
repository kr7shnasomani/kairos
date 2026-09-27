"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { BrandLink } from "./brand-link";
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
import { Icon as SharedIcon, isIconName, type IconName as SharedIconName } from "./icon";
import { getSearchShortcut } from "@/lib/search-shortcut";

// Staff surfaces (Assure group + RCA) are hidden from field workers. Dev-bypass (no session)
// defaults to engineer, so an unauthenticated demo still sees everything.
const STAFF: Role[] = ["engineer", "reliability", "admin"];
/** Staff plus the read-only compliance auditor — mirrors STAFF_AND_COMPLIANCE in use-role.ts. */
const STAFF_AND_COMPLIANCE: Role[] = [...STAFF, "compliance"];

// Nav keys → the shared Phosphor set (components/icon.tsx). Conventional metaphors
// over clever ones: a sidebar is scanned, not read.
const NAV_ICON = {
  management: "squares-four", briefs: "clipboard-text", copilot: "sparkle", assets: "cube",
  events: "pulse", voice: "waveform", alert: "flag", rca: "target", graph: "graph",
  coverage: "chart-pie-slice", compliance: "shield-check", governance: "scales",
  audit: "clock-counter-clockwise", documents: "file-text", projects: "folders",
  offboarding: "handshake", settings: "gear-six", chevron: "caret-right",
} as const satisfies Record<string, SharedIconName>;
type IconName = keyof typeof NAV_ICON;

/** Active items switch to the filled cut of the same glyph (Linear/Apple convention). */
function Icon({ name, className, active = false }: { name: IconName; className?: string; active?: boolean }) {
  const base = NAV_ICON[name];
  const filled = `${base}-fill`;
  return <SharedIcon name={active && isIconName(filled) ? filled : base} className={className} />;
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
      { href: "/management/coverage", label: "Coverage", icon: "coverage", roles: STAFF },
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
        "rail-governor rail-link mx-3 my-1 flex items-center justify-between px-2.5 py-1.5 text-label",
        suppressed
          ? "bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] text-danger"
          : "bg-surface-2 text-muted",
      )}
    >
      {/* Collapsed the wording goes, the count stays — the ratio is the signal,
          and `title` above still carries the full sentence. */}
      <span className="rail-label font-semibold">{suppressed ? "Governor suppressed" : "Governor active"}</span>
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

/** Global actions the rail owns on desktop (there is no top bar): search, the primary
 *  action, and the account. Optional so the rail renders standalone in tests. */
export type RailActions = { onSearch: () => void; onCreate: () => void; onOpenUser: () => void; accountName: string; accountInitials: string };

export function SidebarContent({ onNavigate, role, user, collapsible = false, actions }: { onNavigate?: () => void; role: Role; user: User | null; collapsible?: boolean; actions?: RailActions }) {
  const pathname = usePathname();
  const [railCollapsed, toggleRail] = useRailCollapsed();
  const homeHref = role === "field_worker" ? "/briefs" : "/management";
  const shortcut = getSearchShortcut(typeof navigator === "undefined" ? undefined : navigator.platform);
  const sections = NAV
    .map((s) => ({ ...s, items: s.items.filter((it) => !it.roles || it.roles.includes(role)) }))
    .filter((s) => s.items.length > 0);

  return (
    <div className="flex h-full flex-col">
      {/* Layout here is CSS, not `railCollapsed` — state is false on the first
          client render, so a state-driven row would paint the expanded layout
          inside a 68px rail for one frame on every load. */}
      {/* Fixed 56px in BOTH states. The collapse toggle lives at the foot precisely
          so this row never has to grow to hold it: when it stacked here, collapsing
          pushed the whole icon column ~90px down and nothing lined up any more. */}
      <div className="rail-brand-row flex h-14 shrink-0 items-center gap-2 border-b border-line px-5">
        <BrandLink href={homeHref} />
      </div>

      {actions && (
        <div className="rail-actions flex shrink-0 gap-2 px-3 pt-4">
          <button
            type="button"
            onClick={actions.onSearch}
            aria-label="Search workspace"
            title={`Search (${shortcut})`}
            className="rail-link flex h-9 min-w-0 flex-1 items-center gap-3 border border-line px-2.5 text-body text-muted transition-colors hover:border-[color-mix(in_srgb,var(--accent)_45%,var(--line))] hover:text-ink"
          >
            <SharedIcon name="magnifying-glass" className="size-4 shrink-0" />
            <span className="rail-label flex-1 text-left">Search</span>
            <kbd className="rail-label border border-line px-1.5 font-sans text-micro text-muted">{shortcut}</kbd>
          </button>
          <button
            type="button"
            onClick={actions.onCreate}
            aria-label="Ingest document"
            title="Ingest document"
            data-rail-ingest
            className="fill-sweep grid size-9 shrink-0 place-items-center bg-accent text-on-accent"
          >
            <SharedIcon name="plus" className="relative z-10 size-4" />
          </button>
        </div>
      )}

      {/* No section headings. They cost four rows of chrome, and collapsing the rail
          hid them anyway, so the icon column re-flowed on every toggle. The grouping
          survives as spacing plus each list's aria-label, and the ⌘K palette still
          groups its results by the same NAV section names. */}
      <nav className="rail-nav flex-1 space-y-[var(--rail-section-gap,1.25rem)] overflow-y-auto px-3 pb-2 pt-5 scrollbar-none">
        {sections.map((section) => (
          <ul key={section.group || "top"} aria-label={section.group || undefined} className="space-y-1">
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
                      "rail-link flex items-center gap-3 px-2.5 py-2 text-body transition-colors",
                      // Square row with a 2px accent rule, the landing's active-cell mark.
                      active
                        ? "bg-surface-2 font-semibold text-ink shadow-[inset_2px_0_0_var(--accent)] [&>svg]:text-accent"
                        : "text-muted hover:bg-surface-2 hover:text-ink",
                    )}
                  >
                    <Icon name={item.icon} active={active} />
                    <span className="rail-label">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        ))}

      </nav>

      {user && <GovernorPill userId={user.user_id} />}

      {/* Account lives at the foot of the rail, as in Linear / Vercel / Notion.
          Settings, System Health (admins) and sign-out are inside the menu it opens. */}
      <div className="rail-foot mx-3 mb-3 mt-2 flex items-center gap-2 border-t border-line pt-3">
      {actions ? (
        <button
          type="button"
          onClick={actions.onOpenUser}
          aria-label="Open user menu"
          className="rail-link flex min-w-0 flex-1 items-center gap-3 px-2 py-1 text-left transition-colors hover:text-ink"
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-2 text-label font-bold text-ink">{actions.accountInitials}</span>
          <span className="rail-label min-w-0 flex-1 leading-tight">
            <span className="block truncate text-body text-ink">{actions.accountName}</span>
            <span className="block text-micro capitalize text-muted">{role.replace(/_/g, " ")}</span>
          </span>
          <SharedIcon name="caret-up-down" className="rail-label size-4 shrink-0 text-muted" />
        </button>
      ) : (
        <Link href="/settings" onClick={onNavigate} aria-label="System Settings" title="System Settings" className="rail-link flex min-w-0 flex-1 items-center gap-3 px-2.5 py-2 text-body text-muted transition-colors hover:bg-surface-2 hover:text-ink">
          <Icon name="settings" /><span className="rail-label">System Settings</span>
        </Link>
      )}
      {/* Exactly one toggle in the DOM — a second, hidden copy would shadow it in
          the accessibility tree. Collapsed, it drops under the account square:
          growth at the foot costs scroll height, never icon alignment. */}
      {collapsible && (
        <button
          type="button"
          onClick={toggleRail}
          aria-expanded={!railCollapsed}
          aria-label={railCollapsed ? "Expand navigation" : "Collapse navigation"}
          title={railCollapsed ? "Expand navigation" : "Collapse navigation"}
          className="grid size-8 shrink-0 place-items-center text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          <Icon name="chevron" className={cn("size-4 transition-transform duration-200 motion-reduce:transition-none", !railCollapsed && "rotate-180")} />
        </button>
      )}
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
      <div className="sidebar-scope absolute right-4 top-16 w-64 border border-line p-2 shadow-xl animate-[overlay-in_150ms_ease-out] lg:bottom-3 lg:left-[calc(var(--rail-w)+0.5rem)] lg:right-auto lg:top-auto">
        <div className="flex items-start justify-between gap-3 px-3 py-2"><div className="min-w-0"><p className="truncate text-sm font-semibold">{name}</p><p className="text-caption text-muted">{role.replace(/_/g, " ")}</p></div><ThemeToggle className="-mr-1 -mt-1 shrink-0" /></div>
        <Link href="/settings" onClick={onClose} className="flex items-center gap-2.5 px-3 py-2 text-sm transition-colors hover:bg-surface-2"><SharedIcon name="gear-six" className="size-4 text-muted" />System Settings</Link>
        {ADMIN_ROLES.includes(role as Role) && (
          <Link href="/system-health" onClick={onClose} className="flex items-center gap-2.5 px-3 py-2 text-sm transition-colors hover:bg-surface-2"><SharedIcon name="heartbeat" className="size-4 text-muted" />System Health</Link>
        )}
        <button type="button" onClick={onSignOut} className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-danger transition-colors hover:bg-surface-2"><SharedIcon name="sign-out" className="size-4" />Sign out</button>
      </div>
    </div>
  );
}


export function AppShell({ children }: { children: React.ReactNode }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
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

  const railActions: RailActions = {
    onSearch: () => setPalette(true),
    onCreate: () => router.push("/documents/ingest"),
    onOpenUser: () => setAccountOpen((open) => !open),
    accountName: user?.email ?? "Kairos user",
    accountInitials: getUserInitials(user?.email),
  };

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

      {/* Desktop sidebar — all roles; sidebar-scope remaps tokens to the dark rail palette.
          There is no desktop top bar: search, Ingest and the account live in the rail. */}
      <aside data-rail className="sidebar-scope hidden w-[var(--rail-w)] shrink-0 border-r border-line transition-[width] duration-200 motion-reduce:transition-none lg:block print:hidden">
        <div className="sticky top-0 h-dvh">
          <SidebarContent role={role} user={user} collapsible actions={railActions} />
        </div>
      </aside>

      {mobileDrawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <button className="absolute inset-0 animate-[overlay-in_150ms_ease-out] bg-[var(--scrim)]" aria-label="Close menu" onClick={() => setMobileDrawerOpen(false)} />
          <div className="sidebar-scope absolute inset-y-0 left-0 w-[316px] max-w-[86vw] overflow-y-auto border-r border-line outline-none animate-[drawer-in_250ms_ease-out]">
            <SidebarContent onNavigate={() => setMobileDrawerOpen(false)} role={role} user={user} actions={railActions} />
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
        inert={moreOpen || mobileDrawerOpen || undefined}
        className="flex min-w-0 flex-1 flex-col pb-[calc(56px+env(safe-area-inset-bottom))] lg:pb-0 print:pb-0"
      >
        <MobileAppHeader
          onOpenMenu={() => setMobileDrawerOpen(true)}
          onOpenSearch={() => setPalette(true)}
          onCreate={() => router.push("/documents/ingest")}
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
                ? "bg-danger text-on-danger"
                : "bg-[color-mix(in_srgb,var(--caution)_18%,var(--surface))] text-caution",
            )}
          >
            <span className="size-2 shrink-0 animate-pulse rounded-full bg-current" aria-hidden="true" />
            {capitalize(plantState.state)} mode active
            {" — only critical briefs are being delivered"}
          </div>
        )}
        {/* Shell owns page padding; /copilot opts out (full-bleed sticky composer).
            Every other route sits in the landing's frame: hairline rails either side
            of a centred column, visible once the viewport is wider than the column. */}
        <main id="main" className="flex min-w-0 flex-1 flex-col overflow-x-clip">
          {pathname === "/copilot" ? (
            <div key={pathname} className="app-route flex-1">{children}</div>
          ) : (
            <div className="relative mx-auto flex w-full max-w-[1464px] flex-1 flex-col xl:border-x print:border-0">
              <div key={pathname} className="app-route flex-1 px-5 py-8 sm:px-8 sm:py-10 print:p-0">{children}</div>
            </div>
          )}
        </main>
      </div>

      {/* No mobile bottom tab bar. `BottomTabs` was deleted on 2026-08-15 — it had been
          commented out since the mobile UX was deferred, so it was neither shipped nor
          removed. Mobile navigates via the hamburger sidebar; recover from git if revived. */}
      <AccountMenu open={accountOpen} onClose={() => setAccountOpen(false)} name={user?.email ?? "Kairos user"} role={role} onSignOut={signOut} />
    </div>
  );
}
