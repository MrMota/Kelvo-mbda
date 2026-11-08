"""Rank review/issue rows into themes.

python3 replica/reviews.py replica/reviews.csv --out replica/feedback.md [--themes replica/themes.json]

Input columns: source,url,date,rating,text (+ optional votes). Rows without a URL are dropped.
Weight per row = rating weight (1★→3, 2★→2.5, 3★→2, 4★→1.2, 5★→0.6; blank→1)
               × recency (≤1y→1.5, ≤2y→1.0, older→0.6)
               × votes (1 + log2(1 + votes)).
A theme is THIN when it has fewer than 3 rows or only one source.
"""
import argparse, csv, json, math, re
from collections import defaultdict
from datetime import date
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("csv")
ap.add_argument("--out", required=True)
ap.add_argument("--themes", default=str(Path(__file__).with_name("themes.json")))
ap.add_argument("--today", default=date.today().isoformat())
a = ap.parse_args()

themes = json.load(open(a.themes))
today = date.fromisoformat(a.today)
rows = [r for r in csv.DictReader(open(a.csv, newline="")) if (r.get("url") or "").startswith("http")]

def weight(r):
    rt = (r.get("rating") or "").strip()
    w = {"1": 3, "2": 2.5, "3": 2, "4": 1.2, "5": 0.6}.get(rt[:1], 1.0)
    try:
        age = (today - date.fromisoformat(r["date"][:10])).days
        w *= 1.5 if age <= 365 else 1.0 if age <= 730 else 0.6
    except Exception:
        pass
    v = int(r.get("votes") or 0)
    return w * (1 + math.log2(1 + v))

def first_line(t):
    return t.split("\n", 1)[0].strip()

hits = defaultdict(list)
unmatched = []
for r in rows:
    low = " " + r["text"].lower() + " "
    matched = [name for name, kws in themes.items() if any(re.search(r"(?<![a-z0-9])" + re.escape(k.strip()), low) for k in kws)]
    for m in matched:
        hits[m].append(r)
    if not matched:
        unmatched.append(r)

ranked = sorted(hits.items(), key=lambda kv: -sum(weight(r) for r in kv[1]))
srcs = sorted({r["source"] for r in rows})
dates = sorted(r["date"] for r in rows if r.get("date"))

out = [f"# Feedback ranking\n",
       f"{len(rows)} rows · sources: {', '.join(srcs)} · dates {dates[0] if dates else '?'} → {dates[-1] if dates else '?'} · ranked {a.today}\n",
       "Score = sum of row weights (low rating, recent, many votes count more). A row can sit in several themes.\n",
       "| # | theme | rows | sources | votes | score | |", "| --- | --- | --- | --- | --- | --- | --- |"]
for i, (name, rs) in enumerate(ranked, 1):
    ns = len({r["source"] for r in rs})
    thin = "THIN" if len(rs) < 3 or ns < 2 else ""
    out.append(f"| {i} | {name} | {len(rs)} | {ns} | {sum(int(r.get('votes') or 0) for r in rs)} | {sum(weight(r) for r in rs):.1f} | {thin} |")

for name, rs in ranked:
    out.append(f"\n## {name}\n")
    for r in sorted(rs, key=lambda r: -weight(r))[:8]:
        v = f" · {r['votes']} votes" if r.get("votes") not in (None, "", "0") else ""
        out.append(f"- [{first_line(r['text'])}]({r['url']}) — {r['source']}, {r['date']}{v}")

req = [r for r in rows if re.search(r"feature request|enhancement|add support|support for|would be (nice|great)|please add|allow ", r["text"], re.I) or "feature" in r["source"].lower()]
out.append(f"\n## Requests in users' own words ({len(req)})\n")
for r in sorted(req, key=lambda r: -int(r.get("votes") or 0)):
    out.append(f"- {first_line(r['text'])} — [{r['url'].rsplit('/', 1)[-1]}]({r['url']}) · {r.get('votes') or 0} votes")

out.append(f"\n## Matched no theme ({len(unmatched)}) — read these by hand\n")
for r in sorted(unmatched, key=lambda r: -weight(r)):
    out.append(f"- [{first_line(r['text'])}]({r['url']}) — {r['date']}")

Path(a.out).write_text("\n".join(out) + "\n")
print(f"{len(rows)} rows, {len(ranked)} themes, {len(unmatched)} unmatched → {a.out}")
