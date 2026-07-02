import test from "node:test";
import assert from "node:assert/strict";

import {
  buildX6SeedSnapshot,
  computeMindmapRoute,
  markdownToTree,
  resolveReparentTarget,
  treeToX6Cells,
  x6CellsToMarkdown,
  x6SnapshotToTree,
} from "../src/utils/mindmapX6.js";

test("treeToX6Cells preserves legacy note metadata through an X6 roundtrip", () => {
  const legacyTree = {
    data: {
      text: "<p>中心主题</p>",
      note: "<p>根备注</p>",
      hyperlink: "https://example.com/root",
      tag: ["核心", "入口"],
    },
    children: [
      {
        data: {
          text: "<p>分支甲</p>",
          note: "<p>分支备注</p>",
          hyperlink: "https://example.com/branch",
          tag: ["分支"],
        },
        children: [],
      },
    ],
  };

  const { cells } = treeToX6Cells(legacyTree);
  const roundtrip = x6SnapshotToTree({ _fmt: "x6-mindmap-v1", cells });

  assert.equal(roundtrip.data.text, "中心主题");
  assert.equal(roundtrip.data.note, "<p>根备注</p>");
  assert.equal(roundtrip.data.hyperlink, "https://example.com/root");
  assert.deepEqual(roundtrip.data.tag, ["核心", "入口"]);
  assert.equal(roundtrip.children[0].data.note, "<p>分支备注</p>");
  assert.equal(roundtrip.children[0].data.hyperlink, "https://example.com/branch");
  assert.deepEqual(roundtrip.children[0].data.tag, ["分支"]);
});

test("x6CellsToMarkdown emits siblings in visual top-to-bottom order", () => {
  const cells = [
    { id: "root", x: 80, y: 80, width: 128, height: 38, data: { text: "中心主题", level: 0 } },
    { id: "lower", x: 260, y: 180, width: 108, height: 32, data: { text: "较低分支", level: 1 } },
    { id: "upper", x: 260, y: 100, width: 108, height: 32, data: { text: "较高分支", level: 1 } },
    { id: "e-root-lower", source: { cell: "root" }, target: { cell: "lower" } },
    { id: "e-root-upper", source: { cell: "root" }, target: { cell: "upper" } },
  ];

  assert.equal(x6CellsToMarkdown(cells), "# 中心主题\n- 较高分支\n- 较低分支\n");
});

test("x6CellsToMarkdown encodes bold, hyperlink, and tags (clean route)", () => {
  const cells = [
    { id: "root", x: 80, y: 80, width: 128, height: 38, data: { text: "中心主题", level: 0, fontWeight: "bold" } },
    { id: "link", x: 260, y: 80, width: 108, height: 32, data: { text: "官网", level: 1, hyperlink: "https://ex.com" } },
    { id: "tagged", x: 260, y: 160, width: 108, height: 32, data: { text: "要点", level: 1, tag: ["重点", "待办"] } },
    { id: "e-root-link", source: { cell: "root" }, target: { cell: "link" } },
    { id: "e-root-tagged", source: { cell: "root" }, target: { cell: "tagged" } },
  ];

  assert.equal(x6CellsToMarkdown(cells), "# **中心主题**\n- [官网](https://ex.com)\n- 要点 #重点 #待办\n");
});

test("markdownToTree decodes bold, hyperlink, and trailing tags into node data", () => {
  const tree = markdownToTree("# **中心主题**\n- [官网](https://ex.com)\n- 要点 #重点 #待办\n");

  assert.equal(tree.data.text, "中心主题");
  assert.equal(tree.data.fontWeight, "bold");
  assert.equal(tree.children[0].data.text, "官网");
  assert.equal(tree.children[0].data.hyperlink, "https://ex.com");
  assert.equal(tree.children[1].data.text, "要点");
  assert.deepEqual(tree.children[1].data.tag, ["重点", "待办"]);
});

test("markdown node emphasis survives an export -> import -> export round trip", () => {
  const md = "# **根**\n- [链接](https://a.b)\n- 带标签 #x #y\n";
  const { cells } = treeToX6Cells(markdownToTree(md));

  assert.equal(x6CellsToMarkdown(cells), md);
});

test("markdownToTree keeps partial inline markup as literal text (node bold is all-or-nothing)", () => {
  const tree = markdownToTree("# 根\n- 一半 **粗** 字\n");

  assert.equal(tree.children[0].data.text, "一半 **粗** 字");
  assert.equal(tree.children[0].data.fontWeight, undefined);
});

test("a tag-only node keeps itself and its subtree through a markdown round trip", () => {
  const md = "# 根\n- #孤儿\n  - 子节点\n";
  const tree = markdownToTree(md);

  assert.equal(tree.children[0].data.text, "");
  assert.deepEqual(tree.children[0].data.tag, ["孤儿"]);
  assert.equal(tree.children[0].children[0].data.text, "子节点");

  const { cells } = treeToX6Cells(tree);
  assert.equal(x6CellsToMarkdown(cells), md);
});

test("markdownToTree imports a document whose root heading is tag-only", () => {
  const tree = markdownToTree("# #只有标签\n- 子\n");

  assert.notEqual(tree, null);
  assert.deepEqual(tree.data.tag, ["只有标签"]);
  assert.equal(tree.children[0].data.text, "子");
});

test("x6CellsToMarkdown strips inner # from tags so they re-parse as tags", () => {
  const cells = [{ id: "r", x: 0, y: 0, width: 128, height: 38, data: { text: "标题", level: 0, tag: ["a#b"] } }];

  assert.equal(x6CellsToMarkdown(cells), "# 标题 #ab\n");
});

test("buildX6SeedSnapshot writes the phase-2 default edge routing and style", () => {
  const snapshot = buildX6SeedSnapshot("中心主题");

  assert.equal(snapshot.edgeRouting, "smart-orthogonal");
  assert.equal(snapshot.edgeStyle, "rounded");
});

test("computeMindmapRoute avoids a blocking node on the direct horizontal path", () => {
  const route = computeMindmapRoute(
    { id: "parent", x: 0, y: 80, width: 120, height: 40 },
    { id: "child", x: 320, y: 80, width: 120, height: 40 },
    {
      edgeStyle: "rounded",
      nodeBoxes: [{ id: "blocker", x: 150, y: 70, width: 120, height: 60 }],
    }
  );

  assert.equal(route.vertices.length >= 2, true);
  assert.equal(route.vertices.some((point) => point.y !== 100), true);
});

test("resolveReparentTarget attaches a dragged node to the box it was dropped on", () => {
  const nodes = [
    { id: "root", x: 0, y: 0, w: 100, h: 40, parentId: "" },
    { id: "A", x: 210, y: 105, w: 80, h: 30, parentId: "root" }, // centre (250,120) sits inside B
    { id: "B", x: 200, y: 100, w: 100, h: 40, parentId: "root" },
  ];
  assert.equal(resolveReparentTarget("A", nodes), "B");
});

test("resolveReparentTarget never reparents the root node", () => {
  const nodes = [
    { id: "root", x: 200, y: 100, w: 100, h: 40, parentId: "" },
    { id: "A", x: 190, y: 95, w: 120, h: 60, parentId: "root" },
  ];
  assert.equal(resolveReparentTarget("root", nodes), "");
});

test("resolveReparentTarget refuses a drop onto the moved node's own descendant (no cycle)", () => {
  const nodes = [
    { id: "root", x: 0, y: 0, w: 100, h: 40, parentId: "" },
    { id: "B", x: 205, y: 105, w: 80, h: 30, parentId: "root" }, // centre (245,120) sits inside its child C
    { id: "C", x: 200, y: 100, w: 100, h: 40, parentId: "B" },
  ];
  assert.equal(resolveReparentTarget("B", nodes), "");
});

test("resolveReparentTarget treats a drop on the current parent as a no-op", () => {
  const nodes = [
    { id: "root", x: 200, y: 100, w: 120, h: 60, parentId: "" },
    { id: "A", x: 240, y: 120, w: 40, h: 20, parentId: "root" }, // centre inside root, already its parent
  ];
  assert.equal(resolveReparentTarget("A", nodes), "");
});

test("resolveReparentTarget returns empty when dropped on empty space", () => {
  const nodes = [
    { id: "root", x: 0, y: 0, w: 100, h: 40, parentId: "" },
    { id: "A", x: 500, y: 500, w: 80, h: 30, parentId: "root" },
  ];
  assert.equal(resolveReparentTarget("A", nodes), "");
});
