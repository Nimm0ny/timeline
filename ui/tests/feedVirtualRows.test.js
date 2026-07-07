import test from "node:test";
import assert from "node:assert/strict";

import {
  chunkGalleryRows,
  flattenGroupedRows,
  sliceVirtualWindow,
  shouldRequestMoreForVirtualItems,
} from "../src/composables/useFeedVirtualRows.js";

test("flattenGroupedRows inserts one header before each group's events", () => {
  const rows = flattenGroupedRows([
    { key: "a", title: "甲", subtitle: "1 条", items: [{ id: 1 }, { id: 2 }] },
    { key: "b", title: "乙", subtitle: "2 条", items: [{ id: 3 }] },
  ]);

  assert.deepEqual(
    rows.map((row) => [row.kind, row.key]),
    [
      ["group-header", "group:a"],
      ["event-row", "event:1"],
      ["event-row", "event:2"],
      ["group-header", "group:b"],
      ["event-row", "event:3"],
    ]
  );
});

test("chunkGalleryRows groups events into fixed-width visual rows", () => {
  const rows = chunkGalleryRows([{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }], 2);

  assert.deepEqual(
    rows.map((row) => row.items.map((item) => item.id)),
    [[1, 2], [3, 4], [5]]
  );
});

test("sliceVirtualWindow returns a padded visible range from scroll metrics", () => {
  const window = sliceVirtualWindow({
    count: 100,
    scrollTop: 330,
    viewportHeight: 165,
    estimateSize: 33,
    overscan: 2,
  });

  assert.equal(window.startIndex, 8);
  assert.equal(window.endIndex, 17);
  assert.equal(window.topSpacerPx, 264);
  assert.equal(window.bottomSpacerPx, 2706);
  assert.equal(window.totalSize, 3300);
});

test("shouldRequestMoreForVirtualItems fires near the end and honors guards", () => {
  assert.equal(
    shouldRequestMoreForVirtualItems({
      count: 100,
      lastVisibleIndex: 95,
      hasMore: true,
      threshold: 4,
    }),
    true
  );
  assert.equal(
    shouldRequestMoreForVirtualItems({
      count: 100,
      lastVisibleIndex: 40,
      hasMore: true,
      threshold: 4,
    }),
    false
  );
  assert.equal(
    shouldRequestMoreForVirtualItems({
      count: 100,
      lastVisibleIndex: 99,
      hasMore: true,
      loadingMore: true,
    }),
    false
  );
});
