"""WCAG contrast check for the app's colour tokens, read straight from styles.css.

python3 replica/tools/contrast.py frontend/src/styles.css
Checks every pair below in light and dark. Text pairs need 4.5:1 (AA), UI graphics
(port dots, icon tiles, focus rings) need 3:1. Exit 1 on any failure.
"""
import re, sys

TEXT = [("text", "bg"), ("text", "surface"), ("text-2", "surface"), ("text-2", "surface-2"),
        ("text-3", "surface"), ("text-3", "bg"), ("accent-text", "accent"), ("accent-strong", "accent-soft"),
        ("accent-strong", "surface"), ("danger", "surface"), ("danger", "danger-soft"), ("text-2", "bg")]
GRAPHIC = [("accent", "surface"), ("border-strong", "surface"), ("ok", "surface"), ("warn", "surface")]
PORTS = ["Message", "Text", "Data", "LanguageModel", "Embeddings", "Tool", "Skill"]


def blocks(css):
    light = re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)
    dark = re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\}', css, re.S).group(1)
    parse = lambda b: dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", b))
    L = parse(light)
    return L, {**L, **parse(dark)}


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


css = open(sys.argv[1] if len(sys.argv) > 1 else "frontend/src/styles.css").read()
fails = 0
for mode, t in zip(("light", "dark"), blocks(css)):
    rows = [(f, b, 4.5) for f, b in TEXT] + [(f, b, 3.0) for f, b in GRAPHIC] + [(f"t-{p}", "canvas", 3.0) for p in PORTS]
    for f, b, need in rows:
        if f not in t or b not in t:
            continue
        r = ratio(t[f], t[b])
        ok = r >= need
        fails += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {mode:5} {f:>16} on {b:<12} {t[f]} / {t[b]}  {r:5.2f} (need {need})")
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
