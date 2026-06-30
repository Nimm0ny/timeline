import test from "node:test";
import assert from "node:assert/strict";

import { treeToX6Cells, x6CellsToMarkdown, x6SnapshotToTree } from "../src/utils/mindmapX6.js";

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
