"""Feature parity from replica/features.csv (weights must 3, should 2, could 1; partial = half).

python3 replica/tools/parity.py replica/features.csv   → exit 1 if any `must` row isn't `yes`
"""
import csv, sys

rows = list(csv.DictReader(open(sys.argv[1] if len(sys.argv) > 1 else "replica/features.csv")))
W = {"must": 3, "should": 2, "could": 1}
score = lambda r: 1 if r["clone"] == "yes" else 0.5 if r["clone"] == "partial" else 0
tot = sum(W[r["priority"]] for r in rows if r["priority"] in W)
got = sum(W[r["priority"]] * score(r) for r in rows if r["priority"] in W)
print(f"parity {got / tot:.0%} (weighted)")
for p in W:
    rs = [r for r in rows if r["priority"] == p]
    print(f"  {p:6} {sum(r['clone'] == 'yes' for r in rs)}/{len(rs)} done")
missing = [r for r in rows if r["priority"] == "must" and r["clone"] != "yes"]
for r in missing:
    print(f"  MISSING must: {r['feature']}  ({r['notes']})")
sys.exit(1 if missing else 0)
