# AGENTS.md — Sheria-Centric

Guidance for AI coding agents working in this repository. Read this before touching front-end code.

## What the front end is

**Django 5.0 server-rendered templates + hand-written CSS + vanilla JS.** There is
NO React, Vue, HTMX, Tailwind, SCSS, bundler, or component library. Do not add one
without explicit approval — match the existing pattern instead.

- Templates: Django template language in `templates/` (~160 files, `.html`)
- Styles: plain CSS in `static/css/`, BEM-ish naming (`.panel__head`, `.btn--primary`, `.is-active`)
- Scripts: plain JS files in `static/js/` (~50 files), loaded per page via `{% block extra_js %}`, `defer`, no modules/imports — scripts attach listeners on `DOMContentLoaded`
- Icons: inline stroke SVGs; nav/module icons are SVG strings in `accounts/workspace.py` (`ICON_*` constants) injected with `{{ icon|safe }}`
- Fonts: Google Fonts via `<link>` in the layout head

## The three surfaces (different design languages)

| Surface | Layout | Stylesheet(s) | Palette |
|---|---|---|---|
| Employee workspace | `templates/layouts/workspace.html` | `app.css` + `motion.css` + `chrome.css` | Themed per user (`body.workspace.theme-*`) |
| Client portal | `templates/layouts/client_portal.html` | same three files | Same theme system (`theme-client` default) |
| Auth & landing | `templates/base.html` | `auth.css` + `partnership-crest.css` (+ `site.css` for `home.html`) | Fixed violet (`--purple-*`) |
| Public firm site | `templates/accounts/firm/base.html` | `firm_site.css` | Fixed navy/brass (`--fw-*`) |

⚠ `workspace.html` and `client_portal.html` are ~90% duplicated markup — fix chrome bugs in BOTH.

## Design tokens

Tokens are CSS custom properties defined per surface — there is no global token file.

- Workspace: `app.css:1-38` (`:root` fallbacks) + `app.css:52-128` (`body.workspace` semantics) + 40 `.theme-*` classes (`app.css:162-986`). Semantic tokens: `--ink`, `--ink-muted`, `--line`, `--surface`, `--surface-tint`, `--page-bg`, `--accent`, `--accent-strong`, `--accent-soft`, `--link`, `--focus-ring`, `--danger`, `--success`, `--sidebar-*`, `--notif-badge`.
- Type scale: `--text-xs…xl`, `--leading-*`, `--tracking-*` (`app.css:68-79`).
- Radii: `--radius-sm:8px`, `--radius:10px`, `--radius-lg:14px`, pills `999px`.
- Shadows: `--shadow-xs…lg` (color-mix derived).
- Density: `--density-pad/gap/row-*/nav-*/content` overridden by `.density-compact|.density-airy`.
- Theme/font/density catalogs live in `accounts/appearance.py`; user prefs stored on `Employee.ui_theme/ui_font/ui_density`.
- **Not tokenized**: spacing scale (ad-hoc rem values), z-index (2/30/40/80), breakpoints (~20 scattered values — canonical desktop split is 980px; 720/640 are the common smaller ones).

Rules: use `var(--token)` or `color-mix(in srgb, var(--token) N%, …)` — never hard-code hex in workspace CSS (breaks the 40 themes). Dark theme (`theme-midnight`) exists — no hard `#fff` backgrounds.

## Component conventions

- **Buttons**: `.btn` + `--primary|--danger|--quiet|--warn|--success|--inline|--with-icon`. Loading = `.is-loading` + `.btn-spinner`.
- **Forms**: `.workspace-form` (or `.register-form`) > `.form-field` > `label` + `{{ form.field }}` (widgets already carry `.form-input` from `forms.py`) + `.field-hint` + `.field-error`; non-field errors in `.form-alert` `role="alert"`. Forms use `novalidate` — validation is server-side. Required marker: `<span aria-hidden="true">*</span>`. Sectioned forms use `.register-section` + `.register-grid--2`.
- **Cards/panels**: `.panel` > `.panel__head` (h3 + `.panel__hint`) + `.panel__body`; definition lists use `.data-grid` (`dt`/`dd`).
- **Tables**: `.data-table-wrap > .data-table` with `scope="col"` on every `th`.
- **Modals**: native `<dialog class="workspace-modal">` + `showModal()` JS; `aria-labelledby` required.
- **Toasts**: Django `messages` → `templates/partials/messages_toast.html` → `.toast-stack`, auto-dismiss (`toasts.js`).
- **Empty states**: `.empty-state` + `__rule/__title/__copy`.
- **Page recipe**: `<section class="page page--*">` > `.page-intro` (`.page-kicker` + `h2` + `.page-lead`) > `.panel`s. Width modifiers: `page--centered`, `--form-narrow`, `--form-medium`, `--form-wide`.
- **Status**: `.status-pill status-pill--{status_key}`; locked nav items use `.nav-link.is-disabled` + `aria-disabled` + `tabindex="-1"` + `<em class="nav-soon">Locked</em>`.

## JS conventions

- `app.js` — sidebar toggle, topbar dropdowns (click/Escape/outside-click), session clock, reveal animations (`data-reveal`), `prefers-reduced-motion` respected via `reduceMotion`.
- `live-poll.js` — `SheriaLivePoll.start({url, onPayload, minMs, maxMs})`: adaptive fetch polling, pauses on hidden tab. Use it for live data — don't write new `setInterval` pollers.
- `live-notifications.js`, `live-list.js`, `live-entity.js`, `live-session.js` — loaded on every workspace page.
- Feature JS follows `feature-name.js` naming, one file per page, loaded via `{% block extra_js %}`.

## Routing / pages

- Public + auth + client routes: explicit `path()` in `accounts/urls.py`.
- **All workspace pages go through one catch-all**: `path("<slug:role>/<path:pages>/", views.WorkspaceView…)`. Page slugs, sidebar links, and icons are declared in `accounts/workspace.py` (`PAGE_LOCAL_LINKS`, `SYSTEM_MODULES`, `SHARED_UTILITY_LINKS`). To add a workspace page: add the slug to the right link group + handle it in the view — don't add a `path()`.
- Status flow: signup → `pending_approval` (About Work page, locked nav) → `active` (role dashboard) → `suspended` (forced logout + modal).

## Accessibility baseline (keep it)

- Every `<img>` needs `alt` (`alt=""` for decorative).
- `th` needs `scope="col"`. Decorative SVGs/icons: `aria-hidden="true"`.
- Icon-only buttons need `aria-label`. Toggle buttons need `aria-expanded`/`aria-pressed` + `aria-controls`.
- Known gaps to fix when touching related code: no `aria-invalid`/`aria-describedby` on form errors, no skip link, `role="menu"` used on link-lists without menu keyboard support.

## Gotchas

- `chrome.css` loads AFTER `app.css` and overrides `.btn--primary` (10px not pill), `.data-table th`, `.metric` — check both files before styling those.
- `body.auth-page` clips scrolling (`overflow:hidden`) unless content is wrapped in `.content-shell` (`auth.css:65-76`).
- CSS/JS versions are manual `?v=` strings in templates — bump them when you change a file.
- Landing nav brand links to employee login intentionally.
- Cache-bust helper: `{% load static firm_media %}` + `{% static_bust %}` on the firm site.

## Repo layout

```
accounts/           # single Django app — models.py, views.py (22k lines), forms.py,
                    # workspace.py (nav registry + context), appearance.py (themes)
config/             # settings.py, urls.py, db_bootstrap.py (auto-creates MySQL DB)
templates/          # base.html, layouts/, accounts/ (all pages), accounts/firm/ (public site)
templates/partials/ # messages_toast, access_denied_modal
static/css|js|img/  # front-end assets
manage.py           # py manage.py runserver (needs MySQL running, e.g. XAMPP)
docs/ui-ux-audit.md # full front-end audit (read for deeper detail)
```

## Run / verify

- `py manage.py runserver` → http://127.0.0.1:8000/ (auto-migrates; MySQL must be up)
- Tests: `py manage.py test accounts` (or a single `test_*` file)
- No lint/build/typecheck for front-end code exists.
