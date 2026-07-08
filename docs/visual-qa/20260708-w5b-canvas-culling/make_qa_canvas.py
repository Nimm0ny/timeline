# W5b-1 QA reproducer: create a canvas note with 200 embed cards in a 20x10 grid, referencing
# 60 real notes, so viewport culling can be exercised at N=200 (docs §7.7). Prints the new note
# id; delete it after QA:  curl -s -X DELETE "http://localhost:8000/api/events/<id>?permanent=true"
#
# Usage: backend on :8000, then  python docs/visual-qa/20260708-w5b-canvas-culling/make_qa_canvas.py
import json
import urllib.request

BASE = "http://localhost:8000"
TOPIC = 2  # 古代史 (has >100 entry notes)


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.load(r)


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


rows = get(f"/api/topics/{TOPIC}/events?limit=60")["items"]
pool = [(e["id"], e.get("headline", "")) for e in rows if e.get("noteType", "entry") == "entry"][:60]
assert pool, "no entry notes to embed"

COLS, ROWS = 20, 10  # 200 cards
SPACING_X, SPACING_Y = 320, 220
cells = []
for i in range(COLS * ROWS):
    note_id, headline = pool[i % len(pool)]
    col, row = i % COLS, i // COLS
    cells.append({
        "id": f"c-qa{i:03d}",
        "shape": "embed-card",
        "x": 80 + col * SPACING_X,
        "y": 80 + row * SPACING_Y,
        "width": 240,
        "height": 120,
        "data": {"kind": "embed", "noteId": note_id, "headline": headline, "preview": ""},
        "zIndex": 2,
    })

created = post(f"/api/topics/{TOPIC}/events", {
    "noteType": "canvas",
    "headline": "QA-200-embeds (temp fixture — delete after)",
    "bodyJson": {"_fmt": "x6-canvas-v1", "cells": cells, "background": ""},
})
print("CREATED_ID", created["id"])
print("EMBED_CARDS", len(cells))
print("DISTINCT_NOTES", len({c["data"]["noteId"] for c in cells}))
