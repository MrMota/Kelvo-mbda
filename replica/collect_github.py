"""Collect public Langflow GitHub issues as research rows (official GitHub search API).

Usage: python3 replica/collect_github.py > replica/reviews.csv
Rows: source,url,date,rating,votes,text. GitHub has no star rating, so `rating` is
blank and `votes` holds the issue's reaction count (its 👍-style vote signal).
`text` is the issue title plus a verbatim excerpt of the body (HTML comments, i.e.
the issue-template boilerplate, removed; cut at 500 chars and marked with …).
Polite: ~14 queries, one every 7 s.
"""
import csv, json, re, subprocess, sys, time

REPO = "langflow-ai/langflow"
QUERIES = [
    ("feature request", "is:issue label:enhancement"),
    ("issue", "is:issue ollama"),
    ("issue", "is:issue agent tool calling"),
    ("issue", "is:issue slow OR performance OR latency"),
    ("issue", "is:issue memory OR RAM"),
    ("issue", "is:issue upgrade OR migration"),
    ("issue", "is:issue install OR installation"),
    ("issue", "is:issue custom component"),
    ("issue", "is:issue documentation OR docs"),
    ("issue", "is:issue playground"),
    ("issue", "is:issue version OR versioning OR git"),
    ("issue", "is:issue deploy OR production OR kubernetes"),
    ("issue", "is:issue local model OR offline"),
    ("issue", "is:issue label:bug"),
]

def search(q):
    out = subprocess.run(["gh", "api", "-X", "GET", "search/issues", "-f", f"q=repo:{REPO} {q}",
                          "-f", "sort=reactions", "-f", "order=desc", "-f", "per_page=30"],
                         capture_output=True, text=True)
    if out.returncode:
        print(f"query failed: {q}: {out.stderr.strip()[:200]}", file=sys.stderr)
        return []
    return json.loads(out.stdout)["items"]

seen, rows = set(), []
for i, (kind, q) in enumerate(QUERIES):
    if i:
        time.sleep(7)
    items = search(q)
    print(f"{q}: {len(items)}", file=sys.stderr)
    for it in items:
        if it["html_url"] in seen or "pull_request" in it:
            continue
        seen.add(it["html_url"])
        labels = [l["name"].lower() for l in it.get("labels", [])]
        body = re.sub(r"<!--.*?-->", "", it.get("body") or "", flags=re.S).strip()
        excerpt = body[:500] + ("…" if len(body) > 500 else "")
        src = "GitHub feature requests" if ("enhancement" in labels or kind == "feature request") else "GitHub issues"
        rows.append([src, it["html_url"], it["created_at"][:10], "", it["reactions"]["total_count"],
                     it["title"].strip() + ("\n\n" + excerpt if excerpt else "")])

w = csv.writer(sys.stdout)
w.writerow(["source", "url", "date", "rating", "votes", "text"])
w.writerows(rows)
print(f"{len(rows)} unique rows", file=sys.stderr)
