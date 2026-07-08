import test from "node:test";
import assert from "node:assert/strict";

import { normalizeNoteNode, normalizeSummaryNode } from "../src/models/noteNodes.js";

test("normalizeNoteNode preserves structured event fields", () => {
  const node = normalizeNoteNode({
    id: 1,
    dateKey: 18400101,
    sortKey: 18400101,
    isoDate: "1840-01-01",
    dateParts: { year: 1840, month: 1, day: 1 },
    headline: "Opium War Begins",
    displayLabel: "1840-01-01 Opium War Begins",
    era: "Modern China",
    image: null,
    items: [{ tag: "war", text: "Conflict begins." }],
  });
  assert.equal(node.headline, "Opium War Begins");
  assert.equal(node.dateParts.month, 1);
  assert.equal(node.items.length, 1);
});

test("normalizeSummaryNode preserves bucket metadata", () => {
  const node = normalizeSummaryNode({
    id: "year:1840",
    nodeType: "summary",
    groupBy: "year",
    bucketKey: 1840,
    dateKey: 18400101,
    sortKey: 18400101,
    displayLabel: "1840",
    headline: "1840",
    era: "2 events",
    noteCount: 2,
    rangeStartKey: 18400101,
    rangeEndKey: 18401231,
    rangeStartDate: "1840-01-01",
    rangeEndDate: "1840-12-31",
    items: [{ tag: "summary", text: "2 events in 1840" }],
  });
  assert.equal(node.groupBy, "year");
  assert.equal(node.noteCount, 2);
  assert.equal(node.rangeEndDate, "1840-12-31");
});
