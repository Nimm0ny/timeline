import test from "node:test";
import assert from "node:assert/strict";

import {
  availableDisplayViews,
  BOARD_UNASSIGNED_ID,
  buildBoardGroups,
  compareEventsByColumn,
  IMPLEMENTED_DISPLAY_STYLES,
  pickBoardColumn,
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
  // W3: board/gallery/outline are implemented and listed; each flagged per capability.
  assert.equal(views.find((view) => view.key === "board").enabled, true);
  assert.equal(views.find((view) => view.key === "gallery").enabled, false);
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

test("resolveDisplayStyle keeps a now-implemented board/gallery/outline when capable", () => {
  assert.equal(resolveDisplayStyle("board", ["timeline", "table", "list", "board"]), "board");
  assert.equal(resolveDisplayStyle("gallery", ["table", "list", "gallery"]), "gallery");
  assert.equal(resolveDisplayStyle("outline", ["table", "list", "outline"]), "outline");
});

test("resolveDisplayStyle falls back when the style is incapable", () => {
  // board persisted but the notebook lost its option column → first capable view.
  assert.equal(resolveDisplayStyle("board", ["timeline", "table", "list"]), "timeline");
  // gallery persisted but no images, no dated events → table.
  assert.equal(resolveDisplayStyle("gallery", ["table", "list"]), "table");
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

const SELECT_COL = {
  key: "type",
  label: "类型",
  type: "select",
  visible: true,
  order: 0,
  options: [
    { id: "war", label: "战争", color: "#c00" },
    { id: "treaty", label: "条约", color: "#06c" },
  ],
};

test("pickBoardColumn prefers the first visible select column", () => {
  const columns = [
    { key: "tags", label: "标签", type: "multiselect", visible: true, order: 0, options: [{ id: "a", label: "A" }] },
    SELECT_COL,
  ];
  assert.equal(pickBoardColumn(columns).key, "type");
});

test("pickBoardColumn falls back to a multiselect, and is null without any option column", () => {
  const multi = { key: "tags", label: "标签", type: "multiselect", visible: true, order: 0, options: [{ id: "a", label: "A" }] };
  assert.equal(pickBoardColumn([multi]).key, "tags");
  assert.equal(pickBoardColumn([{ key: "place", label: "地点", type: "text", visible: true, order: 0 }]), null);
  assert.equal(pickBoardColumn([]), null);
});

test("buildBoardGroups buckets by option order, chronological within a column", () => {
  const events = [
    { id: 1, dateKey: 18600101, extra: { type: "war" } },
    { id: 2, dateKey: 18400101, extra: { type: "war" } },
    { id: 3, dateKey: 18420101, extra: { type: "treaty" } },
  ];
  const groups = buildBoardGroups(events, SELECT_COL);
  assert.deepEqual(groups.map((g) => g.id), ["war", "treaty"]);
  // war bucket sorted by dateKey asc → id 2 (1840) before id 1 (1860).
  assert.deepEqual(groups[0].items.map((e) => e.id), [2, 1]);
  assert.deepEqual(groups[1].items.map((e) => e.id), [3]);
});

test("buildBoardGroups collects empty/unknown values into a trailing 未分类 bucket", () => {
  const events = [
    { id: 1, dateKey: 1, extra: { type: "war" } },
    { id: 2, dateKey: 2, extra: { type: "" } }, // cleared
    { id: 3, dateKey: 3, extra: { type: "ghost" } }, // value with no matching option
  ];
  const groups = buildBoardGroups(events, SELECT_COL);
  const last = groups.at(-1);
  assert.equal(last.id, BOARD_UNASSIGNED_ID);
  assert.deepEqual(last.items.map((e) => e.id), [2, 3]);
  // option buckets always render even when empty (stable board shape).
  assert.equal(groups.find((g) => g.id === "treaty").items.length, 0);
});

test("buildBoardGroups puts a multiselect event under each of its values", () => {
  const multi = {
    key: "tags",
    label: "标签",
    type: "multiselect",
    visible: true,
    order: 0,
    options: [
      { id: "cn", label: "中国" },
      { id: "uk", label: "英国" },
    ],
  };
  const events = [{ id: 1, dateKey: 1, extra: { tags: ["cn", "uk"] } }];
  const groups = buildBoardGroups(events, multi);
  assert.deepEqual(groups.find((g) => g.id === "cn").items.map((e) => e.id), [1]);
  assert.deepEqual(groups.find((g) => g.id === "uk").items.map((e) => e.id), [1]);
});

test("buildBoardGroups returns [] for a non-option column", () => {
  assert.deepEqual(buildBoardGroups([{ id: 1 }], { key: "place", type: "text" }), []);
});

test("buildBoardGroups dedups a repeated multiselect value (one card per bucket)", () => {
  const multi = {
    key: "tags", label: "标签", type: "multiselect", visible: true, order: 0,
    options: [{ id: "cn", label: "中国" }],
  };
  // Malformed extra: the same option id repeated. The event must land once.
  const events = [{ id: 1, dateKey: 1, extra: { tags: ["cn", "cn"] } }];
  const groups = buildBoardGroups(events, multi);
  assert.deepEqual(groups.find((g) => g.id === "cn").items.map((e) => e.id), [1]);
});
