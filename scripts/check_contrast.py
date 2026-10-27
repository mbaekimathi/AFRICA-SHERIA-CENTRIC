"""Contrast audit — every theme x both modes.

Resolves the effective custom-property values for each of the 40 workspace
themes in light and dark mode, then checks WCAG contrast ratios for the
token pairs components actually rely on.

Sources:
  light  = static/css/tokens.css (:root + body.workspace defaults)
         + static/css/app.css    (:root, body.workspace, .theme-*)
  dark   = light values overridden by
         + static/css/tokens.css (html.mode-dark body.workspace)
         + static/css/themes-dark.css (html.mode-dark body.workspace remaps,
                                       html.mode-dark body.theme-*)

Run:  py scripts/check_contrast.py
Exit code 1 if any required pair fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "static" / "css" / "app.css"
TOK = ROOT / "static" / "css" / "tokens.css"
DARK = ROOT / "static" / "css" / "themes-dark.css"

# (fg token, bg token, underlay token|None, min ratio, label)
PAIRS = [
    ("--ink", "--surface", None, 4.5, "body text on panel"),
    ("--ink", "--page-bg", None, 4.5, "body text on page"),
    ("--ink", "--surface-raised", "--surface", 4.5, "body text on raised"),
    ("--ink-muted", "--surface", None, 4.5, "muted text on panel"),
    ("--ink-muted", "--page-bg", None, 4.5, "muted text on page"),
    ("--link", "--surface", None, 4.5, "link on panel"),
    ("--link", "--page-bg", None, 4.5, "link on page"),
    ("--accent-ink", "--accent", None, 4.5, "primary btn label"),
    ("--accent-ink", "--accent-hover", "--accent-strong", 4.5, "primary btn hover"),
    ("--accent-strong", "--accent-soft", "--surface", 4.5, "accent text on tint"),
    ("--accent", "--surface", None, 3.0, "accent ui on panel"),
    ("--sidebar-ink", "--sidebar-bg", None, 4.5, "sidebar text"),
    ("--sidebar-muted", "--sidebar-bg", None, 3.0, "sidebar muted text"),
    ("--sidebar-ink", "--sidebar-hover", "--sidebar-bg", 4.5, "sidebar text on hover"),
    ("--danger-ink", "--danger", None, 4.5, "danger badge label"),
    ("--success-ink", "--success", None, 4.5, "success badge label"),
    ("--warning-ink", "--warning", None, 4.5, "warning badge label"),
    ("--info-ink", "--info", None, 4.5, "info badge label"),
    ("--danger", "--danger-bg", "--surface", 4.5, "danger pill text"),
    ("--success", "--success-bg", "--surface", 4.5, "success pill text"),
    ("--warning", "--warning-bg", "--surface", 4.5, "warning pill text"),
    ("--info", "--info-bg", "--surface", 4.5, "info pill text"),
]

HEX = re.compile(r"#([0-9a-fA-F]{3,8})\b")
VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)")
MIX = re.compile(
    r"color-mix\(\s*in srgb\s*,\s*(.+?)\s+([\d.]+)%\s*,\s*(.+?)\s*\)$"
)
DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def hex_to_rgb(s: str) -> tuple[float, float, float]:
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))


def parse_decls(block: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in DECL.finditer(block)}


def blocks(css: str, selector_re: str) -> list[tuple[str, str]]:
    """Return [(selector, body)] for rules whose selector matches."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel = m.group(1).strip()
        if re.search(selector_re, sel):
            out.append((sel, m.group(2)))
    return out


def build_maps() -> dict[str, dict[str, dict[str, str]]]:
    """{theme: {'light': {tok: raw}, 'dark': {tok: raw}}}"""
    app = APP.read_text(encoding="utf-8")
    tok = TOK.read_text(encoding="utf-8")
    dark = DARK.read_text(encoding="utf-8")

    base: dict[str, str] = {}
    # :root + body.workspace defaults from both files
    for css in (tok, app):
        for sel, body in blocks(css, r"^:root$|^body\.workspace$"):
            base.update(parse_decls(body))

    themes: dict[str, dict[str, dict[str, str]]] = {}
    for sel, body in blocks(app, r"theme-[a-z_0-9]+"):
        for part in sel.split(","):
            part = part.strip()
            m = re.fullmatch(r"\.theme-([a-z_0-9]+)", part)
            # real theme blocks set the full semantic set; component classes
            # like .theme-card / .theme-admin-* don't
            if not m or "--sidebar-bg" not in body or "--accent" not in body:
                continue
            key = m.group(1)
            themes.setdefault(key, {"light": dict(base), "dark": {}})
            themes[key]["light"].update(parse_decls(body))

    # dark layer: global remaps then per-theme blocks
    dark_base: dict[str, str] = {}
    for css in (tok, dark):
        for sel, body in blocks(css, r"html\.mode-dark body\.workspace$"):
            dark_base.update(parse_decls(body))

    for sel, body in blocks(dark, r"html\.mode-dark body\.theme-"):
        m = re.search(r"theme-([a-z_0-9]+)", sel)
        if not m:
            continue
        key = m.group(1)
        themes.setdefault(key, {"light": dict(base), "dark": {}})
        themes[key]["dark"].update(parse_decls(body))

    # effective dark = light map + dark base + dark theme overrides
    for key, modes in themes.items():
        eff = dict(modes["light"])
        eff.update(dark_base)
        eff.update(modes["dark"])
        modes["dark"] = eff

    return themes


def resolve(
    raw: str, env: dict[str, str], depth: int = 0
) -> tuple[float, float, float, float] | None:
    """Resolve a token value to (r, g, b, alpha). Alpha < 1 = translucent."""
    if depth > 12 or raw is None:
        return None
    raw = raw.strip()
    m = HEX.fullmatch(raw)
    if m:
        return (*hex_to_rgb(m.group(1)[:6]), 1.0)
    m = re.fullmatch(
        r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+)(%?)\s*)?\)",
        raw,
    )
    if m:
        a = 1.0
        if m.group(4) is not None:
            a = float(m.group(4)) / (100.0 if m.group(5) else 1.0)
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)), a)
    m = VAR.fullmatch(raw)
    if m:
        tok, fallback = m.group(1), m.group(2)
        if tok in env:
            return resolve(env[tok], env, depth + 1)
        return resolve(fallback, env, depth + 1) if fallback else None
    m = MIX.fullmatch(raw)
    if m:
        a_raw, pct, b_raw = m.group(1), float(m.group(2)), m.group(3)
        a = resolve(a_raw, env, depth + 1)
        b = (
            resolve(env.get("--surface", "#ffffff"), env, depth + 1)
            if b_raw.strip() == "transparent"
            else resolve(b_raw, env, depth + 1)
        )
        if a is None or b is None:
            return None
        t = pct / 100.0
        rgb = tuple(a[i] * t + b[i] * (1 - t) for i in range(3))
        alpha = a[3] * t + b[3] * (1 - t)
        if b_raw.strip() == "transparent":
            alpha = a[3] * t
        return (*rgb, alpha)
    m = HEX.search(raw)
    if m:
        return (*hex_to_rgb(m.group(1)[:6]), 1.0)
    return None


def over(fg: tuple[float, float, float, float], bg_rgb) -> tuple[float, float, float]:
    a = fg[3]
    return tuple(fg[i] * a + bg_rgb[i] * (1 - a) for i in range(3))


def lum(rgb) -> float:
    def ch(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg) -> float:
    l1, l2 = sorted((lum(fg), lum(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def main() -> int:
    themes = build_maps()
    if len(themes) != 40:
        print(f"expected 40 themes, resolved {len(themes)}")
        return 1

    fails: list[str] = []
    warns: list[str] = []
    for key in sorted(themes):
        for mode in ("light", "dark"):
            env = themes[key][mode]
            for fg_tok, bg_tok, under_tok, min_r, label in PAIRS:
                fg = resolve(env.get(fg_tok, ""), env)
                bg = resolve(env.get(bg_tok, ""), env)
                under = (
                    resolve(env.get(under_tok, ""), env)
                    if under_tok
                    else resolve(env.get("--surface", "#ffffff"), env)
                )
                if fg is None or bg is None or under is None:
                    warns.append(
                        f"{key}/{mode}: unresolved {fg_tok}/{bg_tok}/{under_tok} ({label})"
                    )
                    continue
                bg_rgb = over(bg, under[:3]) if bg[3] < 1.0 else bg[:3]
                fg_rgb = over(fg, bg_rgb) if fg[3] < 1.0 else fg[:3]
                r = ratio(fg_rgb, bg_rgb)
                if r < min_r:
                    fails.append(
                        f"{key:>16}/{mode:<5} {label:<24} {r:5.2f} < {min_r:.1f}  "
                        f"({fg_tok} on {bg_tok})"
                    )

    for w in warns:
        print("WARN ", w)
    if fails:
        print(f"\n{len(fails)} contrast failures:")
        for f in fails:
            print("FAIL ", f)
        return 1
    print(f"All {len(themes)} themes x 2 modes pass ({len(PAIRS)} pairs each).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
