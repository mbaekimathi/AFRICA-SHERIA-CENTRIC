"""Generate static/css/themes-dark.css from the light .theme-* blocks in app.css.

Each theme's dark variant is derived from that theme's own sidebar palette, so
the dark canvas keeps the theme's undertone instead of falling back to a generic
gray. Accents are lifted until they clear a minimum contrast bar against the
dark surface; badge ink flips to dark when white fails WCAG AA.

Regenerate:  py scripts/generate_dark_themes.py
"""
from __future__ import annotations

import colorsys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_CSS = ROOT / "static" / "css" / "app.css"
OUT_CSS = ROOT / "static" / "css" / "themes-dark.css"

THEME_RE = re.compile(r"^\.theme-([a-z_0-9]+)\s*\{\s*$")
INLINE_RE = re.compile(r"^\.theme-([a-z_0-9]+)\s*\{(.*)\}\s*$")
VAR_RE = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*(.+?);?\s*$")
INLINE_VAR_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+)")

# Valid theme keys from accounts/appearance.py THEME_GROUPS (+ the product shell).
VALID_THEMES = {
    "product", "firm_admin", "managing_partner", "advocate", "intern",
    "it_support", "employee", "client", "midnight", "graphite", "cedar",
    "cobalt", "olive", "copper", "arctic", "espresso", "jade", "marine",
    "sunrise", "citrus", "azure", "emerald", "saffron", "flamingo",
    "electric", "ruby", "lime", "orchid", "violet_glow", "teal_matter",
    "orange_brief", "rose_seal", "blue_docket", "verdant_leaf",
    "amethyst_file", "indigo_list", "ember_court", "fuchsia_client",
    "cyan_harbor", "blush_advice",
}


def parse_themes(css: str) -> dict[str, dict[str, str]]:
    themes: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in css.splitlines():
        inline = INLINE_RE.match(line)
        if inline and inline.group(1) in VALID_THEMES:
            name = inline.group(1)
            themes.setdefault(name, {})
            for var, val in INLINE_VAR_RE.findall(inline.group(2)):
                themes[name][var] = val.strip()
            continue
        m = THEME_RE.match(line)
        if m and m.group(1) in VALID_THEMES:
            current = m.group(1)
            themes.setdefault(current, {})
            continue
        if current:
            if line.strip() == "}":
                current = None
                continue
            v = VAR_RE.match(line)
            if v:
                themes[current][v.group(1)] = v.group(2).rstrip(";")
    return themes


# ---------- color helpers (stdlib only) ----------

def hex_to_rgb(value: str) -> tuple[float, float, float]:
    h = value.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


def hls(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    return colorsys.rgb_to_hls(*rgb)


def from_hls(h: float, l: float, s: float) -> tuple[float, float, float]:
    return colorsys.hls_to_rgb(h, min(max(l, 0.0), 1.0), min(max(s, 0.0), 1.0))


def scale_light(rgb, factor: float, lift: float = 0.0) -> tuple[float, float, float]:
    h, l, s = hls(rgb)
    return from_hls(h, l * factor + lift, s)


def luminance(rgb) -> float:
    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def is_hex(value: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{3,8}", value.strip()))


def lift_to_contrast(color, bg, target: float, cap_l: float = 0.8):
    """Raise lightness until `color` reaches `target` contrast on `bg`."""
    h, l, s = hls(color)
    rgb = color
    while contrast(rgb, bg) < target and l < cap_l:
        l += 0.02
        rgb = from_hls(h, l, s)
    return rgb


# ---------- derivation ----------

OPTIONAL_VARS = ("--brand-mark", "--chrome-accent")
INK_ALIAS_VARS = ("--title", "--heading")


DARK_INK = (20 / 255, 20 / 255, 24 / 255)  # #141418
WHITE = (1.0, 1.0, 1.0)


def mix(a, b, t: float):
    return tuple(a[i] * t + b[i] * (1 - t) for i in range(3))


def derive_dark(name: str, t: dict[str, str]) -> list[str]:
    shell = hex_to_rgb(t["--sidebar-bg"])
    page = scale_light(shell, 0.68)
    surface = scale_light(shell, 1.0, 0.028)
    tint = scale_light(surface, 1.0, 0.045)
    raised = scale_light(surface, 1.0, 0.075)
    sidebar = scale_light(shell, 0.6)

    accent = hex_to_rgb(t["--accent"])
    # lift accent until usable on the dark surface (UI component bar: 3:1)
    accent = lift_to_contrast(accent, surface, target=3.3)
    h, l, s = hls(accent)
    accent_strong = from_hls(h, min(l + 0.11, 0.88), s)

    # accent-strong must also read as text on the accent tint
    soft = mix(accent, surface, 0.16)
    accent_strong = lift_to_contrast(accent_strong, soft, target=4.7, cap_l=0.92)

    # text drawn directly on the accent (primary buttons) — check BOTH
    # accent and accent-strong; mid-luminance accents may need the accent
    # itself nudged before either ink clears AA.
    def best_ink(acc, st):
        w = min(contrast(WHITE, acc), contrast(WHITE, st))
        d = min(contrast(DARK_INK, acc), contrast(DARK_INK, st))
        return (WHITE if w >= d else DARK_INK), max(w, d)

    accent_ink, score = best_ink(accent, accent_strong)
    guard = 0
    while score < 4.5 and guard < 30:
        guard += 1
        # dark ink wants lighter accents; white ink wants darker accents
        if accent_ink == DARK_INK:
            accent = lift_to_contrast(accent, DARK_INK, 4.55, cap_l=0.95)
            accent_strong = lift_to_contrast(accent_strong, DARK_INK, 4.55, cap_l=0.95)
        else:
            h, l, s = hls(accent)
            while contrast(WHITE, accent) < 4.55 and l > 0.05:
                l -= 0.02
                accent = from_hls(h, l, s)
            h, l, s = hls(accent_strong)
            while contrast(WHITE, accent_strong) < 4.55 and l > 0.05:
                l -= 0.02
                accent_strong = from_hls(h, l, s)
        accent_ink, score = best_ink(accent, accent_strong)

    badge = t.get("--notif-badge")
    badge_ink = None
    if badge and is_hex(badge):
        badge_rgb = hex_to_rgb(badge)
        badge_ink = "#141418" if contrast(DARK_INK, badge_rgb) >= 4.5 else "#ffffff"

    lines = [
        f"html.mode-dark body.theme-{name} {{",
        f"  --ink: {t['--sidebar-ink']};",
        f"  --ink-muted: {t['--sidebar-muted']};",
        "  --line: rgba(255, 255, 255, 0.10);",
        "  --hairline: rgba(255, 255, 255, 0.065);",
        f"  --accent: {rgb_to_hex(accent)};",
        f"  --accent-strong: {rgb_to_hex(accent_strong)};",
        "  --accent-soft: color-mix(in srgb, var(--accent) 16%, var(--surface));",
        f"  --accent-ink: {rgb_to_hex(accent_ink)};",
        f"  --link: {rgb_to_hex(accent_strong)};",
        f"  --surface: {rgb_to_hex(surface)};",
        f"  --surface-tint: {rgb_to_hex(tint)};",
        f"  --surface-raised: {rgb_to_hex(raised)};",
        f"  --page-bg: {rgb_to_hex(page)};",
        f"  --sidebar-bg: {rgb_to_hex(sidebar)};",
        f"  --sidebar-ink: {t['--sidebar-ink']};",
        f"  --sidebar-muted: {t['--sidebar-muted']};",
        "  --sidebar-line: rgba(255, 255, 255, 0.08);",
        "  --sidebar-hover: rgba(255, 255, 255, 0.06);",
        "  --sidebar-active: color-mix(in srgb, var(--accent) 22%, transparent);",
        f"  --sidebar-active-ink: {t['--sidebar-ink']};",
        "  --dot: var(--accent);",
    ]
    for var in OPTIONAL_VARS:
        if var in t:
            lines.append(f"  {var}: var(--accent);")
    for var in INK_ALIAS_VARS:
        if var in t:
            lines.append(f"  {var}: var(--ink);")
    if "--kicker" in t:
        lines.append("  --kicker: var(--accent);")
    if badge_ink:
        lines.append(f"  --notif-badge-ink: {badge_ink};")
    lines.append("}")
    return lines


def semantic(hexv: str, pct: float, worst_surface) -> str:
    """Lift a semantic color until it clears AA on its own tint over the
    lightest dark surface (worst case for light text on tinted bg)."""
    rgb = hex_to_rgb(hexv)
    bg = mix(rgb, worst_surface, pct)
    return rgb_to_hex(lift_to_contrast(rgb, bg, target=4.75, cap_l=0.92))


def main() -> None:
    themes = parse_themes(APP_CSS.read_text(encoding="utf-8"))
    order = list(themes)
    if len(order) != 40:
        raise SystemExit(f"expected 40 themes, parsed {len(order)}: {order}")

    # semantic colors are shared — tune them against the lightest surface
    surfaces = [
        scale_light(hex_to_rgb(t["--sidebar-bg"]), 1.0, 0.028) for t in themes.values()
    ]
    worst = max(surfaces, key=luminance)

    out = [
        "/* ============================================================",
        "   GENERATED by scripts/generate_dark_themes.py - do not edit.",
        "   Dark variants of every .theme-* block in app.css.",
        "   Activated by html.mode-dark (set before first paint by the",
        "   inline script in the layout heads).",
        "   ============================================================ */",
        "",
        "html.mode-dark {",
        "  color-scheme: dark;",
        "}",
        "",
        "/* Semantic state + elevation remaps shared by all dark themes.",
        "   Colors derive from the active theme's tokens, so each theme",
        "   keeps its own undertone. */",
        "html.mode-dark body.workspace {",
        f"  --danger: {semantic('#f0836f', 0.15, worst)};",
        "  --danger-bg: color-mix(in srgb, var(--danger) 15%, var(--surface));",
        "  --danger-line: color-mix(in srgb, var(--danger) 34%, transparent);",
        f"  --success: {semantic('#63c98f', 0.14, worst)};",
        "  --success-bg: color-mix(in srgb, var(--success) 14%, var(--surface));",
        "  --success-line: color-mix(in srgb, var(--success) 32%, transparent);",
        f"  --warning: {semantic('#e0a458', 0.15, worst)};",
        "  --warning-bg: color-mix(in srgb, var(--warning) 15%, var(--surface));",
        "  --warning-line: color-mix(in srgb, var(--warning) 34%, transparent);",
        f"  --info: {semantic('#7cb3f2', 0.15, worst)};",
        "  --info-bg: color-mix(in srgb, var(--info) 15%, var(--surface));",
        "  --info-line: color-mix(in srgb, var(--info) 34%, transparent);",
        "  --focus-ring: color-mix(in srgb, var(--accent) 45%, transparent);",
        "  --shadow-color: #000000;",
        "  --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.4);",
        "  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.36), 0 6px 16px rgba(0, 0, 0, 0.4);",
        "  --shadow-md: 0 8px 24px rgba(0, 0, 0, 0.48);",
        "  --shadow-lg: 0 8px 16px rgba(0, 0, 0, 0.44), 0 24px 48px rgba(0, 0, 0, 0.52);",
        "}",
        "",
    ]

    for name in order:
        out.extend(derive_dark(name, themes[name]))
        out.append("")

    OUT_CSS.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {OUT_CSS} ({len(order)} dark theme blocks)")


if __name__ == "__main__":
    main()
