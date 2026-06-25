import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSingleLinePreview,
  buildTimelineCardLayout,
  buildTimelineCardLayouts,
  buildTimelineOffsetIndex,
} from "../src/services/pretextLayout.js";

const baseEvent = {
  id: 101,
  dateKey: 18400601,
  headline: "鸦片战争",
  displayLabel: "1840-06-01 鸦片战争",
  bodyMarkdown:
    "## 背景\n鸦片战争爆发，清政府被迫面对来自海上的军事压力，中国近代史由此展开新的阶段。",
  tags: ["war", "war", "diplomacy"],
  items: [{ tag: "war", text: "legacy fallback" }],
};

test("buildTimelineCardLayout creates a clamped Chinese markdown preview", () => {
  const layout = buildTimelineCardLayout(baseEvent, { textWidth: 260, titleWidth: 220 });

  assert.equal(layout.eventId, 101);
  assert.equal(layout.cardWidth, 531);
  assert.ok(layout.previewText.includes("背景"));
  assert.ok(layout.previewText.endsWith("..."));
  assert.ok(layout.previewLineCount <= 2);
  assert.ok(layout.estimatedHeight >= 147);
  assert.ok(layout.estimatedHeight <= 175);
});

test("buildTimelineCardLayout only changes layout output when width changes", () => {
  const original = structuredClone(baseEvent);
  const narrow = buildTimelineCardLayout(baseEvent, { textWidth: 220 });
  const wide = buildTimelineCardLayout(baseEvent, { textWidth: 480 });

  assert.notEqual(narrow.previewText, wide.previewText);
  assert.deepEqual(baseEvent, original);
});

test("buildTimelineCardLayout handles legacy items, empty body, long words, and punctuation", () => {
  const legacy = buildTimelineCardLayout({
    id: 1,
    headline: "Legacy",
    tags: [],
    items: [{ tag: "science", text: "来自旧 items 的正文会作为摘要回退。" }],
  });
  const empty = buildTimelineCardLayout({ id: 2, headline: "Empty", tags: [], items: [] });
  const longWord = buildTimelineCardLayout({
    id: 3,
    headline: "Long",
    bodyMarkdown: "supercalifragilisticexpialidocious".repeat(8),
    tags: ["custom"],
  });
  const punctuation = buildTimelineCardLayout({ id: 4, headline: "Marks", bodyMarkdown: "。。。。。。！！！？？？" });

  assert.ok(legacy.previewText.includes("旧 items"));
  assert.equal(empty.previewText, "");
  assert.ok(longWord.previewText.length > 0);
  assert.ok(punctuation.previewText.length > 0);
});

test("buildSingleLinePreview clamps to one preview row", () => {
  const preview = buildSingleLinePreview("辛亥革命推翻帝制并推动共和制度建立".repeat(4), "timelineCardPreview", 160);

  assert.ok(preview.endsWith("..."));
  assert.ok(preview.length < 30);
});

test("buildTimelineCardLayouts and offset index support date positioning", () => {
  const events = [
    { ...baseEvent, id: 1, dateKey: 18400601 },
    { ...baseEvent, id: 2, dateKey: 19111010, headline: "辛亥革命" },
  ];
  const layouts = buildTimelineCardLayouts(events);
  const index = buildTimelineOffsetIndex(
    [
      { key: "1840", items: [events[0]] },
      { key: "1911", items: [events[1]] },
    ],
    layouts
  );

  assert.deepEqual(index.map((item) => item.eventId), [1, 2]);
  assert.ok(index[1].estimatedTop > index[0].estimatedTop);
  assert.equal(index.find((item) => item.dateKey >= 19000101).eventId, 2);
});
