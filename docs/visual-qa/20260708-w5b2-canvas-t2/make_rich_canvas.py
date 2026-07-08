# W5b-2 fidelity reproducer: one entry note with rich markdown (heading / list / blockquote /
# inline code) embedded in a single-card canvas. Zoom the card past ~2x → it reaches the T2 "full"
# tier and renders the FULL read-mode markdown in place of the preview (docs §7.2). Expect the
# full card body DOM = [H1, P, UL(3xLI), BLOCKQUOTE, P(code)], scrolling within the fixed box.
#
# Usage: backend up, then  python make_rich_canvas.py   (BASE defaults :8000; set BASE to override)
# Delete both ids after QA:  curl -s -X DELETE ".../api/events/<id>?permanent=true"
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


body = (
    "# 秦朝统一\n\n秦始皇统一六国，建立中央集权：\n\n"
    "- 书同文、车同轨\n- 统一度量衡\n- 郡县制\n\n"
    "> 废封建，立郡县。\n\n使用 `丞相` 制度。"
)
note = post(f"/api/topics/{TOPIC}/events", {
    "noteType": "entry", "headline": "QA-rich-markdown (temp)", "bodyMarkdown": body,
})
nid = note["id"]
cells = [{
    "id": "c-rich0", "shape": "embed-card", "x": 300, "y": 200, "width": 240, "height": 120,
    "data": {"kind": "embed", "noteId": nid, "headline": "", "preview": ""}, "zIndex": 2,
}]
canvas = post(f"/api/topics/{TOPIC}/events", {
    "noteType": "canvas", "headline": "QA-rich-canvas (temp)",
    "bodyJson": {"_fmt": "x6-canvas-v1", "cells": cells, "background": ""},
})
print("RICH_NOTE_ID", nid, "RICH_CANVAS_ID", canvas["id"])
