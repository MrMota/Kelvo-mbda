"""Lint the directory listings in listing.json.

python3 replica/launch/listing.py replica/launch/listing.json [--brand replica/brand.json]

Limits: GitHub description 350; GitHub topics ≤20, lowercase, ≤50 chars, letters/digits/-;
PyPI summary ≤ 200 (keep under 120 to avoid truncation); Docker Hub short description 100;
Product Hunt name 40, tagline 60, description 260; Show HN title 80.
Also flags: names from brand.json `avoid`, ranking/price claims ("best", "#1", "free!",
"cheapest", "fastest"), emoji in short fields, and unverifiable superlatives.
Exit 1 on any error; warnings don't fail.
"""
import json, re, sys
from pathlib import Path

args = sys.argv[1:]
path = args[0] if args else "replica/launch/listing.json"
brand = Path(args[args.index("--brand") + 1]) if "--brand" in args else Path(path).resolve().parents[1] / "brand.json"
L = json.load(open(path))
avoid = json.load(open(brand)).get("avoid", []) if brand.exists() else []
errors, warns = [], []

def chars(s):  # count user-perceived characters (no combining marks)
    return len(re.sub(r"[̀-ͯ️‍]", "", s))

def limit(where, s, n, soft=None):
    c = chars(s)
    if c > n:
        errors.append(f"{where}: {c} chars > {n}")
    elif soft and c > soft:
        warns.append(f"{where}: {c} chars (limit {n}, but over {soft} gets truncated in places)")

CLAIMS = re.compile(r"\b(best|#1|number one|cheapest|fastest|world'?s|leading|free!|guaranteed)\b", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")

def check_text(where, s, short=False):
    for n in avoid:
        if re.search(re.escape(n), s, re.I if len(n) >= 5 else 0):
            errors.append(f"{where}: contains avoided name '{n}'")
    if CLAIMS.search(s):
        errors.append(f"{where}: ranking/price claim '{CLAIMS.search(s).group(0)}'")
    if short and EMOJI.search(s):
        warns.append(f"{where}: emoji in a short field")

g = L.get("github", {})
limit("github.description", g.get("description", ""), 350)
check_text("github.description", g.get("description", ""), True)
topics = g.get("topics", [])
if len(topics) > 20:
    errors.append(f"github.topics: {len(topics)} > 20")
for t in topics:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", t):
        errors.append(f"github.topics: '{t}' must be lowercase letters, digits, hyphens, ≤50")
    check_text("github.topics", t)
p = L.get("pypi", {})
limit("pypi.summary", p.get("summary", ""), 200, soft=120)
check_text("pypi.summary", p.get("summary", ""), True)
for k in p.get("keywords", []):
    check_text("pypi.keywords", k)
d = L.get("docker_hub", {})
limit("docker_hub.short_description", d.get("short_description", ""), 100)
check_text("docker_hub.short_description", d.get("short_description", ""), True)
ph = L.get("product_hunt", {})
limit("product_hunt.name", ph.get("name", ""), 40)
limit("product_hunt.tagline", ph.get("tagline", ""), 60)
limit("product_hunt.description", ph.get("description", ""), 260)
for k in ("name", "tagline", "description"):
    check_text(f"product_hunt.{k}", ph.get(k, ""), k != "description")
hn = L.get("show_hn", {})
limit("show_hn.title", hn.get("title", ""), 80)
check_text("show_hn.title", hn.get("title", ""), True)
if hn.get("title") and not hn["title"].startswith("Show HN: "):
    errors.append("show_hn.title: must start with 'Show HN: '")

for w in warns:
    print("warn ", w)
for e in errors:
    print("ERROR", e)
print(f"{len(errors)} error(s), {len(warns)} warning(s)")
sys.exit(1 if errors else 0)
