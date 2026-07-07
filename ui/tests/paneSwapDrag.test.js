import test from "node:test";
import assert from "node:assert/strict";

import {
  DEAD_ZONE,
  dragIntent,
  isArmed,
  paneSpans,
  penetration,
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

// --- 1. paneSpans geometry (docs/pane-swap-drag-design.md §3.1) --------------

test("paneSpans: detail keeps width R and feed fills the rest in all four forms", () => {
  for (const form of FORMS) {
    const { detail, feed } = paneSpans({ W, L, R, ...form });
    assert.equal(detail.hi - detail.lo, R, `${form.name}: detail width`);
    assert.equal(feed.hi - feed.lo, W - L - R, `${form.name}: feed width`);
  }
});

test("paneSpans: feed and detail are always adjacent (share one boundary)", () => {
  for (const form of FORMS) {
    const { detail, feed } = paneSpans({ W, L, R, ...form });
    const adjacent = feed.hi === detail.lo || detail.hi === feed.lo;
    assert.ok(adjacent, `${form.name}: panes adjacent`);
  }
});

test("paneSpans: matches the exact grid tracks for edge/center on nav-left", () => {
  const edge = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  assert.deepEqual(edge.feed, { lo: 268, hi: 1508 });
  assert.deepEqual(edge.detail, { lo: 1508, hi: 1920 });

  const center = paneSpans({ W, L, R, navRight: false, detailCenter: true });
  assert.deepEqual(center.detail, { lo: 268, hi: 680 });
  assert.deepEqual(center.feed, { lo: 680, hi: 1920 });
});

test("paneSpans: nav-right mirrors the sidebar to the right edge", () => {
  const edge = paneSpans({ W, L, R, navRight: true, detailCenter: false });
  assert.deepEqual(edge.detail, { lo: 0, hi: 412 });
  assert.deepEqual(edge.feed, { lo: 412, hi: 1652 }); // W - L = 1652

  const center = paneSpans({ W, L, R, navRight: true, detailCenter: true });
  assert.deepEqual(center.feed, { lo: 0, hi: 1240 }); // W - L - R
  assert.deepEqual(center.detail, { lo: 1240, hi: 1652 });
});

test("paneSpans: compact-desktop clamped widths still tile the viewport", () => {
  // Caller passes already-painted L/R (workspaceStyle clamps 220-240 / 360-380).
  const cw = 1000;
  const cl = 240;
  const cr = 380;
  const { detail, feed } = paneSpans({ W: cw, L: cl, R: cr, navRight: false, detailCenter: false });
  assert.equal(detail.hi - detail.lo, cr);
  assert.equal(feed.lo, cl);
  assert.equal(feed.hi, detail.lo);
});

// --- 2. dragIntent: dead zone + axis (§4 defence line 2) ---------------------

test("dragIntent: travel below the dead zone stays pending (a click, not a drag)", () => {
  assert.equal(dragIntent(3, 3), "pending"); // hypot ≈ 4.24 < 6
  assert.equal(dragIntent(DEAD_ZONE - 0.01, 0), "pending");
});

test("dragIntent: a mostly-horizontal move past the dead zone begins the drag", () => {
  assert.equal(dragIntent(10, 2), "drag");
  assert.equal(dragIntent(8, 0), "drag");
  assert.equal(dragIntent(-30, 5), "drag");
});

test("dragIntent: a mostly-vertical move aborts (scroll/other gesture)", () => {
  assert.equal(dragIntent(2, 10), "abort");
  assert.equal(dragIntent(0, 8), "abort");
});

test("dragIntent: a 45° tie counts as horizontal so a diagonal still swaps", () => {
  assert.equal(dragIntent(7, 7), "drag");
  assert.equal(dragIntent(-7, 7), "drag");
});

// --- 3. penetration / isArmed: commit threshold at the target midline --------

test("penetration is zero until the pointer crosses the shared boundary", () => {
  const target = { lo: 1508, hi: 1920 }; // detail, to the right of the dragged feed
  assert.equal(penetration(1508, target, true), 0); // exactly on the boundary
  assert.equal(penetration(1400, target, true), 0); // still on the dragged side
  assert.equal(penetration(1600, target, true), 92); // 92px in
});

test("isArmed: dragging the feed arms only past the detail midline, and survives overshoot", () => {
  const { feed, detail } = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  // detail = {1508,1920}, width 412, midline 1714
  assert.equal(isArmed(1508, feed, detail), false); // at boundary
  assert.equal(isArmed(1714, feed, detail), false); // exactly the midline
  assert.equal(isArmed(1715, feed, detail), true); // one px past the midline
  assert.equal(isArmed(1950, feed, detail), true); // overshoot past the far edge
  assert.equal(isArmed(1600, feed, detail), false); // crossed boundary but short of midline
});

test("isArmed: dragging the detail arms leftward past the feed midline, reversibly", () => {
  const { feed, detail } = paneSpans({ W, L, R, navRight: false, detailCenter: false });
  // feed = {268,1508}, width 1240, midline 888
  assert.equal(isArmed(1509, detail, feed), false); // still on the dragged (right) side
  assert.equal(isArmed(888, detail, feed), false); // exactly the midline
  assert.equal(isArmed(887, detail, feed), true); // one px past
  assert.equal(isArmed(200, detail, feed), true); // overshoot past the far edge
  assert.equal(isArmed(1000, detail, feed), false); // retreated back before the midline → disarmed
});

test("isArmed: holds in every 2×2 form when the pointer sits just past the target midline", () => {
  for (const form of FORMS) {
    const spans = paneSpans({ W, L, R, ...form });
    for (const pane of ["feed", "detail"]) {
      const dragged = spans[pane];
      const target = pane === "feed" ? spans.detail : spans.feed;
      const mid = (target.lo + target.hi) / 2;
      const targetIsRight = target.lo + target.hi > dragged.lo + dragged.hi;
      const justPast = targetIsRight ? mid + 1 : mid - 1;
      assert.equal(isArmed(justPast, dragged, target), true, `${form.name} / drag ${pane}`);
      assert.equal(isArmed(mid, dragged, target), false, `${form.name} / drag ${pane} at midline`);
    }
  }
});

// --- 4/5. onPaneDragStart gating (§4 defence line 4, §10.1 test 5) -----------

function makeHook(overrides = {}) {
  return usePaneSwapDrag({
    isEnabled: () => true,
    getLayout: () => ({ W, L, R, navRight: false, detailCenter: false }),
    getGhostEl: () => null,
    onCommit: () => {},
    ...overrides,
  });
}

test("onPaneDragStart ignores touch/pen input, keeping the drag idle", () => {
  const hook = makeHook();
  hook.onPaneDragStart({ pane: "feed", x: 0, y: 0, pointerType: "touch", button: 0 });
  assert.equal(hook.draggedPane.value, null);
  assert.equal(hook.dragging.value, false);
});

test("onPaneDragStart ignores non-primary buttons", () => {
  const hook = makeHook();
  hook.onPaneDragStart({ pane: "feed", x: 0, y: 0, pointerType: "mouse", button: 2 });
  assert.equal(hook.draggedPane.value, null);
});

test("onPaneDragStart is a no-op when the gesture is disabled (right-closed / mobile)", () => {
  const hook = makeHook({ isEnabled: () => false });
  hook.onPaneDragStart({ pane: "detail", x: 0, y: 0, pointerType: "mouse", button: 0 });
  assert.equal(hook.draggedPane.value, null);
});

test("onPaneDragStart arms the pending phase for a valid primary mouse press", () => {
  // Minimal window stub so the accepted path can register its listeners.
  const listeners = [];
  const stub = {
    addEventListener: (type) => listeners.push(type),
    removeEventListener: () => {},
  };
  const original = globalThis.window;
  globalThis.window = stub;
  try {
    const hook = makeHook();
    hook.onPaneDragStart({ pane: "feed", x: 40, y: 40, pointerType: "mouse", button: 0 });
    assert.equal(hook.draggedPane.value, "feed");
    assert.equal(hook.dragging.value, false); // pending, not yet dragging (no move past dead zone)
    assert.ok(listeners.includes("pointermove"));
    assert.ok(listeners.includes("pointerup"));
  } finally {
    if (original === undefined) delete globalThis.window;
    else globalThis.window = original;
  }
});
