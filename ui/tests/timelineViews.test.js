import test from "node:test";
import assert from "node:assert/strict";

import {
  aggregateOptionChips,
  availableDisplayViews,
  BOARD_UNASSIGNED_ID,
  buildBoardGroups,
  compareEventsByColumn,
  countMindmapNodes,
  IMPLEMENTED_DISPLAY_STYLES,
  MINDMAP_LAYOUTS,
  mindmapRootData,
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

test("aggregateOptionChips flattens visible option columns in order, skipping text/hidden/invisible", () => {
  const columns = [
    SELECT_COL, // select: war/treaty
    { key: "place", label: "地点", type: "text", visible: true, order: 1 }, // non-option → skipped
    {
      key: "tags",
      label: "标签",
      type: "multiselect",
      visible: true,
      order: 2,
      options: [
        { id: "cn", label: "中国", color: "#f00" },
        { id: "uk", label: "英国", color: "#00f" },
      ],
    },
    { key: "hiddenOpt", label: "隐藏", type: "select", visible: true, order: 3, options: [{ id: "x", label: "X" }] },
    { key: "invis", label: "不可见", type: "select", visible: false, order: 4, options: [{ id: "y", label: "Y" }] },
  ];
  const event = { extra: { type: "war", place: "广州", tags: ["cn", "uk"], hiddenOpt: "x", invis: "y" } };

  const chips = aggregateOptionChips(event, columns, ["hiddenOpt"]);
  assert.deepEqual(chips.map((chip) => chip.label), ["战争", "中国", "英国"]);
});

test("aggregateOptionChips returns [] when no visible option column holds a value", () => {
  assert.deepEqual(aggregateOptionChips({ extra: { place: "x" } }, [{ key: "place", type: "text", visible: true }]), []);
  assert.deepEqual(aggregateOptionChips({ extra: {} }, [SELECT_COL]), []);
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

// --- W5 mindmap snapshot/tree helpers ---
test("mindmapRootData reads the root from a full snapshot", () => {
  const snapshot = { root: { data: { text: "中心" }, children: [{ data: { text: "枝" } }] }, layout: "mindMap", theme: {} };
  assert.equal(mindmapRootData(snapshot).data.text, "中心");
});

test("mindmapRootData rebuilds a root tree from an X6 snapshot", () => {
  const snapshot = {
    _fmt: "x6-mindmap-v1",
    cells: [
      { id: "root", x: 80, y: 80, width: 128, height: 38, data: { text: "中心主题", level: 0 } },
      { id: "branch", x: 260, y: 80, width: 108, height: 32, data: { text: "分支甲", level: 1 } },
      { id: "leaf", x: 420, y: 120, width: 92, height: 28, data: { text: "细节点", level: 2 } },
      { id: "e-root-branch", source: { cell: "root" }, target: { cell: "branch" } },
      { id: "e-branch-leaf", source: { cell: "branch" }, target: { cell: "leaf" } },
    ],
  };

  const root = mindmapRootData(snapshot);
  assert.equal(root.data.text, "中心主题");
  assert.equal(root.children[0].data.text, "分支甲");
  assert.equal(root.children[0].children[0].data.text, "细节点");
});

test("mindmapRootData reads the root from a legacy bare tree", () => {
  const tree = { data: { text: "旧根" }, children: [] };
  assert.equal(mindmapRootData(tree).data.text, "旧根");
});

test("mindmapRootData returns null for empty/malformed values", () => {
  assert.equal(mindmapRootData(null), null);
  assert.equal(mindmapRootData({}), null);
  assert.equal(mindmapRootData({ root: { children: [] } }), null); // no root.data
});

test("countMindmapNodes counts root plus all descendants", () => {
  const root = {
    data: { text: "r" },
    children: [
      { data: { text: "a" }, children: [{ data: { text: "a1" } }, { data: { text: "a2" } }] },
      { data: { text: "b" } },
    ],
  };
  assert.equal(countMindmapNodes(root), 5);
  assert.equal(countMindmapNodes(null), 0);
  assert.equal(countMindmapNodes({ data: { text: "solo" } }), 1);
});

test("MINDMAP_LAYOUTS exposes the X6 free/tree presets with stable keys", () => {
  const keys = MINDMAP_LAYOUTS.map((item) => item.key);
  assert.ok(keys.includes("free"));
  assert.ok(keys.includes("logicalStructure"));
  assert.ok(keys.includes("logicalStructureLeft"));
  assert.ok(keys.includes("organizationStructure"));
  assert.equal(new Set(keys).size, keys.length); // no dupes
  assert.ok(MINDMAP_LAYOUTS.every((item) => item.key && item.label));
});
