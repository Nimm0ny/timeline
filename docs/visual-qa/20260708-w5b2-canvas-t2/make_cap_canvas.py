# W5b-2 cap-test reproducer: a canvas with 40 embed cards in a tight 8x5 grid, so at zoom >=1.5
# ALL 40 centers stay on-screen at once (each card >=360px wide) → 40 T2 "full" candidates >
# EMBED_FULL_BUDGET(24). Verifies the budget gate demotes the surplus to preview (docs §7.3).
# Expect (zoom 1.6, 1440x900): 24 is-full + 16 preview, console "T2 over budget: 40 → 24".
#
# Usage: backend up, then  python make_cap_canvas.py   (BASE defaults :8000; set BASE to override)
# Delete after QA:  curl -s -X DELETE "http://localhost:8000/api/events/<id>?permanent=true"
import json
import os
import urllib.request

BASE = os.environ.get("BASE", "http://localhost:8000")
TOPIC = 2


def post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


rows = json.load(urllib.request.urlopen(f"{BASE}/api/topics/{TOPIC}/events?limit=60"))["items"]
pool = [e["id"] for e in rows if e.get("noteType", "entry") == "entry"][:60]
assert pool, "no entry notes to embed"

cells = []
for i in range(40):
    col, row = i % 8, i // 8
    cells.append({
        "id": f"c-cap{i:02d}", "shape": "embed-card",
        "x": 200 + col * 120, "y": 200 + row * 120, "width": 240, "height": 120,
        "data": {"kind": "embed", "noteId": pool[i % len(pool)], "headline": "", "preview": ""},
        "zIndex": 2,
    })

created = post(f"/api/topics/{TOPIC}/events", {
    "noteType": "canvas", "headline": "QA-cap-40 (temp fixture — delete after)",
    "bodyJson": {"_fmt": "x6-canvas-v1", "cells": cells, "background": ""},
})
print("CREATED_ID", created["id"], "| cards", len(cells))
