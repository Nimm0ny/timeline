import { onBeforeUnmount, ref } from "vue";

// Mouse-only drag to swap the feed and detail panes by grabbing the empty area of
// either column's toolbar. This is the third entry point for the detailPosition
// toggle (settings segmented control + detail ⋮ menu being the other two); it owns
// no persisted state and commits through the same updateDetailPosition().
// Full design: docs/pane-swap-drag-design.md.

export const DEAD_ZONE = 6; // px of travel below which a press is a click, not a drag
export const GHOST_OFFSET = 14; // px the ghost chip trails the pointer by (both axes)

// Horizontal [lo, hi] span each pane paints at, for the active nav/detail combo.
// Mirrors the grid-template-columns + `order` rules in timeline-notes.css and the
// resizer math (docs/layout-swap-design.md §1/§7, pane-swap-drag-design.md §3.1).
// W = viewport width, L = painted sidebar width, R = painted detail width.
export function paneSpans({ W, L, R, navRight, detailCenter }) {
  if (!detailCenter && !navRight) {
    return { feed: { lo: L, hi: W - R }, detail: { lo: W - R, hi: W } };
  }
  if (!detailCenter && navRight) {
    return { detail: { lo: 0, hi: R }, feed: { lo: R, hi: W - L } };
  }
  if (detailCenter && !navRight) {
    return { detail: { lo: L, hi: L + R }, feed: { lo: L + R, hi: W } };
  }
  return { feed: { lo: 0, hi: W - L - R }, detail: { lo: W - L - R, hi: W - L } };
}

// Classify the first move past the dead zone: a mostly-vertical move is treated as
// a scroll/other gesture and aborts the drag (pane-swap-drag-design.md §4 line 2).
// A 45° tie counts as horizontal so a diagonal intent still swaps.
export function dragIntent(dx, dy, deadZone = DEAD_ZONE) {
  if (Math.hypot(dx, dy) < deadZone) return "pending";
  return Math.abs(dx) >= Math.abs(dy) ? "drag" : "abort";
}

// How far the pointer has entered the target pane past their shared boundary (0 if
// it has not crossed yet). The dragged and target panes are always adjacent, so the
// boundary is the target edge facing the dragged pane.
export function penetration(x, targetSpan, targetIsRight) {
  return targetIsRight
    ? Math.max(0, x - targetSpan.lo)
    : Math.max(0, targetSpan.hi - x);
}

// Commit rule: the pointer must cross the *midline* of the target pane, not merely
// touch the boundary. Overshooting past the far edge keeps it armed (intent is
// obvious); retreating back before the midline disarms it (reversible).
export function isArmed(x, draggedSpan, targetSpan) {
  const targetIsRight = targetSpan.lo + targetSpan.hi > draggedSpan.lo + draggedSpan.hi;
  const width = targetSpan.hi - targetSpan.lo;
  return penetration(x, targetSpan, targetIsRight) > width / 2;
}

export function usePaneSwapDrag({ isEnabled, getLayout, getGhostEl, onCommit }) {
  const dragging = ref(false);
  const draggedPane = ref(null); // "feed" | "detail"
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
  let rafId = 0;
  let cleanup = null;

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
      const next = isArmed(lastX, draggedSpan, targetSpan);
      if (next !== armed.value) armed.value = next;
    });
  }

  function beginDrag() {
    phase = "dragging";
    const spans = paneSpans(getLayout());
    draggedSpan = draggedPane.value === "feed" ? spans.feed : spans.detail;
    targetSpan = draggedPane.value === "feed" ? spans.detail : spans.feed;
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
    const shouldCommit = phase === "dragging" && armed.value;
    reset();
    if (shouldCommit) onCommit();
  }

  function onKey(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      reset();
    }
  }

  function onPaneDragStart({ pane, x, y, pointerType, button }) {
    if (phase !== "idle") return;
    if (!isEnabled()) return;
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

  // Tear down any in-flight drag if the host unmounts mid-gesture, so window
  // listeners and a pending rAF can never outlive the component.
  onBeforeUnmount(reset);

  return { dragging, draggedPane, armed, targetRect, onPaneDragStart };
}
