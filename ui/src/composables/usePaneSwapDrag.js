import { getCurrentInstance, onBeforeUnmount, ref } from "vue";

// Mouse-only drag to rearrange the three columns by grabbing the empty area of a
// column's toolbar, then releasing past a threshold. Each column maps to one layout
// knob (docs/pane-swap-drag-design.md):
//   - sidebar → toggles navPosition (moves the function bar to the opposite edge)
//   - feed / detail → toggles detailPosition (swaps the list and the detail pane)
// The composable owns no persisted state; it commits through the page's
// updateNavPosition / updateDetailPosition, the same handlers the settings control
// and the ⋮ menu use.

export const DEAD_ZONE = 6; // px of travel below which a press is a click, not a drag
export const GHOST_OFFSET = 14; // px the ghost chip trails the pointer by (both axes)
// Feed/detail are adjacent, so committing means dragging INTO the target pane by this
// much — capped so a wide target (the feed) doesn't demand an arm's-length drag.
export const COMMIT_PENETRATION = 200;

// Horizontal [lo, hi] span each column paints at, for the active nav/detail combo.
// Mirrors the grid-template-columns + `order` rules in notes.css and the
// resizer math (docs/layout-swap-design.md §1/§7). W = viewport width, L = painted
// sidebar width, R = painted detail width; a closed detail collapses to zero width.
export function paneSpans({ W, L, R, navRight, detailCenter, rightOpen = true }) {
  const Rd = rightOpen ? R : 0;
  if (!detailCenter && !navRight) {
    return { sidebar: { lo: 0, hi: L }, feed: { lo: L, hi: W - Rd }, detail: { lo: W - Rd, hi: W } };
  }
  if (!detailCenter && navRight) {
    return { detail: { lo: 0, hi: Rd }, feed: { lo: Rd, hi: W - L }, sidebar: { lo: W - L, hi: W } };
  }
  if (detailCenter && !navRight) {
    return { sidebar: { lo: 0, hi: L }, detail: { lo: L, hi: L + Rd }, feed: { lo: L + Rd, hi: W } };
  }
  return { feed: { lo: 0, hi: W - L - Rd }, detail: { lo: W - L - Rd, hi: W - L }, sidebar: { lo: W - L, hi: W } };
}

// The slot the dragged column moves into, and the pane whose knob its release
// toggles. The sidebar always lands on the opposite outer edge (a strip of its own
// width); feed and detail swap into each other's slot.
export function swapTarget(pane, spans, { W, L, navRight }) {
  if (pane === "sidebar") {
    const span = navRight ? { lo: 0, hi: L } : { lo: W - L, hi: W };
    return { span, knob: "nav" };
  }
  const otherPane = pane === "feed" ? "detail" : "feed";
  return { span: spans[otherPane], knob: "detail" };
}

// Classify the first move past the dead zone: a mostly-vertical move is treated as a
// scroll/other gesture and aborts. A 45° tie counts as horizontal so a diagonal
// intent still swaps.
export function dragIntent(dx, dy, deadZone = DEAD_ZONE) {
  if (Math.hypot(dx, dy) < deadZone) return "pending";
  return Math.abs(dx) >= Math.abs(dy) ? "drag" : "abort";
}

// How far the pointer has entered the target span past the boundary facing the
// dragged pane (0 if it has not crossed yet).
export function penetration(x, targetSpan, targetIsRight) {
  return targetIsRight
    ? Math.max(0, x - targetSpan.lo)
    : Math.max(0, targetSpan.hi - x);
}

// Commit rule, per gesture:
//   - sidebar: the pointer crosses the viewport centre toward the opposite edge —
//     "drag the bar past the middle and it flips sides".
//   - feed/detail: the pointer enters the adjacent target pane by min(half its
//     width, COMMIT_PENETRATION) — never arms while still over the dragged pane,
//     and a wide target doesn't force a long drag.
// Overshoot past the far edge stays armed; retreating disarms (reversible).
export function isArmed(pane, x, draggedSpan, targetSpan, viewportW) {
  const targetIsRight = targetSpan.lo + targetSpan.hi > draggedSpan.lo + draggedSpan.hi;
  if (pane === "sidebar") {
    const mid = viewportW / 2;
    return targetIsRight ? x >= mid : x <= mid;
  }
  const need = Math.min((targetSpan.hi - targetSpan.lo) / 2, COMMIT_PENETRATION);
  return penetration(x, targetSpan, targetIsRight) > need;
}

export function usePaneSwapDrag({ isEnabled, getLayout, getGhostEl, onCommit }) {
  const dragging = ref(false);
  const draggedPane = ref(null); // "sidebar" | "feed" | "detail"
  const armed = ref(false);
  const targetRect = ref({ left: 0, width: 0 });

  // Non-reactive drag scratch: kept out of refs so pointermove never touches Vue.
  let phase = "idle"; // "idle" | "pending" | "dragging"
  let startX = 0;
  let startY = 0;
  let lastX = 0;
  let lastY = 0;
  let draggedSpan = null;
  let targetSpan = null;
  let viewportW = 0;
  let cleanup = null;
  let rafId = 0;

  function applyGhostTransform() {
    const el = getGhostEl();
    if (el) el.style.transform = `translate3d(${lastX + GHOST_OFFSET}px, ${lastY + GHOST_OFFSET}px, 0)`;
  }

  // One compositor-only update per frame: move the ghost, recompute armed. Reads no
  // layout — spans were cached at drag start (pane-swap-drag-design.md §5).
  function scheduleFrame() {
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      applyGhostTransform();
      const next = isArmed(draggedPane.value, lastX, draggedSpan, targetSpan, viewportW);
      if (next !== armed.value) armed.value = next;
    });
  }

  function beginDrag() {
    phase = "dragging";
    const layout = getLayout();
    const spans = paneSpans(layout);
    const target = swapTarget(draggedPane.value, spans, layout);
    draggedSpan = spans[draggedPane.value];
    targetSpan = target.span;
    viewportW = layout.W;
    targetRect.value = { left: targetSpan.lo, width: targetSpan.hi - targetSpan.lo };
    armed.value = false;
    dragging.value = true;
    applyGhostTransform(); // seed position before first paint so the ghost never flashes at 0,0
  }

  function reset() {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    phase = "idle";
    dragging.value = false;
    draggedPane.value = null;
    armed.value = false;
    if (cleanup) {
      cleanup();
      cleanup = null;
    }
  }

  function onMove(event) {
    lastX = event.clientX;
    lastY = event.clientY;
    if (phase === "pending") {
      const intent = dragIntent(lastX - startX, lastY - startY);
      if (intent === "abort") {
        reset();
        return;
      }
      if (intent === "drag") {
        beginDrag();
      } else {
        return; // still inside the dead zone
      }
    }
    if (phase === "dragging") scheduleFrame();
  }

  function onUp() {
    const pane = draggedPane.value;
    const shouldCommit = phase === "dragging" && armed.value;
    reset();
    if (shouldCommit) onCommit(pane);
  }

  function onKey(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      reset();
    }
  }

  function onPaneDragStart({ pane, x, y, pointerType, button }) {
    if (phase !== "idle") return;
    if (!isEnabled(pane)) return;
    if (pointerType && pointerType !== "mouse") return;
    if (button != null && button !== 0) return;

    phase = "pending";
    draggedPane.value = pane;
    startX = x;
    startY = y;
    lastX = x;
    lastY = y;

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", reset);
    window.addEventListener("keydown", onKey);
    window.addEventListener("blur", reset);
    window.addEventListener("resize", reset);
    cleanup = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", reset);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("blur", reset);
      window.removeEventListener("resize", reset);
    };
  }

  // Pure-function tests instantiate this composable outside component setup; skip
  // lifecycle registration there so Vue doesn't warn while preserving runtime cleanup.
  if (getCurrentInstance()) {
    // Tear down any in-flight drag if the host unmounts mid-gesture, so window
    // listeners and a pending rAF can never outlive the component.
    onBeforeUnmount(reset);
  }

  return { dragging, draggedPane, armed, targetRect, onPaneDragStart };
}
