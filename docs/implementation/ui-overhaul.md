# UI overhaul: bring the workspace up to the landing page

Status: **All phases done (2026-09-22).** The desktop top bar from Phase 4 was later replaced by a sidebar-first shell; see the last follow-up. Audited at 1440x900, light + dark, against the live dev server.

## The diagnosis in one line

The landing page and the workspace already share the **same colours and fonts**
(`--lp-*` and the app tokens are near-identical hex values, and both load Instrument Sans + DM Sans).
What they do not share is the **shape language, type treatment, layout structure and motion**.
The landing reads as a precise engineering document; the workspace reads as a generic
rounded-card SaaS template with the brand colour on top.

## What makes the landing page work (the target)

| Trait | Landing (`.landing`, `globals.css` §Public landing page) |
|---|---|
| Corners | Square chrome everywhere. Only product mockups round (`.lp-mock`, 10px). |
| Display type | Instrument Sans **500**, `line-height: 1`, `letter-spacing: -0.05em`, large. |
| Emphasis | Charcoal highlight box behind a key phrase; orange second line. |
| Eyebrow | Filled orange block, white uppercase label (`HOW IT WORKS`). |
| Structure | Centred column with hairline **frame rails** (`.lp-frame`), **corner ticks** (`.lp-tick`), alternating `#f8f8f8` bands, dark bands for contrast. |
| Grids | 1px hairline **mesh** of cells, not floating cards with gaps. |
| Numbers | Big display numerals (`~20%`, `88%`) in accent, label under. |
| Buttons | Square orange block with a `▸` glyph; secondary is a square black block. |
| Hover | `.lp-card`: scale 1.02 + accent border. `.lp-cell`: accent wash + 2px top bar that draws left→right. |
| Motion | Scroll reveal with child stagger (`data-reveal` / `data-stagger`), bars that grow, tab crossfade. |
| Colour discipline | Orange + ink + grey. Colour means something. |

## Issues found

Counts are from `frontend/src/app/(app)` + `frontend/src/components`.

### A. Shape language (biggest visual gap)
1. **362** `rounded-lg/xl/md` and **100** `rounded-full` on chrome: cards, buttons, inputs, tabs, pills, rail items. Landing chrome is square.
2. **97** `shadow-*` uses and `Card interactive` hovers with `-translate-y-0.5 hover:shadow-lg` (`components/ui-card.tsx:23`). Landing never floats a card on a shadow; it lifts by scale + accent border.
3. Pages are **floating rounded cards separated by gaps** on white (Overview, Governance, Graph). Landing uses a framed column and hairline meshes.

### B. Typography
4. `PageHeader` h1 (`components/ui.tsx:~996`) is `font-semibold` (600), `leading-tight`, `letter-spacing: 0` (forced by `globals.css` `h1,h2,h3 { letter-spacing: 0 }`). Landing display is weight 500, lh 1, -0.05em. Same font, completely different voice.
5. Type scale tops out at 28px (`--text-display`); page titles look small and timid next to the landing.
6. Eyebrows are plain orange text, not the landing's filled orange label block.
7. KPI numerals are **Geist Mono** (`.tabular`) in five different status colours. Landing stats are Instrument display numerals in accent.
8. `font-display` utility is used **0** times; headings only get it through the global `h1,h2,h3` rule, so card titles, KPI labels and section heads fall back to DM Sans.

### C. Colour discipline
9. **Rainbow KPI tiles** (Overview, Governance): tinted background + coloured left bar + coloured numeral per tile (brown / blue / red / red). Four alarm colours on one row means none of them signals anything.
10. Status pills in 5 tinted colours everywhere (`StatusBadge`, `TONE_STYLE`), plus a blue `Phase 3 · Proactive` pill in the header and a blue `Report` pill beside orange/red pills on Governance cards.
11. Graph edges use four colours; legend has to explain them.

### D. Layout and shell
12. **Rail**: active item is a rounded orange-soft pill; items are rounded. Landing nav is square cells with hairline dividers and an accent rule.
13. **Header**: rounded search pill + rounded icon buttons + blue pill. Landing header is a bordered row of cells ending in a solid orange CTA block.
14. No frame rails, no corner ticks, no bands in the app: nothing ties it visually to the landing.

### E. Data display
15. Overview "Operational events" is a **`type="monotone"` area** (`app/(app)/overview/page.tsx:182`) over integer daily counts: one event on 13 Sept renders as a smooth hump with fractional values in between. It invents data. Landing uses bars (`.lp-bar`, hero-gradient leader).
16. Axis dates read "9 Sept … 22 Sept", 14 crowded labels.
17. "Needs attention" is 8 near-identical rows ("Overdue conflict · engineering" x3, "Overdue quarantine · deviation_flag" x4) with raw snake_case.
18. Graph node labels and the validity list show raw filenames (`regulatory_clause_excerpts.pdf`, `work_order_closeo…`).
19. System health is a wrap of rounded text chips; landing would use a cell mesh with a status dot per cell.

### F. Copy
20. **Eyebrows leak internal architecture**: "Layer 7 · Dual-track governance", "Layer 11 · Root Cause", "Layer 12 · Model Gate", "Flow C · Universal document ingestion" (33 distinct eyebrows, ~20 are layer numbers). Users do not know the 13-layer diagram; landing eyebrows say what the section is (`THE PROBLEM`, `HOW IT WORKS`).
21. Mixed case: "Layer 11 · Root Cause" vs "Layer 11 · Quality & compliance".

### G. Empty and first states
22. Copilot empty state is a generic centred chat-bubble icon in a rounded tile + rounded suggestion pills: the stock AI-chat look. The landing's hero voice ("The plant already knows.") is the obvious reference.
23. `EmptyState` is a dashed rounded box with a generic info-circle icon.

### H. Motion
24. Landing's reveal + stagger system exists only under `.lp-anim`; the app has `rise-in` but uses it in **4** places. Lists, KPI rows and card grids appear all at once.
25. `animate-bounce` x10 and `animate-pulse` x13: toy motion the landing never uses.

### I. Root cause (why fixing it page by page would fail)
26. **127** hand-rolled `rounded-xl border border-line bg-surface` cards versus **7** files importing the `Card` primitive. Restyling `Card` today changes almost nothing. Primitives must be adopted first, then restyled once.

## The plan

Principle: **fix the system, not the pages.** Change tokens and primitives, migrate call sites
onto them, then do page-specific work. Every phase ships green (`tsc`, lint, vitest) and is
screenshotted before/after.

### Phase 0: decisions (decided 2026-09-22)
- **Square chrome** (radius 0) like the landing. Status dots and avatars stay round.
- **Frame rails** on the content column at ≥1280px, off below (Phase 4).

### Phase 1: tokens (`globals.css`) ✅
Shipped as: every Tailwind `--radius-*` variable zeroed in unlayered `:root` (squares all
`rounded-{xs…4xl}` call sites without a codemod; `rounded-full` untouched); `--text-hero`;
`.display`; `.stagger`; `.mesh` (in `@layer components` so utilities still win); and
`--lp-*` lookups in `.lp-card` / `.lp-cell` / `.lp-tick` / `.lp-frame` fall back to app
tokens, so the workspace reuses the landing classes directly instead of copies.
Original intent:
- `--radius: 0`, `--radius-lg: 0` (one change flips every `rounded-card` user).
- Make `.landing`'s `--lp-*` alias the app tokens where values are equal, so there is one palette source.
- Promote landing classes out of `.landing` scope into shared ones: `.frame` (rails), `.tick`, `.band`, `.cell` (hover mesh), `.lift` (lp-card hover), `.reveal` / `[data-stagger]`, `.bar` / `.bar--lead`.
- Display type: add `--text-hero: 40px`, and a `.display` rule (Instrument 500, lh 1, -0.05em / -0.03em at ≤28px). Drop the global `letter-spacing: 0` on headings.
- Reveal gating: add the `anim` class to `<html>` in the existing `themeInit` script so no-JS still renders.

### Phase 2: primitives (`components/ui.tsx`, `ui-card.tsx`, `skeleton.tsx`) ✅
Shipped: PageHeader, Card, Button (press scale), KpiCard/KpiGroup, StatusBadge (square, tint
kept: its contrast is measured), PhaseBadge *(deleted later — see the icons follow-up)*, FilterTabs, DataTable, EmptyState, metric
skeleton. Deferred: `CardGrid` (use `.mesh` directly in Phase 3), `›` glyph on primary Button.
| Primitive | Change |
|---|---|
| `PageHeader` | `.display` h1 at `--text-hero`; eyebrow becomes filled orange label; optional `highlight` prop for the charcoal box. |
| `Card` | Square, hairline, no shadow; `interactive` → `.lift` (scale + accent border). New `CardGrid` = hairline mesh of `.cell`s. |
| `Button` | Square; primary = orange block + `▸`; secondary = ink block; ghost = hairline. |
| `KpiCard` / `KpiGroup` | Instrument display numeral in ink; accent only for the lead metric; danger only when the value crosses a real threshold. No tinted backgrounds, no left bars. Laid out as a mesh. |
| `StatusBadge` | Square chip, neutral ground, coloured dot carries the state. Keeps text + dot for non-colour cue. |
| `FilterTabs` | Landing tab cells (`--lp-tab`, `--lp-tab-idle`). |
| `DataTable` | Square, uppercase micro headers, row hover = accent wash. |
| `EmptyState` | Landing voice: display line + one sentence + square CTA; no generic icon. |
| Skeletons | Match new geometry exactly (zero CLS). |

### Phase 3: migration ✅
Shipped: chrome pills, chips, progress bars and icon buttons squared (round kept for dots,
avatars, switches, radios, step numbers, success icons); `shadow-xs/sm` flattened via `@theme`
(md+ kept for overlays); `animate-bounce` → `animate-pulse`; translate/shadow hovers → `lp-card`
/ `lp-cell`; every KPI row plus the Governance controls grid on `.mesh` + `.stagger` (9 rows
then, 8 after `/system-benchmarks` was removed; 13 `.mesh` call sites today, including health,
Copilot suggestions, Settings and the login panel).
`.mesh` became container top/left + cell right/bottom borders so a short last row shows ground.
**Skipped:** codemodding the 127 hand-rolled cards onto `Card`. With radius and small shadows
driven by tokens they already render identically; revisit only if Card gains behaviour.
Original intent:
- Codemod the 127 hand-rolled cards onto `Card`/`CardGrid`.
- Strip `rounded-*` from chrome and `shadow-*` from in-page surfaces (keep overlay shadows: modal, palette, menus).
- Replace `animate-bounce`; keep `animate-pulse` only on overdue/critical dots.

### Phase 4: shell (`app-shell.tsx`, `app-header.tsx`) ✅ — *header later removed, see the sidebar-first follow-up*
Shipped: desktop header is a row of hairline cells (search + phase · calendar · briefs · user)
ending in a solid accent **Ingest ›** block; rail brand row is 64px with a bottom rule so the
header line runs across the rail (dropped when collapsed, where the row is taller); active rail
item is square with a 2px inset accent rule and accent icon; content sits in a `max-w-[1464px]`
column with `xl:border-x` rails and accent `lp-tick`s at the header junction (`/copilot` stays
full-bleed). Verified at 1440, 1920, collapsed rail and 375px (no horizontal scroll).
Original intent:
- Rail: square rows, active = 2px orange left rule + ink text, hairline group dividers, corner tick at the rail/header junction.
- Header: row of hairline cells (search · phase · calendar · new · bell · user); phase badge becomes a neutral square chip.
- Content: framed column with rails + ticks; page header sits in a band, body on white.

### Phase 5: pages ✅
Shipped: Overview events chart is daily **bars** (peak day in accent, rest ink; `minTickGap` 40)
instead of a monotone area that drew fractional events; "Needs attention" rows run through
`label()` (`Deviation flag`, not `deviation_flag`); system health is a service cell mesh.
Copilot empty state uses the landing hero (eyebrow, display headline with an accent second line,
numbered suggestion mesh). 23 "Layer N · …" / "Flow C · …" eyebrows rewritten (22 live; one was on a page later removed) as
`Area · Topic` in user language. Graph document nodes get titles from `readableNodeLabel`
(`lib/api.ts`, tested) instead of vault filenames.
**Skipped:** graph edge colours stay four: they encode authority level, which the legend
explains, so collapsing them would drop data. "Needs attention" grouping: humanised labels plus
the asset chip already separate the rows.
Original intent:
| Page | Work |
|---|---|
| Overview `/overview` | KPI mesh; events chart → daily **bars** with lead-bar gradient + grow-in, fewer axis ticks ("9 Sep"); group "Needs attention" by type with counts, humanised labels; system health as a status cell mesh. |
| Copilot | Hero-voice empty state; suggestions as a 2x2 cell mesh; composer square with orange send block. |
| Governance | Control cards → cell mesh with the accent top-bar hover; one badge colour language. |
| Assets / Documents / Events / Audit | Table + filter restyle only (primitives do most of it). |
| Graph | Humanise node labels (title from document, not filename); two edge colours max (verified vs not) + dash for unverified. |
| RCA, Compliance, Field, Off-boarding | Primitive pass + reveal/stagger. |
| All | Rewrite the ~20 "Layer N ·" eyebrows into user language (e.g. "Governance · Human sign-off", "Root cause"). |

### Phase 6: motion pass ✅
Shipped: `.stagger` on every mesh (KPI rows, Governance controls, health, Copilot suggestions);
removed `(app)/template.tsx`, which replayed a second 8px entrance on top of the shell's
`.app-route` (pages travelled 16px); `transition-all` on Overview reveals narrowed to
opacity/transform. All motion stays under the global `prefers-reduced-motion` rule.
Original intent:
- `data-reveal` + `data-stagger` on KPI rows, card meshes and list rows (≤6 staggered, 60ms steps, like the landing).
- Keep the existing count-up, page-in and bar-grow; all under `prefers-reduced-motion`.
- Compositor-only properties (transform/opacity). No layout animation.

### Phase 7: verification ✅
Done 2026-09-22: all static routes (36 then, 34 after the two system pages were removed) loaded at 1440px and 375px (72 checks) with no error
state, no horizontal scroll, no rounded chrome left (radius 2–99px on any element wider than
40px), and every page h1 at Instrument 500 / 40px (desktop). Screenshots reviewed for
Overview, Governance, Assets, Compliance, Copilot and Graph in light, Overview in dark, the
collapsed rail, 1920px (frame rails) and 375px. `tsc` clean; vitest green apart from the date-bound offboarding fixture, which fails on
unchanged code too (272/273 at the latest run, 2026-09-27; fixed 2026-09-28 by freezing the
test's system clock — see `status.md`).
**Not done:** high-contrast palette screenshots; contrast re-measurement (every text/ground
pair introduced reuses an already-measured token pair); dynamic `[id]` routes beyond the ones
reached by clicking through.
Dev-server note: deleting a route file (`template.tsx`) left Turbopack serving a 500 for it
until `docker restart kairos-frontend`; a `git stash` round-trip likewise left stale CSS.
Original intent:
- Screenshot every route in light, dark, high-contrast and 375px (the `docs/implementation/e2e-sweep.md` route list; 44 then, 42 now).
- Contrast: re-measure every token pair touched (square chips change the ground under text).
- `vitest`, `tsc`, lint in Docker; keyboard pass on rail, header, tabs, tables.

### Follow-up: icons and phase jargon ✅ (2026-09-22)
First attempt (squaring the hand-drawn Lucide copies with a global stroke rule) was rejected:
the drawings themselves were the problem. Replaced the whole set instead: **Phosphor
Regular** icons (MIT, `@phosphor-icons/core@2.1.1`) inlined as path data in
`components/icon.tsx`, no npm dependency. The set is now 60 entries — 42 outline glyphs plus
18 `*-fill` cuts for active nav items (43 at the first pass; unused ones were dropped as pages
and the top bar went). All 82 hand-drawn `<svg>` icons across ~50 files
now render `<Icon name=…>`; the rail maps nav keys onto it (`gauge` Overview, `tray` Briefs,
`tree-structure` RCA, `scales` Governance, `gear-six` Settings, …). The square-cap CSS rule is
gone. Only the sparkline (a chart) is still a raw `<svg>`. Link arrows use `›`.
`PhaseBadge` ("Phase 3 · Proactive") is deleted and three "Phase N" messages rephrased in plain
words: the rollout stage is operator detail, still enforced server-side and in `/health/detailed`.

### Follow-up: page removals and widths ✅ (2026-09-22)
`/system-information` and `/system-benchmarks` removed (routes, rail links, system tabs, route
labels, role rule; model-gate runs remain on `/governance/model-gate`). `SystemTabs` renders
nothing when only one tab is left (non-admins). Every page workspace is now `max-w-[1400px]`:
Settings, plant state, field voice / elicitation / deviation, ingest, compare, off-boarding,
asset register / identity and briefs had narrower caps (1100, 1200, `5xl`) and sat inset from
the rest. Settings' section list and panel are one hairline `.mesh` panel.

### Follow-up: sidebar-first shell ✅ (2026-09-22)
The desktop top bar is gone (`app-header.tsx` deleted), following Linear / Vercel / Notion:
the rail owns the global actions. Top: Search (⌘K) beside a solid accent **+ Ingest**. Foot:
the account row (initials, email, role), opening a menu beside the rail with System Settings,
System Health (admins) and Sign out. Removed as dead chrome: the calendar (a static month
grid with no data behind it) and the bell (a link to `/briefs`, already in the nav, with a
count that was never populated). Content now starts at the top of the viewport, so sticky
side panels moved `lg:top-20` → `lg:top-6` and Copilot is `lg:h-dvh`. Mobile keeps its top bar
(menu · search · + · account).
Icons re-picked for convention over cleverness: `squares-four` Overview, `clipboard-text`
Briefs, `sparkle` Copilot, `pulse` Events, `waveform` Voice, `flag` Deviation, `target` RCA,
`chart-pie-slice` Coverage, `file-text` Documents, `folders` Projects, `handshake`
Off-boarding. The active item uses the Phosphor **fill** cut of its glyph.
Rail budget at 1440x900: engineer ~72px spare, full admin rail fits (~5px).

### Follow-up: login, dark theme, detail pass ✅ (2026-09-23)
**Login.** The context panel used `bg-ink`/`text-canvas`, which *inverted* in dark mode (white
panel, dark form). It now carries `sidebar-scope`, the same permanently-dark token remap the nav
rail uses, so it reads the same in both themes. The fake skeleton mock (grey placeholder bars)
is replaced by what each role actually gets — Supervisors / Engineers / Field teams in a
`.mesh`, matching `routeAllowed` — plus the landing's eyebrow block, display heading, accent
corner tick, an accent primary CTA with `›`, and square inputs with hover + focus states.

**Dark palette.** The rail is `#0a0a0a` in every theme and the dark canvas was *also* `#0a0a0a`,
so the rail stopped reading as its own surface and cards floated on nothing. Now three separated
greys: canvas `#101010`, surface `#181818`, surface-2 `#222222`, with `--line` at `#ffffff26`
(hairlines need more presence on dark). Ink on canvas still measures 17.4:1.

**`--on-danger`.** Filled danger blocks (Button, plant-state banner, blast-radius count, record
button) hardcoded `text-white`, which on dark's lighter red (`#e85a63`) measures 3.6:1 — under AA.
The new token is white on light and `#1b0e0f` on dark (~5:1).

**Theme flip.** `ThemeToggle` wraps the attribute write in `document.startViewTransition`, so the
palette crossfades (260ms) instead of snapping; browsers without it, and reduced-motion users,
get the instant swap. Tuned via `::view-transition-old/new(root)` in `globals.css`.

**Detail pass.** Chart tooltip squared and given a shadow that survives a dark canvas; every
remaining `transition-all` narrowed to real properties; Assets and Documents table columns given
explicit widths (headers and cells were clipping: "Complianc", "OEM manua"); signals feed is two
lines per row (one line broke words mid-syllable at ~360px); health cells show the service name
in full, with the redundant sixfold "Healthy" moved to `sr-only` (visible, and toned, the moment
a service is degraded or down).

### Follow-up: header scale, rail collapse, ticks, one hover idiom ✅ (2026-09-27)
**Header scale.** Not a missing template — 41 of 44 pages already use `PageHeader`; `compact`
(20px, for per-record views) was set on three *workspaces*: `/field/voice`, `/field/deviation`,
`/compliance/audit-pack`. Dropped there, kept on the `[id]`/`[workOrderId]` views. `/login`'s h1
gained `sm:text-hero`; the off-boarding session title (`text-subtitle`, body font) now uses the
display face at `text-title`. `field/voice/page.test.tsx` pins the size so it cannot drift back.
**Rule: `compact` is for per-record views only.**

**Rail collapse.** Collapsing used to *grow* the two blocks above the nav — the brand row restacked
to hold the toggle (56→102px) and the actions row stacked (52→96px) — pushing every icon ~90px
down. Now the toggle lives in the rail foot (beside the account row expanded, under it collapsed:
the foot may grow, it only costs scroll height) and the collapsed rail keeps Search alone
(`[data-rail-ingest]` is hidden; Ingest stays on ⌘K and `/documents`). Both blocks are 56px + 52px
in both states. Measured after: first nav icon at **120px expanded and collapsed**, 0px drift,
no nav overflow at 1440x900 — re-confirmed after the section headings were removed.

**Rail rows are the same height in both states.** Removing the headings was not enough: a row's
height came from its *content*, and hiding the label dropped it from 19.5px (the label's line box)
to 18px (the bare icon). That 1.5px compounded — the last icon landed 20px off its expanded
position — and the collapsed rail also used a smaller section gap (0.5rem vs 1rem), adding 8px per
group boundary. Both are gone: `[data-rail] .rail-link` has a `min-height` floor (2.25rem, 2.125rem
under `max-height: 1020px`) and there is now one section gap for both states. Measured: **0px drift
on every row**, engineer (14) and admin (16 + governor pill), expanded and collapsed, with no nav
overflow at 1440x900. The Governor pill hides when collapsed — "0/6" with no label is a riddle, and
its row is what tipped the collapsed admin rail into scrolling.

**Section headings gone.** `OPERATE / ANALYZE / ASSURE / KNOWLEDGE` were collapsible buttons that
`display:none`'d when the rail collapsed, so the icon column re-flowed on every toggle. Removed,
along with the per-group collapse state. The grouping survives as spacing (`--rail-section-gap`,
raised to 1rem now that ~90px of chrome is gone) and as each list's `aria-label`, and the ⌘K
palette still groups results by the same `NAV` section names. Rail now has ~164px spare at
1440x900 (was 72px).

**Corner ticks.** Removed from `EmptyState` and the login panel — landing decoration, and both were
already broken outside `.landing`: the EmptyState one painted *nothing* (`--lp-accent` is undefined
there, so `.lp-tick--solid`'s background computed to transparent) and the login one rendered a
*white* square (`.sidebar-scope` does not remap `--canvas`). `.lp-tick` stays in `globals.css` for
the landing's own 6 call sites.

**One hover idiom.** `.fill-sweep` in `globals.css`: a `::after` panel scaling from the left over
240ms — the calm reading of the landing's 72-span pixel wipe, with no extra DOM, so icon-only
squares get it too. It fills `--sweep` (`#0b1015`), deliberately **not** `--ink`, which is
near-white in dark mode and would erase the label mid-sweep. Applied to `Button` variants
`primary`/`danger` (replacing `hover:brightness-105`, which *lightened* the accent) and to the new
`ButtonLink` (Next `<Link>` cannot come out of `<Button>`). 16 hand-rolled accent buttons migrated
onto the two primitives, which also fixed two with no hover at all and two that snapped with no
transition. The round record button keeps a colour change — a left-to-right sweep clips oddly on a
circle.

### Follow-up: separators, hover coverage, tile parity ✅ (2026-09-27)
**No more `·` in the workspace** (the landing keeps its own, it is out of scope here). All 25 eyebrows are now the area alone (`Overview`, `Assure`, `Governance`) — the
page title already names the page. The other ~84 in-app dots became commas, except label+value
pairs which lost the separator entirely: `L3 Standard` (`authorityLabel`, feeds every
AuthorityBadge), `Governor active`, `Low confidence 40%`, `Snapshot <date>`, `Read-only <role>`,
`Overrides 7d`, and the datastore names shortened to `Neo4j` / `Qdrant` / `Redis` / `FastAPI`.
The governance loading pill `···` is now `…`. Tests updated with the strings.

**The sweep covers every button.** `ghost` was left out, so secondary actions like *Cross-site
patterns* still did nothing on hover. All three variants sweep now, and `.fill-sweep:hover` flips
`color` to `--on-sweep` (unlayered, so it beats the control's own `text-*` utility) — a ghost
button's ink label has to invert once the ink is under it. Migrated the last hand-rolled
secondaries: the Overview *Cross-site patterns* link, both `/assets` header actions
(`identity-action.tsx`), the nonconformance RCA link.

**The sweep inverts.** `--sweep` is the opposite of its ground, or it disappears into it:
near-black on white, near-white on the dark canvas, and `.sidebar-scope` flips it too — an ink
sweep on the ink rail swallowed the Ingest `+` whole.

**KPI tiles hover the same everywhere.** Overview's tiles were links (so they lifted) while
Governance's were inert. The four Governance tiles now deep-link to their queues
(`/governance/conflicts`, `/quarantine`, `/sla`) and hover identically. Tiles with no destination
stay inert on purpose — a hover that leads nowhere is a lie. Tile height 104px → 96px with tighter
internal spacing; the skeleton follows it (zero layout shift, pinned by `ui-metric.test.tsx`).

### Follow-up: two landing edits ✅ (2026-09-27)
The landing is otherwise out of scope for this document, but two changes were made there on
request: the **Developers** footer column was removed (grid narrowed 3 → 2 columns), and a
**demo player** was added behind a single switch. Paste a YouTube link into `DEMO_YOUTUBE_URL`
(`app/page.tsx`) and the `#demo` section, the header's Demo cell and the hero CTA's in-page scroll
all appear; leave it empty and none of it renders and the CTA keeps leaving for
`DEMO_FALLBACK_URL`. The player is a **facade** — the poster is the page's own `lp-media` panel and
YouTube is contacted only on press (`youtube-nocookie`), so the embed costs nothing on first load.
URL parsing lives in `lib/youtube.ts` with a test over all five link shapes, because a silent
`null` would mean the section simply never appears.

## Guardrails (from CLAUDE.md, unchanged by this plan)
Tokens only, no hex in markup. Tailwind v4 syntax. No new npm deps. `RefusalCard` stays the only
safety-critical surface. Every answer keeps `sources[]` + `AuthorityBadge`. Frontend only: no
backend or data changes.

## Order and size
Phases 1–2 are the leverage (~1 day, visible on every page at once). Phase 3 is mechanical but
wide (~1 day). Phases 4–5 are the polish (~1–2 days). Phase 6–7 ~half a day.
