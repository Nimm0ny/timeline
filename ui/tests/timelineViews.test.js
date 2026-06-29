import test from "node:test";
import assert from "node:assert/strict";

import {
  availableDisplayViews,
  compareEventsByColumn,
  IMPLEMENTED_DISPLAY_STYLES,
  resolveDisplayStyle,
} from "../src/utils/timelineNotes.js";

test("availableDisplayViews lists only implemented views, flagged per capability", () => {
  const views = availableDisplayViews(["timeline", "table", "list", "board"]);
  assert.deepEqual(
    views.map((view) => view.key),
    IMPLEMENTED_DISPLAY_STYLES
  );
  assert.equal(views.find((view) => view.key === "timeline").enabled, true);
  assert.equal(views.find((view) => view.key === "table").enabled, true);
  // board is capable on the backend but not an implemented view → never listed in W2.
  assert.equal(views.some((view) => view.key === "board"), false);
});

test("availableDisplayViews disables an incapable view (timeline without dated notes)", () => {
  const views = availableDisplayViews(["table", "list"]);
  assert.equal(views.find((view) => view.key === "timeline").enabled, false);
  assert.equal(views.find((view) => view.key === "table").enabled, true);
});

test("availableDisplayViews treats empty capabilities as all-enabled (back-compat)", () => {
  assert.ok(availableDisplayViews([]).every((view) => view.enabled));
});

test("resolveDisplayStyle keeps a capable implemented style", () => {
  assert.equal(resolveDisplayStyle("table", ["timeline", "table", "list"]), "table");
  assert.equal(resolveDisplayStyle("list", ["table", "list"]), "list");
});

test("resolveDisplayStyle falls back when the style is unimplemented or incapable", () => {
  // board is not implemented in W2 → fall back to the first capable implemented view.
  assert.equal(resolveDisplayStyle("board", ["timeline", "table", "list", "board"]), "timeline");
  // timeline persisted but no dated events → fall back to table.
  assert.equal(resolveDisplayStyle("timeline", ["table", "list"]), "table");
});

test("resolveDisplayStyle respects the persisted style when capabilities are unknown", () => {
  assert.equal(resolveDisplayStyle("table", []), "table");
  assert.equal(resolveDisplayStyle("timeline", []), "timeline");
});

test("compareEventsByColumn sorts by time via dateKey, direction-aware", () => {
  const a = { id: 1, dateKey: 18400101 };
  const b = { id: 2, dateKey: 18420101 };
  assert.deepEqual([b, a].sort(compareEventsByColumn({ key: "time" }, 1)).map((e) => e.id), [1, 2]);
  assert.deepEqual([a, b].sort(compareEventsByColumn({ key: "time" }, -1)).map((e) => e.id), [2, 1]);
});

test("compareEventsByColumn sorts a free-text column by its rendered value", () => {
  const column = { key: "place", type: "text" };
  const a = { id: 1, dateKey: 1, extra: { place: "Berlin" } };
  const b = { id: 2, dateKey: 2, extra: { place: "Athens" } };
  // Athens < Berlin → id 2 first.
  assert.deepEqual([a, b].sort(compareEventsByColumn(column, 1)).map((e) => e.id), [2, 1]);
});

test("compareEventsByColumn sorts a checkbox column checked-first", () => {
  const column = { key: "done", type: "checkbox" };
  const a = { id: 1, dateKey: 1, extra: { done: "false" } };
  const b = { id: 2, dateKey: 2, extra: { done: "true" } };
  assert.deepEqual([a, b].sort(compareEventsByColumn(column, 1)).map((e) => e.id), [2, 1]);
});
