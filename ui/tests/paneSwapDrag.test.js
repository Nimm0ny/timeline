import test from "node:test";
import assert from "node:assert/strict";

import {
  COMMIT_PENETRATION,
  DEAD_ZONE,
  dragIntent,
  isArmed,
  paneSpans,
  penetration,
  swapTarget,
  usePaneSwapDrag,
} from "../src/composables/usePaneSwapDrag.js";

const W = 1920;
const L = 268;
const R = 412;
const FORMS = [
  { name: "edge + nav-left", navRight: false, detailCenter: false },
  { name: "edge + nav-right", navRight: true, detailCenter: false },
  { name: "center + nav-left", navRight: false, detailCenter: true },
  { name: "center + nav-right", navRight: true, detailCenter: true },
];

// --- paneSpans geometry (docs/pane-swap-drag-design.md §3.1) -----------------

test("paneSpans: the three columns tile the viewport with no gap/overlap in all forms", () => {
  for (const form of FORMS) {
    const { sidebar, feed, detail } = paneSpans({ W, L, R, ...form });
    const ordered = [sidebar, feed, detail].sort((a, b) => a.lo - b.lo);
    assert.equal(ordered[0].lo, 0, `${form.name}: starts at 0`);
    assert.equal(ordered[2].hi, W, `${form.name}: ends at W`);
    assert.equal(ordered[0].hi, ordered[1].lo, `${form.name}: no gap 0-1`);
    assert.equal(ordered[1].hi, ordered[2].lo, `${form.name}: no gap 1-2`);
  }
});

test("paneSpans: sidebar width L and detail width R hold in every form", () => {
  for (const form of FORMS) {
    const { sidebar, detail } = paneSpans({ W, L, R, ...form });
    assert.equal(sidebar.hi - sidebar.lo, L, `${form.name}: sidebar width`);
    assert.equal(detail.hi - detail.lo, R, `${form.name}: detail width`);
  }
});

test("paneSpans: sidebar always sits on an outer edge (touches 0 or W)", () => {
  for (const form of FORMS) {
    const { sidebar } = paneSpans({ W, L, R, ...form });
    assert.ok(sidebar.lo === 0 || sidebar.hi === W, `${form.name}: sidebar on edge`);
  }
});

test("paneSpans: a closed detail collapses to zero width, feed takes the slack", () => {
  const { feed, detail } = paneSpans({ W, L, R, navRight: false, detailCenter: false, rightOpen: false });
  assert.equal(detail.hi - detail.lo, 0);
  assert.equal(feed.lo, L);
  assert.equal(feed.hi, W); // feed spans from the sidebar edge to the viewport edge
});

test("paneSpans: matches exact tracks for edge/center on nav-left", () => {
  const edge = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  assert.deepEqual(edge.sidebar, { lo: 0, hi: 268 });
  assert.deepEqual(edge.feed, { lo: 268, hi: 1508 });
  assert.deepEqual(edge.detail, { lo: 1508, hi: 1920 });

  const center = paneSpans({ W, L, R, navRight: false, detailCenter: true });
  assert.deepEqual(center.detail, { lo: 268, hi: 680 });
  assert.deepEqual(center.feed, { lo: 680, hi: 1920 });
});

// --- swapTarget: which slot + which knob (§1) --------------------------------

test("swapTarget: sidebar lands on the opposite edge and toggles the nav knob", () => {
  const spans = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  const left = swapTarget("sidebar", spans, { W, L, navRight: false });
  assert.deepEqual(left.span, { lo: W - L, hi: W }); // opposite (right) edge strip
  assert.equal(left.knob, "nav");

  const spansR = paneSpans({ W, L, R, navRight: true, detailCenter: false });
  const right = swapTarget("sidebar", spansR, { W, L, navRight: true });
  assert.deepEqual(right.span, { lo: 0, hi: L }); // opposite (left) edge strip
  assert.equal(right.knob, "nav");
});

test("swapTarget: sidebar drag stays correct when the detail is closed (2-column)", () => {
  // Right-closed: the feed absorbs the collapsed detail slot, but the sidebar still
  // swaps to the opposite edge and the threshold is still the viewport centre.
  const spans = paneSpans({ W, L, R, navRight: false, detailCenter: false, rightOpen: false });
  const { span, knob } = swapTarget("sidebar", spans, { W, L, navRight: false });
  assert.deepEqual(span, { lo: W - L, hi: W });
  assert.equal(knob, "nav");
  assert.equal(isArmed("sidebar", 959, spans.sidebar, span, W), false);
  assert.equal(isArmed("sidebar", 960, spans.sidebar, span, W), true);
});

test("swapTarget: feed and detail swap into each other's slot, toggling the detail knob", () => {
  const spans = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  const fromFeed = swapTarget("feed", spans, { W, L, navRight: false });
  assert.deepEqual(fromFeed.span, spans.detail);
  assert.equal(fromFeed.knob, "detail");

  const fromDetail = swapTarget("detail", spans, { W, L, navRight: false });
  assert.deepEqual(fromDetail.span, spans.feed);
  assert.equal(fromDetail.knob, "detail");
});

// --- dragIntent: dead zone + axis (§4 defence line 2) ------------------------

test("dragIntent: travel below the dead zone stays pending", () => {
  assert.equal(dragIntent(3, 3), "pending");
  assert.equal(dragIntent(DEAD_ZONE - 0.01, 0), "pending");
});

test("dragIntent: horizontal begins the drag, vertical aborts, 45° ties horizontal", () => {
  assert.equal(dragIntent(10, 2), "drag");
  assert.equal(dragIntent(-30, 5), "drag");
  assert.equal(dragIntent(2, 10), "abort");
  assert.equal(dragIntent(0, 8), "abort");
  assert.equal(dragIntent(7, 7), "drag");
});

// --- isArmed feed/detail: capped penetration into the adjacent target --------

test("isArmed(feed): arms after entering the detail by COMMIT_PENETRATION, survives overshoot", () => {
  const { feed, detail } = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  // detail = {1508,1920}, width 412 → need = min(206, 200) = 200; boundary 1508
  assert.equal(isArmed("feed", 1708, feed, detail, W), false); // exactly at the threshold
  assert.equal(isArmed("feed", 1709, feed, detail, W), true); // one px past
  assert.equal(isArmed("feed", 1600, feed, detail, W), false); // crossed boundary, short of threshold
  assert.equal(isArmed("feed", 1508, feed, detail, W), false); // right on the boundary
  assert.equal(isArmed("feed", 1950, feed, detail, W), true); // overshoot past the far edge
});

test("isArmed(detail): wide feed target is capped so it doesn't demand an arm's-length drag", () => {
  const { feed, detail } = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  // feed = {268,1508}, width 1240 → need = min(620, 200) = 200; boundary 1508
  assert.equal(isArmed("detail", 1308, detail, feed, W), false); // exactly at the threshold
  assert.equal(isArmed("detail", 1307, detail, feed, W), true); // one px past
  assert.equal(isArmed("detail", 1000, detail, feed, W), true); // comfortably inside
  assert.equal(isArmed("detail", 1509, detail, feed, W), false); // still on the dragged side
  assert.equal(isArmed("detail", 200, detail, feed, W), true); // overshoot
});

test("COMMIT_PENETRATION caps the required travel at 200px", () => {
  assert.equal(COMMIT_PENETRATION, 200);
});

// --- isArmed sidebar: crosses the viewport centre ---------------------------

test("isArmed(sidebar): nav-left arms once the pointer passes the viewport centre", () => {
  const spans = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  const { span } = swapTarget("sidebar", spans, { W, L, navRight: false });
  assert.equal(isArmed("sidebar", 959, spans.sidebar, span, W), false);
  assert.equal(isArmed("sidebar", 960, spans.sidebar, span, W), true); // viewport centre
  assert.equal(isArmed("sidebar", 1800, spans.sidebar, span, W), true);
});

test("isArmed(sidebar): nav-right mirrors — arms when the pointer passes centre going left", () => {
  const spans = paneSpans({ W, L, R, navRight: true, detailCenter: false });
  const { span } = swapTarget("sidebar", spans, { W, L, navRight: true });
  assert.equal(isArmed("sidebar", 961, spans.sidebar, span, W), false);
  assert.equal(isArmed("sidebar", 960, spans.sidebar, span, W), true);
  assert.equal(isArmed("sidebar", 100, spans.sidebar, span, W), true);
});

test("penetration is zero until the pointer crosses the shared boundary", () => {
  const target = { lo: 1508, hi: 1920 };
  assert.equal(penetration(1508, target, true), 0);
  assert.equal(penetration(1400, target, true), 0);
  assert.equal(penetration(1600, target, true), 92);
});

// --- onPaneDragStart gating (§4 defence line 4) ------------------------------

function makeHook(overrides = {}) {
  return usePaneSwapDrag({
    isEnabled: () => true,
    getLayout: () => ({ W, L, R, navRight: false, detailCenter: false, rightOpen: true }),
    getGhostEl: () => null,
    onCommit: () => {},
    ...overrides,
  });
}

test("onPaneDragStart ignores touch/pen input", () => {
  const hook = makeHook();
  hook.onPaneDragStart({ pane: "feed", x: 0, y: 0, pointerType: "touch", button: 0 });
  assert.equal(hook.draggedPane.value, null);
  assert.equal(hook.dragging.value, false);
});

test("onPaneDragStart ignores non-primary buttons", () => {
  const hook = makeHook();
  hook.onPaneDragStart({ pane: "detail", x: 0, y: 0, pointerType: "mouse", button: 2 });
  assert.equal(hook.draggedPane.value, null);
});

test("onPaneDragStart consults isEnabled with the specific pane (feed disabled, sidebar allowed)", () => {
  const seen = [];
  const hook = makeHook({
    isEnabled: (pane) => {
      seen.push(pane);
      return pane === "sidebar"; // e.g. right pane closed → only the sidebar may drag
    },
  });
  hook.onPaneDragStart({ pane: "feed", x: 0, y: 0, pointerType: "mouse", button: 0 });
  assert.equal(hook.draggedPane.value, null); // feed rejected
  assert.deepEqual(seen, ["feed"]);
});

test("onPaneDragStart arms the pending phase for a valid primary mouse press", () => {
  const listeners = [];
  const stub = { addEventListener: (type) => listeners.push(type), removeEventListener: () => {} };
  const original = globalThis.window;
  globalThis.window = stub;
  try {
    const hook = makeHook();
    hook.onPaneDragStart({ pane: "sidebar", x: 40, y: 40, pointerType: "mouse", button: 0 });
    assert.equal(hook.draggedPane.value, "sidebar");
    assert.equal(hook.dragging.value, false); // pending, not dragging yet
    assert.ok(listeners.includes("pointermove"));
    assert.ok(listeners.includes("pointerup"));
  } finally {
    if (original === undefined) delete globalThis.window;
    else globalThis.window = original;
  }
});
