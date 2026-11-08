"""Find anything of the original left in the codebase.

python3 replica/tools/sweep.py . --config replica/brand.json
python3 replica/tools/sweep.py . --avoid "Name,Company" --domains name.com --colors "#7528FC"

Searches file contents and file names (case-insensitive, also inside identifiers such
as NameEmbed or name_client) for avoided names and domains, and flags exact or near
copies of the original's brand colours (RGB distance < 40). Skips dependencies, build
output, git and the replica/ planning folder. Exit 1 if anything is found.
"""
import argparse, json, os, re, sys

SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "dist", "build", "static", "replica", "__pycache__", ".pytest_cache", "test-results"}
TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".jsx", ".json", ".css", ".html", ".md", ".toml", ".yml", ".yaml", ".txt", ".svg", ".sql", ".cfg", ".ini", ""}

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("--config")
ap.add_argument("--avoid", default="")
ap.add_argument("--domains", default="")
ap.add_argument("--colors", default="")
a = ap.parse_args()
cfg = json.load(open(a.config)) if a.config else {}
avoid = [x.strip() for x in (cfg.get("avoid") or a.avoid.split(",")) if x.strip()]
domains = [x.strip() for x in (cfg.get("domains") or a.domains.split(",")) if x.strip()]
colors = [x.strip().lower() for x in (cfg.get("colors") or a.colors.split(",")) if x.strip()]

def rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def near(h):
    try:
        c = rgb(h)
    except ValueError:
        return None
    for o in colors:
        d = sum((x - y) ** 2 for x, y in zip(c, rgb(o))) ** 0.5
        if d < 40:
            return o, round(d)
    return None

def name_re(n):
    body = re.escape(n).replace(r"\ ", r"[\s_-]?").replace(r"\-", r"[\s_-]?")
    if len(n) < 5:  # short names: only at the start of a word or identifier (so MBDA ≠ lambda)
        return re.compile(r"(?<![A-Za-z])(?:%s|%s|%s)" % (body, body.lower(), body.capitalize()))
    return re.compile(body, re.I)


name_res = [name_re(n) for n in avoid]
dom_res = [re.compile(re.escape(d), re.I) for d in domains]
hex_re = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
hits = []
for dirpath, dirnames, files in os.walk(a.root):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in files:
        p = os.path.join(dirpath, fn)
        rel = os.path.relpath(p, a.root)
        for r in name_res:
            if r.search(fn):
                hits.append(f"{rel}: file name contains '{r.pattern}'")
        if os.path.splitext(fn)[1].lower() not in TEXT_EXT or fn.endswith((".lock", "-lock.json")):
            continue
        try:
            lines = open(p, encoding="utf-8").read().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(lines, 1):
            for r in name_res + dom_res:
                if r.search(line):
                    hits.append(f"{rel}:{i}: '{r.search(line).group(0)}' → {line.strip()[:100]}")
            for m in hex_re.findall(line):
                n = near(m)
                if n:
                    hits.append(f"{rel}:{i}: colour {m} is {'the original' if n[1] == 0 else 'near the original'} {n[0]} (distance {n[1]})")
print("\n".join(hits) if hits else "clean")
print(f"\n{len(hits)} finding(s) · avoid={avoid} domains={domains} colours={colors}")
sys.exit(1 if hits else 0)
