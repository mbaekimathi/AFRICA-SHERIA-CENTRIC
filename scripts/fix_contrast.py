"""Nudge light-mode theme tokens in app.css until the contrast audit passes.

Operates on the 40 `.theme-*` blocks: darkens --ink-muted / --accent /
--accent-strong the minimum amount needed, and picks an --accent-ink
(white or theme-tinted dark) that clears AA on both --accent and
--accent-strong. Only touches token declarations — never component rules.

Run BEFORE generate_dark_themes.py (dark accents derive from these):
  py scripts/fix_contrast.py && py scripts/generate_dark_themes.py
"""
from __future__ import annotations

import colorsys
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_contrast import APP, TOK, build_maps, resolve, ratio  # noqa: E402

DARK_INK = (20, 20, 24)  # #141418 — 0-255 scale, same as resolve() output
WHITE = (255, 255, 255)


def hls(rgb):
    return colorsys.rgb_to_hls(*(c / 255 for c in rgb))


def from_hls(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h, min(max(l, 0), 1), min(max(s, 0), 1))
    return (round(r * 255), round(g * 255), round(b * 255))


def to_hex(rgb):
    return "#" + "".join(f"{int(c):02x}" for c in rgb)


def darker(rgb, step):
    h, l, s = hls(rgb)
    return from_hls(h, l - step, s)


def lighter(rgb, step):
    h, l, s = hls(rgb)
    return from_hls(h, l + step, s)


def lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def fix_theme(env: dict[str, str]) -> dict[str, str]:
    """Return {token: new hex value} that must change in this theme block."""
    patch: dict[str, str] = {}

    def rgb(tok):
        v = resolve(env.get(tok, ""), env)
        return v[:3] if v else None

    def get(tok):
        return patch.get(tok, env.get(tok, ""))

    # --ink-muted: darken until 4.55 on both surface and page-bg
    muted, surf, page = rgb("--ink-muted"), rgb("--surface"), rgb("--page-bg")
    if muted and surf and page:
        orig = muted
        while min(ratio(muted, surf), ratio(muted, page)) < 4.55:
            new = darker(muted, 0.03)
            if new == muted:
                break
            muted = new
        if muted != orig:
            patch["--ink-muted"] = to_hex(muted)

    # --accent on --surface >= 3.05 (UI components)
    accent, surf = rgb("--accent"), rgb("--surface")
    if accent and surf:
        orig = accent
        while ratio(accent, surf) < 3.05:
            new = darker(accent, 0.02)
            if new == accent:
                break
            accent = new
        if accent != orig:
            patch["--accent"] = to_hex(accent)

    # --accent-strong doubles as --link text on surface/page-bg and as
    # accent text on --accent-soft tints — hold it to 4.7 for margin.
    strong, soft = rgb("--accent-strong"), rgb("--accent-soft")
    surf, page = rgb("--surface"), rgb("--page-bg")
    if strong and soft and surf and page:
        orig = strong
        while min(ratio(strong, soft), ratio(strong, surf), ratio(strong, page)) < 4.7:
            new = darker(strong, 0.02)
            if new == strong:
                break
            strong = new
        if strong != orig:
            patch["--accent-strong"] = to_hex(strong)

    # --accent-ink + --accent-hover:
    #   ink must clear AA on --accent AND on the button hover bg.
    #   --accent-strong is the darkened text/link role — it stays dark, so a
    #   light accent can't reuse it as hover bg; dark-ink themes get their
    #   own slightly-darkened --accent-hover instead.
    env_acc = dict(env)
    env_acc.update(patch)
    accent = rgb("--accent") if "--accent" not in patch else resolve(patch["--accent"], env_acc)[:3]
    strong = rgb("--accent-strong") if "--accent-strong" not in patch else resolve(patch["--accent-strong"], env_acc)[:3]
    if accent and strong:
        def hover_for(cand_ink, acc, st):
            # hover bg that keeps cand_ink readable; white ink -> dark strong,
            # dark ink -> lightly darkened accent (bounded so ink still passes)
            if cand_ink == WHITE:
                return st
            hv = darker(acc, 0.07)
            while ratio(cand_ink, hv) < 4.6:
                hv = lighter(hv, 0.01)
            return hv

        w_hov = hover_for(WHITE, accent, strong)
        d_hov = hover_for(DARK_INK, accent, strong)
        w = min(ratio(WHITE, accent), ratio(WHITE, w_hov))
        d = min(ratio(DARK_INK, accent), ratio(DARK_INK, d_hov))
        if w >= 4.5 and w >= d:
            ink = None  # default #fff + --accent-strong hover already works
        elif d >= 4.5 and d > w:
            ink = DARK_INK
            patch["--accent-hover"] = to_hex(d_hov)
        else:
            # mid-luminance accent: move --accent toward the nearer side —
            # white ink wants accent lum <= 0.183, dark ink wants >= 0.255.
            la = lum(accent)
            if abs(la - 0.183) <= abs(la - 0.255):
                while ratio(WHITE, accent) < 4.55:
                    accent = darker(accent, 0.015)
                ink = WHITE
            else:
                while ratio(DARK_INK, accent) < 4.55:
                    accent = lighter(accent, 0.015)
                ink = DARK_INK
                patch["--accent-hover"] = to_hex(hover_for(DARK_INK, accent, strong))
            patch["--accent"] = to_hex(accent)
        if ink is not None:
            patch["--accent-ink"] = to_hex(ink)

    return patch


def main() -> int:
    themes = build_maps()
    css = APP.read_text(encoding="utf-8")
    lines = css.splitlines(keepends=True)

    # locate each .theme-X block's line span
    block_re = re.compile(r"^\.theme-([a-z_0-9]+)\s*\{")
    spans: dict[str, list[int]] = {}
    cur = None
    for i, line in enumerate(lines):
        if "{" in line and "}" in line:
            continue  # single-line rules (e.g. --notif-badge) aren't blocks
        m = block_re.match(line)
        if m and m.group(1) in themes:
            cur = m.group(1)
            spans[cur] = [i, i]
            continue
        if cur is not None:
            if line.strip() == "}":
                spans[cur][1] = i
                cur = None

    changed = 0
    # bottom-up: splicing a block shifts line numbers of everything below,
    # so apply patches from the last block to the first
    for name, span in sorted(spans.items(), key=lambda kv: -kv[1][0]):
        env = themes[name]["light"]
        patch = fix_theme(env)
        if not patch:
            continue
        start, end = span
        body = lines[start : end + 1]
        have = set()
        for j, line in enumerate(body):
            dm = re.match(r"^(\s*)(--[\w-]+)\s*:", line)
            if dm and dm.group(2) in patch:
                body[j] = f"{dm.group(1)}{dm.group(2)}: {patch[dm.group(2)]};\n"
                have.add(dm.group(2))
        # append tokens the block doesn't declare (e.g. --accent-ink)
        missing = [t for t in patch if t not in have]
        if missing:
            add = [f"  {t}: {patch[t]};\n" for t in missing]
            body = body[:-1] + add + body[-1:]
        lines[start : end + 1] = body
        changed += 1
        print(f"{name}: " + ", ".join(f"{k}={v}" for k, v in sorted(patch.items())))

    APP.write_text("".join(lines), encoding="utf-8")
    print(f"\npatched {changed} theme blocks in app.css")
    return 0


if __name__ == "__main__":
    sys.exit(main())
