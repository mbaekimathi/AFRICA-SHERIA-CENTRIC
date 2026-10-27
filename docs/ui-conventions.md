# UI Conventions — Sheria-Centric

Working contract for the "Quiet Luxury Legal" redesign. Extracted from the code
as it exists (Phase 0 audit). Companion doc: `docs/ui-ux-audit.md` (deeper audit).

---

## 1. Stack (confirmed)

- Django 5.0 server-rendered templates (DTL), hand-written CSS, vanilla JS.
- **No** React/Tailwind/bundler/SCSS/CSS-in-JS/animation libs. None may be added.
- Templates: `templates/` (151 `.html` under `accounts/` + `layouts/` + `partials/` + `base.html` + `accounts/firm/`).
- JS: `static/js/` (~50 files), plain scripts with `defer`, listeners on `DOMContentLoaded`, no modules.
- Routing: workspace pages go through ONE catch-all `<slug:role>/<path:pages>/`;
  new workspace pages register in `accounts/workspace.py` (`PAGE_LOCAL_LINKS`,
  `SYSTEM_MODULES`, `SHARED_UTILITY_LINKS`) — **never** in `urls.py`.

## 2. Surfaces and stylesheet load order

| Surface | Layout | CSS (load order) | JS (always loaded) |
|---|---|---|---|
| Employee workspace | `templates/layouts/workspace.html` | `tokens.css` → `app.css` → `motion.css` → `themes-dark.css` → `chrome.css` | toasts, theme-mode, app, live-poll, live-notifications, live-session, live-list, live-entity |
| Client portal | `templates/layouts/client_portal.html` | `tokens.css` → `app.css` → `motion.css` → `themes-dark.css` → `chrome.css` | toasts, theme-mode, app, live-poll, live-session, live-notifications |
| Auth + landing | `templates/base.html` (+ `accounts/home.html` adds `site.css`) | `auth.css` → `partnership-crest.css` → (`site.css` on home) | toasts, theme-mode, auth, live-poll, live-session |
| Public firm site | `templates/accounts/firm/base.html` (extends `base.html`) | `auth.css` → `partnership-crest.css` → `firm_site.css` | toasts, theme-mode, auth, live-poll, live-session, firm_site |

- `chrome.css` **wins over `app.css`** (loads later). It re-radiusses `.btn--primary`
  (999px→10px, `chrome.css:714`), re-themes `.data-table th` (`chrome.css:681`),
  rebuilds `.metric` (`chrome.css:263-649`). Edit the winning file; no `!important` wars.
- `body` classes that drive appearance:
  - Workspace/portal: `class="workspace theme-{key} font-{key} density-{key}"`
  - Auth/landing: `{% block body_class %}` → e.g. `auth-page`, `site-page site-page--landing`
  - Firm site: `site-page site-page--firm` → `.fw-site` wrapper

## 3. Token system

No global token file — four parallel vocabularies:

| File | Anchor | Prefix |
|---|---|---|
| `app.css:1-38` + `:52-128` | `:root` fallbacks + `body.workspace` semantics | `--ink`, `--accent`, `--surface`, `--sidebar-*` |
| `auth.css:1-39` | `:root` | `--purple-50…950`, `--brass`, `--ink` |
| `site.css:3-21` | `:root` | `--lp-*` |
| `firm_site.css:3-23` | `:root` | `--fw-*` |

### Workspace semantic tokens (per theme)

```
--ink --ink-muted --line
--accent --accent-strong --accent-soft
--surface --surface-tint --page-bg
--sidebar-bg --sidebar-ink --sidebar-muted --sidebar-line
--sidebar-hover --sidebar-active --sidebar-active-ink
--danger --danger-bg --danger-line
--success --success-bg --success-line --warning
--notif-badge --notif-badge-ink          (per-theme, app.css:987-1026)
--dot --brand-mark --chrome-accent       (optional per-theme)
--title --heading --kicker --icon --icon-muted --link --focus-ring
--icon-1..7                              (icon tone palette)
```

Aliases kept for older CSS (`body.workspace`, `app.css:120-127`):
`--text --text-muted --bg --surface-2 --border --radius-md --accent-ink`.

### Type scale (`app.css:68-79`)

`--text-xs:.72rem --text-sm:.8125rem --text-base:.9375rem --text-md:1.0625rem`
`--text-lg:1.25rem --text-xl:clamp(1.35rem,1.2rem+.45vw,1.7rem)`
`--leading-tight:1.25 --leading-body:1.55 --leading-loose:1.7`
`--tracking-tight:-.025em --tracking-ui:-.011em --tracking-wide:.07em`

### Density (`app.css:82-89`; overrides `.density-compact|.density-airy` `1029-1064`)

`--density-pad --density-gap --density-scale --density-row-y --density-row-x`
`--density-nav-y --density-nav-x --density-content`

### Radius / shadow / easing

- `--radius-sm:8px --radius:10px --radius-lg:14px`; pills `999px` (ad-hoc radii also exist).
- `--shadow-xs…lg` = `color-mix` on `--ink` (`app.css:19-25`); midnight overrides with black rgba.
- `--ease: cubic-bezier(.22,1,.36,1)` `--ease-out: cubic-bezier(.16,1,.3,1)`.

### NOT tokenized today (Phase 1 adds these)

- Spacing scale (ad-hoc rem values everywhere)
- z-index (observed: 2 nav-badge, 30 backdrop, 40 sidebar/dropdowns, 80 toasts)
- Motion durations (hand-rolled `.15–.3s`)
- Breakpoints (see §6)
- Semantic colors: `--info`, warning bg/line, elevated surface, hairline, glass, skeleton

## 4. Themes

- **40 `.theme-*` classes** (`app.css:162-986`): 8 role/client + 32 studio/accent/modern.
- Each sets the full semantic set shown above; `--notif-badge` is patched per theme at `987-1026`.
- Catalog: `accounts/appearance.py` `THEME_GROUPS` (labels/blurbs for the picker).
- Resolution: personal pick → session snapshot → `CompanyThemeSetting`
  (`resolve_user_workspace_theme`, `appearance.py:291`; clients: `resolve_client_portal_theme`, `:502`).
- Theme previews: `.theme-card--{key}` swatch vars at `app.css:~10060-10140`
  (these intentionally hard-code theme colors — they ARE the theme).
- **Dark mode (Phase 1): every theme now has a derived dark variant** in
  `static/css/themes-dark.css` (generated — do not hand-edit; see §13). Dark
  blocks activate via `html.mode-dark`, set before first paint by an inline
  head script (`localStorage["sc-theme-mode"]` → else `prefers-color-scheme`).
  Toggle: `.mode-toggle[data-mode-toggle]` in both topbars + `theme-mode.js`.
  Smooth color transition via `html.mode-anim` (added after first paint).

## 5. Fonts

- Workspace: `body.font-{key}` → `.font-*` classes set `--font-sans`/`--font-serif`
  (`app.css:7878-7987`). 20 pairings in `appearance.py` `FONT_CATALOG`.
- Only the active pairing is fetched (`google_fonts_stylesheet_href`) via
  `{{ google_fonts_href }}` in the two shell layouts. Theme-settings pages fetch all.
- Auth/base: IBM Plex Sans + Playfair Display. Firm site: Cormorant Garamond + Outfit.
- All Google Fonts via `<link>` + `display=swap`; none self-hosted.

## 6. Breakpoints (canonical set for new work)

Observed ~30 distinct values. Canonical desktop split = **980px** (sidebar
off-canvas below, sticky above; `app.js:14` mirrors `matchMedia("(min-width:980px)")`).

| Token name (docs only — vars can't be used in @media) | Value | Use |
|---|---|---|
| bp-sm | 480px | small phones / single-column forms |
| bp-md | 720px | large phone / small tablet, stacked cards |
| bp-lg | 980px | sidebar rail↔full, topbar condenses |
| bp-xl | 1280px | wide desktop refinements |

Legacy values still in the wild (migrate opportunistically, don't mass-rewrite):
380, 420, 479, 519, 520, 559, 560, 599, 639, 640, 700, 719, 760, 780, 800, 840,
860, 880, 899, 900, 920, 960, 979, 981, 1100, 1101, 1180, 1200.

## 7. Component recipes (restyle in place — markup must keep working)

- **Page**: `<section class="page page--{slug}">` > `.page-intro` (`.page-kicker` + `h2` + `.page-lead`) > `.panel`s. Width mods: `page--centered/--form-narrow/--form-medium/--form-wide` + per-page caps (`app.css:2393-2424, 6786-6831`).
- **Buttons**: `.btn` + `--primary|--danger|--quiet|--warn|--success|--inline|--with-icon|--docs-*`; `.is-loading`+`.btn-spinner`; auth adds `--ghost|--google`. ⚠ THREE radius variants (pill in app.css, 10px in chrome.css, auth pill).
- **Forms**: `.workspace-form|.register-form` > `.form-field` > `label` + input(`.form-input`) + `.field-hint` + `.field-error`; non-field errors `.form-alert[role=alert]`; `novalidate` (server-side validation); required `*` is `aria-hidden`. Sections: `.register-section` + `.register-grid--2`.
- **Panels**: `.panel` > `.panel__head`(`h3`+`.panel__hint`) + `.panel__body`; definition lists `.data-grid` (`dt`/`dd`).
- **Tables**: `.data-table-wrap > .data-table`, `th scope="col"`, `white-space:nowrap` → horizontal scroll wrapper (no mobile card transform today).
- **Status**: `.status-pill status-pill--{key}` — ~15 variants, all hard-coded pastel pairs (`app.css:4576-4700`).
- **Modals**: native `<dialog class="workspace-modal">` + `showModal()`; `aria-labelledby`; 37 dialogs; per-modal bespoke subclasses exist.
- **Toasts**: `partials/messages_toast.html` → `.toast-stack`/`.toast--{type}`; `toasts.js` handles progress bar + pause-on-hover/focus + dismiss (error 7.5s / success 2.2s).
- **Empty state**: `.empty-state` + `__rule/__title/__copy` (~15 pages, not universal).
- **Nav**: `.nav-link` + `.is-active`(inset accent bar) / `.is-disabled`(`aria-disabled`+`tabindex=-1`+`.nav-soon` "Locked"); `.nav-icon`, `.nav-badge`.
- **Topbar**: `.topbar-pill--date/--time/--firm` (hidden <1100px), `.icon-btn`, `.notif-menu`, `.session-menu`, `.profile-menu` dropdowns.
- **Metrics**: `.metric`, `.metrics--dash`, `.metric--glass` (count-up wired in `app.js:365`).
- **Reveal**: `[data-reveal]` + `.is-visible` via IntersectionObserver (`app.js:312`); CSS in `motion.css`/`site.css`. ~59 usages.

## 8. Hard-coded color inventory

| File | hex | rgba() | Notes |
|---|---|---|---|
| `app.css` | ~1,932 | ~172 | bulk is inside `.theme-*` + `.theme-card--*` blocks (legit). Component offenders: `.status-pill--*` pastels (`4576+`), `#fff` input/modal/chip/menu bgs (`2809, 2928, 2946, 3010, 6901`), Google btn (`11636-11638`), `--icon-2..7` (`103-108`). |
| `motion.css` | 107 | 28 | `.icon-3d--*` clay palette + named icon hues (`31-58`). |
| `chrome.css` | 73 | 15 | |
| `auth.css` | 50 | 75 | fixed violet palette (by design, pre-rebrand) |
| `site.css` | 33 | 60 | fixed landing palette |
| `firm_site.css` | 507 | 224 | fixed navy/brass palette |
| `partnership-crest.css` | 27 | 27 | |
| templates | 1 inline `style` hex (`firm/contact.html`) | — | ~104 inline `style=` total, mostly `--stagger` var passing (OK) |

Rule going forward: component CSS uses `var(--token)` or
`color-mix(in srgb, var(--token) N%, …)` only. Hex lives in `.theme-*` blocks,
per-surface `:root` palettes, and theme-preview swatches.

## 9. Icon systems

**Canonical: `templates/partials/icons.html`** — one flat-stroke sprite, 24px
grid, `currentColor`, stroke ~1.7, round caps/joins. Included once per page by
the layouts (`workspace.html`, `client_portal.html`, `base.html`). Usage:
`<svg class="icon" aria-hidden="true"><use href="#i-name"/></svg>` — sizes via
`.icon--sm/.icon--lg/.icon--xl` (tokens.css) or contextual CSS
(`.icon-tile svg`, `.topbar-pill__icon svg`, …).

Two symbol families live in the sprite:
- **Chrome/nav** (`i-home`, `i-menu`, `i-bell`, `i-calendar`, `i-clock`,
  `i-building`, `i-caret`, `i-back`, `i-sun`, `i-moon`, …) — used by the
  layouts' topbar/mobile-bar and the `ICON_*` constants in
  `accounts/workspace.py` (rendered via `{{ icon|safe }}`).
- **Matter/doc browse tiles** (`i-client`, `i-clients`, `i-handshake`,
  `i-briefcase`, `i-bulb`, `i-scroll`, `i-globe`, `i-shield`, `i-search-doc`,
  `i-advice`, `i-folder`, `i-list`, `i-gavel`, `i-scales`, `i-courthouse`,
  `i-land`, `i-document`) — names match `MATTER_CATEGORY_ICON_META` /
  `COURT_RANK_ICON_META` in `views.py`, so `i-{{ icon }}` resolves for every
  value views can pass.

**Tile wrapper**: `.icon-tile` (motion.css) — tone variants `--1…--7` +
`--sm`/`--lg`, optional `.icon-tile--float` (reduced-motion gated). The
legacy partials `accounts/partials/icon_3d.html` and `icon_flat.html` are
kept as thin shims emitting `.icon-tile` + sprite `<use>` so the ~37
existing include sites need no edits; new code should write the tile markup
directly. The old glyph partials (`icon_3d_glyph`, `icon_flat_glyph`,
`icon_3d_profile`) and the whole `.icon-3d*` clay CSS block were removed;
`icon_flat_profile.html` (photo/initials tile) stays — it's a user tile, not
an icon.

**Not icons (intentional artwork, keep)**: `drive_file_icon.html`
(`.drive-file-3d` file-type thumbnails — they depict W/X/P/PDF document
types), the 48px firm-logo `<svg>` in the layouts, `accounts/firm/_icons.html`
(firm site's own 48px-grid set — separate design language), and the ~440
ad-hoc inline `<svg>`s in page templates (charts, illustrations, previews,
brand marks). Migrate an inline SVG only when a sprite symbol is a true
equivalent.

## 10. JS conventions

- One file per feature (`feature-name.js`), loaded via `{% block extra_js %}` `defer`.
- `app.js`: sidebar toggle (<980px drawer + backdrop + Escape), topbar dropdowns
  (click/Escape/outside-click), session clock (1s tick + localStorage active-time),
  `[data-reveal]` IO reveal, `[data-magnetic]` tilt, `.dash-hero` spotlight,
  `.metric--glass` count-up. `reduceMotion` gates all decorative motion.
- `live-poll.js`: `SheriaLivePoll.start({url,onPayload,minMs,maxMs})` — adaptive,
  visibility-aware. Use it; no new `setInterval` pollers.
- `toasts.js`: lifecycle for `[data-toast]` (progress, pause, dismiss).
- `site.js`: landing hero slider + typewriter (motion-gated).

## 11. Cache-bust + misc traps

- Manual `?v=` strings on CSS/JS in templates — **bump every reference when a file
  changes**. Current keys: workspace `app.css?case-name-email-1`, `motion.css?metric-hover-1`,
  `chrome.css?metric-menus-3`; portal `app.css?gen-invoice-tax-1`, `chrome.css?client-portal-chrome-2`;
  base `auth.css?auth-identity-h-2`, `partnership-crest.css?v=9`; home `site.css?landing-hero-pro-2`.
  Firm site uses `{% static_bust %}` (mtime-based — auto).
- `client_portal.html` ≈ 90% duplicate of `workspace.html` — chrome fixes must land
  in BOTH (portal has staff-impersonation banner + theme-settings link; workspace has
  `back_url`, `dashboard_disabled`, `page_nav_items` badges, live-list/entity scripts).
- **`{# #}` is single-line only in Django** — a multi-line `{#` block is NOT
  stripped; it renders as literal text (and any `<svg>` inside it renders too).
  Use `{% comment %}…{% endcomment %}` for multi-line notes.
- `body.auth-page` clips scroll unless content is in `.content-shell` (`auth.css:65-76`).
- Landing nav brand intentionally links to employee login.
- `role="menu"` on `.profile-dropdown`/`.metric-dropdown` without menu keyboard support (known gap).

## 12. Accessibility baseline (preserve)

`<img alt>` everywhere; `th scope="col"`; 37 native `<dialog>`s; `aria-expanded/controls`
on toggles; `aria-disabled`+`tabindex=-1` on locked nav; `prefers-reduced-motion`
in JS + 8 CSS blocks. Gaps: no skip link, no `aria-invalid`/`aria-describedby` on
errors, `role="menu"` misuse, sub-12px type in badges/pills.

---

## 13. Phase 1 foundation (implemented)

### New files

- `static/css/tokens.css` — loads FIRST on workspace/portal. Scales that were
  ad-hoc: `--space-1…10`, `--radius-xs`, `--radius-pill`, `--z-base…toast`,
  `--dur-fast/base/slow/slower`, `--ease-in-out`, `--icon-sm/md/lg`.
  New semantic color roles on `body.workspace`: `--surface-raised`, `--hairline`,
  `--accent-ink`, `--accent-hover`, `--info(-bg/-line)`, `--warning-bg/-line`,
  `--success-ink`, `--danger-ink`, `--warning-ink`, `--info-ink`, `--glass-bg/-line`,
  `--skeleton-base/-shine`, categorical `--cat-1…10` (with dark remaps).
  Primitives: `.icon` (+`--sm/--lg/--xl/--stroke-bold`), `.skeleton`
  (+`.skeleton--line`, shimmer, reduced-motion gated), baseline `:focus-visible`.
- `static/css/themes-dark.css` — GENERATED (40 `html.mode-dark body.theme-*`
  blocks + shared dark semantic/elevation remaps). Never hand-edit:
  `py scripts/generate_dark_themes.py` rebuilds it from app.css.
- `templates/partials/icons.html` — flat-stroke SVG sprite (`<symbol>`s, 24px
  grid, ~1.7 stroke, `currentColor`). Include once per page after the flash
  block; use `<svg class="icon" aria-hidden="true"><use href="#i-name"/></svg>`.
- `static/js/theme-mode.js` — persists `sc-theme-mode` in localStorage,
  wires `[data-mode-toggle]`, follows OS until the user chooses.
- `scripts/generate_dark_themes.py`, `scripts/fix_contrast.py`,
  `scripts/check_contrast.py` — the theme pipeline + AA audit (22 token pairs ×
  40 themes × 2 modes). Order: `fix_contrast` → `generate_dark_themes` → `check_contrast`.

### New/changed conventions

- **Mode flag lives on `<html>`** (`mode-dark`/`mode-light`), set by a 4-line
  inline script in every layout `<head>` BEFORE stylesheet links (no-flash).
- **`--accent-hover` vs `--accent-strong`**: `--accent-strong` is the darkened
  text/link role (light mode) / lifted text role (dark). Button hover bg uses
  `var(--accent-hover, var(--accent-strong))` — light-accent themes define
  `--accent-hover` so dark `--accent-ink` still clears AA.
- **No component hexes**: `app.css`/`chrome.css` interactive surfaces now use
  `var(--surface*)`, `var(--accent-soft)`, `--cat-*`, semantic `*-bg/-line/-ink`.
  Paper-like whites (doc sheets, letterheads, print previews, switch thumbs,
  seals) intentionally remain white — they depict documents, not chrome.
- `theme-midnight`'s own palette = light-mode identity; its `mode-dark` variant
  is generated like the rest.

### Verification status (Phase 1)

- `py scripts/check_contrast.py` → **all 40 themes × 2 modes pass** 22 pairs.
- `py manage.py check` clean; CSS brace balance OK; edited templates parse.

## 14. Phase 2 workspace shell (implemented)

- **Three shell modes**: desktop `>=980px` = full sidebar (sticky, `--sidebar-width`);
  tablet `720-979px` = icon rail (`--sidebar-rail-width`, sticky in-flow, labels
  hidden via `.sidebar:not(.is-open)` rules); mobile `<=719px` = off-canvas
  drawer + `.mobile-bar`.
- **Rail expansion**: the topbar hamburger toggles `.sidebar.is-open`; at rail
  widths the sidebar stays `position:sticky` and only its `width` animates —
  it overlays `.workspace-main` (no reflow, no position swap).
- **`.mobile-bar`** (fixed bottom, `<=719px` only): dark-chrome bar with Home /
  Alerts / Menu. Lives at the end of `.workspace-main` in both layouts; Alerts
  forwards to `#notif-trigger`, Menu drives `setSidebarOpen`, `#mobilebar-badge`
  mirrors `#notif-badge` via MutationObserver in `app.js`. `.app-footer` gets
  `margin-bottom` to clear it.
- **Active nav indicator**: `.nav-link.is-active::before` — a 3px accent bar
  (`--chrome-accent`) at the link's left edge, defined in `chrome.css`
  (the `app.css` `::before` stays `content:none` as the no-chrome fallback).
- **Topbar glass**: translucent `--chrome` + `backdrop-filter: blur(14px)` with
  an `@supports` solid fallback. Sidebar/topbar/mobile-bar share the
  `--chrome*` token family — one dark "frame" in both modes.
- **Page headers**: `.page-intro h2`/`.page h2` use `--font-serif` (serif where
  the font theme has one, sans otherwise); `.page-kicker` has a hairline dash
  `::before`.
- **JS**: `app.js` has `mqDesktop` (980) + `mqDrawer` (719); any boundary
  change closes the sidebar. `setSidebarOpen` syncs `aria-expanded`/labels on
  both `#sidebar-toggle` and `#mobilebar-menu`.
- **`?v=ql-shell-1`**: bumped on `app.css`, `chrome.css`, `app.js` in both
  workspace layouts.

## 15. Phase 3 shared components (implemented)

- **Buttons**: one silhouette — chrome.css sets `.btn { border-radius: var(--radius) }`
  which beats app.css's per-variant `999px` pills (same specificity, later file).
  `.btn:active` presses (scale .985), `:disabled`/`.is-disabled` dim, `.btn:focus-visible`
  gets the 2px + `--focus-ring` halo. `.btn--with-icon svg` sizes to `--icon-sm`.
- **Forms**: inputs are always `font-size: max(16px, …)` — iOS never zooms on
  focus. `::placeholder` = 70% `--ink-muted`; native checkbox/radio/range use
  `accent-color: var(--accent)`; `.field-error` is flex with a small `--danger`
  dot `::before` (rendered only when errors exist, so no [hidden] conflict).
- **Tables**: `th:first-child`/`td:first-child` are `position:sticky; left:0`
  with opaque bgs (chrome.css matches the th/zebra/hover backgrounds so the
  pinned column stays on-brand). **Vertical sticky headers are impossible**
  with `overflow-x:auto` wraps — don't try; the dark chrome `th` is the
  header affordance instead.
- **Mobile card transform**: `.data-table-wrap--cards` OR auto-activated via
  `:has(td[data-label])` — annotate `<td data-label="Column">` in templates to
  opt a table in; thead hides, rows become hairline cards, `td::before` prints
  the label. Cells without `data-label` right-align (action cells).
- **Status pills**: 1px `currentColor` hairline + `.icon` slot at 0.8rem.
- **Modals**: `::backdrop` uses `--scrim` + blur; card fades/scales in
  (no-preference only); <=719px becomes a bottom sheet (full-width, top
  radii, safe-area padding). `.sidebar-backdrop` also uses `--scrim`.
- **Skeletons**: `.skeleton` + `--line/--avatar/--btn/--card` in tokens.css.
- **Empty states**: optional `.empty-state__icon` hairline medallion before the rule.
- **`?v=ql-components-1`** on tokens/app/chrome in both workspace layouts.

## 16. Phase 4 client portal (implemented)

- Portal differentiation is **token-only**: `body.workspace--portal` (added to
  `client_portal.html`) retunes radii (+2px), hairlines (quieter), canvas
  (60% `--surface-tint` blend — keeps each theme's undertone), and shadows
  (softer). Dark mode has its own remap under `html.mode-dark`.
- Density retune applies **only** to `.density-comfortable` — the client's
  compact/airy preference still wins (both on body, portal class would
  otherwise outrank the density class on specificity).
- The portal gets the same Phase 2/3 chrome for free: rail/drawer/mobile-bar,
  cards, tables, pills, modals. Alerts item on `.mobile-bar` renders only
  when `client.status == "active"` (matches the topbar notif gate).
- **`?v=ql-portal-1`** on tokens.css in both layouts.

## 17. Phase 5 auth / landing / firm site (implemented)

- **Mode gating is per-surface via blocks in `base.html`**:
  `{% block mode_init %}` (no-flash script), `{% block mode_toggle %}`
  (floating `.mode-toggle` button), `{% block mode_script %}`
  (`theme-mode.js`). Surfaces opt out by overriding the blocks.
- **Auth pages dark mode**: single `html.mode-dark` block at the end of
  `auth.css` remaps `:root` tokens (`--ink/-muted`, `--surface(-soft)`,
  `--purple-50/100/200/800`, `--border`, shadows, semantic bgs) + a dark
  `.auth-page` gradient. `.auth-brand` stays dark in both modes.
- **Landing light mode**: `site.css` white alphas were rewritten to
  `color-mix(in srgb, var(--lp-ink) N%, transparent)` and violet-dusk
  alphas to `color-mix(--lp-bg-deep)` — they invert automatically.
  `html.mode-light` remaps `--lp-bg/-deep/-elevated`, ink/muted/line, and
  darkens `--lp-violet/-bright/-teal/-orange/-gold` for AA on light.
  The identity-card gradient (`#1a1a38/#080818`) and Google button stay
  dark/white intentionally (brand artwork).
- **`.mode-toggle` on auth/landing**: floating bottom-right circle styled
  in auth.css (self-contained — tokens.css isn't loaded on this surface);
  sun/moon swap + entrance animation duplicated there.
- **Firm site is light-only** (12k lines, 258 hard colors — dark remap is a
  separate project): `firm/base.html` overrides `mode_init` to force
  `mode-light`, empties `mode_toggle` and `mode_script`.
- **Scroll-reveal, hero carousel, typewriter** already existed (`site.js`).
- **`?v=ql-auth-2`** on auth.css (`base.html`) and site.css (`home.html`).
- **Trap fixed post-Phase-5**: a "Client auth extras" section lived in
  `site.css`, but site.css is never loaded on auth pages — `.provider-icon`,
  `.email-provider`, `.manual-login`, `.auth-divider`, `.google-btn-wrap`,
  `.btn--secondary`, `.btn--google`, `.provider-hints`, `.provider-chip`,
  `.auth-switch--muted`, and `.auth-shell--single .avatar--lg` were moved to
  `auth.css`. `.pending-status`, `.client-profile`, `.detail-list` remain in
  site.css as dead rules (no template uses them).

## 18. Phase 6 QA findings + residual debt

**Verified green**
- `py scripts/check_contrast.py` → all 40 themes × 2 modes × 22 pairs pass.
- `py manage.py check` clean; all changed templates parse; CSS braces balanced.
- Skip link added (`.skip-link` → `#main-content`, both workspace layouts).
- Reduced-motion: every new animation is inside a `no-preference` block;
  `mode-anim` transitions also gated now.
- 24 interactive `color:#fff` hazards fixed → `--accent-ink`/`--danger-ink`/
  `--sidebar-*` (incl. `.staff-portal-banner` → chrome tokens).

**Residual debt (page-level polish, safe to leave)**
- ~160 remaining bare hexes in app.css are: letterhead/invoice/SERP preview
  artwork (paper whites — intentional), fixed-hue categorical tiles with
  white text (consistent both modes), `@media print` whites, and scattered
  status hues in page-specific sections. Sweep incrementally when touching
  those pages.
- `motion.css` clay `.icon-3d--*` palette — **removed** (post-Phase-6 icon
  consolidation). Remaining `.icon-orb` hero artwork still has hard-coded
  hues; sweep when touching those heroes.
- Form errors still lack `aria-invalid`/`aria-describedby` wiring;
  `role="menu"` lists lack arrow-key menu behavior; some badge text <12px.
- `data-label` annotation for the mobile card transform: add
  `data-label="Column name"` to `<td>`s in high-traffic tables.
- Firm site dark mode needs a dedicated `--fw-*` remap project.
- No browser-level visual regression was run — do a manual pass at
  360/768/1280 when convenient.
