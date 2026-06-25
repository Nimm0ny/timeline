import test from "node:test";
import assert from "node:assert/strict";

import {
  buildReadableDetailGroups,
  buildEditorDraft,
  buildEventPreview,
  buildTimelineGridTemplate,
  buildVisibleTimelineColumns,
  collectEventTags,
  groupTimelineEvents,
  normalizeEventExtra,
  normalizeTopicColumns,
} from "../src/utils/timelineNotes.js";

const events = [
  {
    id: 2,
    dateKey: 19111010,
    isoDate: "1911-10-10",
    dateParts: { year: 1911, month: 10, day: 10 },
    headline: "Republic Revolution",
    displayLabel: "1911-10-10 Republic Revolution",
    era: "Modern China",
    bodyMarkdown: "## Result\nPolitical system changed.",
    tags: ["politics", "reform"],
    items: [{ tag: "politics", text: "Political system changed." }],
  },
  {
    id: 1,
    dateKey: 18400601,
    isoDate: "1840-06-01",
    dateParts: { year: 1840, month: 6, day: 1 },
    headline: "Trade Conflict",
    displayLabel: "1840-06-01 Trade Conflict",
    era: "Modern China",
    bodyMarkdown: "## Context\nTreaty port pressure begins.",
    tags: ["war", "diplomacy"],
    items: [{ tag: "war", text: "Treaty port pressure begins." }],
  },
  {
    id: 3,
    dateKey: 18400301,
    isoDate: "1840-03-01",
    dateParts: { year: 1840, month: 3, day: 1 },
    headline: "Archive Review",
    displayLabel: "1840-03-01 Archive Review",
    era: "Source Notes",
    bodyMarkdown: "Early archive pass.",
    tags: ["science"],
    items: [{ tag: "science", text: "Early archive pass." }],
  },
];

test("groupTimelineEvents sorts events and filters by search query", () => {
  const groups = groupTimelineEvents(events, "year", "trade");

  assert.equal(groups.length, 1);
  assert.equal(groups[0].key, "1840");
  assert.deepEqual(groups[0].items.map((event) => event.id), [1]);
});

test("groupTimelineEvents keeps chronological order within grouped years", () => {
  const groups = groupTimelineEvents(events, "year", "");

  assert.deepEqual(groups.map((group) => group.key), ["1840", "1911"]);
  assert.deepEqual(groups[0].items.map((event) => event.id), [3, 1]);
});

test("buildEventPreview strips markdown and truncates to the requested length", () => {
  const preview = buildEventPreview(
    {
      bodyMarkdown: "## Heading\nThis **timeline** entry has enough text for preview trimming.",
      items: [],
    },
    22
  );

  assert.equal(preview, "Heading This timeline...");
});

test("collectEventTags deduplicates structured tags and preserves fallback item tags", () => {
  const structured = collectEventTags({ tags: ["war", "war", "diplomacy"], items: [] });
  const fallback = collectEventTags({
    tags: [],
    items: [
      { tag: "science", text: "A" },
      { tag: "science", text: "B" },
      { tag: "custom", text: "C" },
    ],
  });

  assert.deepEqual(structured.map((tag) => tag.value), ["war", "diplomacy"]);
  assert.deepEqual(fallback.map((tag) => tag.value), ["science", "custom"]);
});

test("buildEditorDraft clones event DTO fields for safe editing", () => {
  const event = {
    id: 99,
    dateParts: { year: 1949, month: 10, day: 1 },
    headline: "Founding Note",
    era: "Modern",
    bodyMarkdown: "",
    tags: ["politics"],
    attachments: [{ id: 7, name: "source.pdf", filename: "source.pdf" }],
    relatedEventIds: [1],
    relatedEvents: [{ id: 1, headline: "Trade Conflict" }],
    items: [{ tag: "politics", text: "Fallback body" }],
  };
  const draft = buildEditorDraft(event);

  assert.equal(draft.dateYear, 1949);
  assert.equal(draft.bodyMarkdown, "Fallback body");
  assert.deepEqual(draft.tags, ["politics"]);
  assert.deepEqual(draft.relatedEventIds, [1]);

  draft.attachments[0].name = "changed.pdf";
  assert.equal(draft.attachments[0].name, "changed.pdf");
  assert.equal(event.attachments[0].name, "source.pdf");
});

test("buildReadableDetailGroups removes empty read-mode support groups", () => {
  const groups = buildReadableDetailGroups({
    tags: ["", " politics ", "politics"],
    attachments: [{ name: "  " }, { filename: "source.pdf" }],
    relatedEvents: [{ id: 1, headline: "" }, { id: 2, headline: "Trade Conflict" }],
  });

  assert.deepEqual(groups.tags, ["politics"]);
  assert.deepEqual(groups.attachments.map((attachment) => attachment.filename), ["source.pdf"]);
  assert.deepEqual(groups.relatedEvents.map((event) => event.id), [2]);
});

test("normalizeTopicColumns validates and sorts user-defined columns", () => {
  const columns = normalizeTopicColumns([
    { key: "source", label: "来源", type: "text", width: 180, order: 2, visible: true },
    { key: "place", label: "地点", type: "text", width: 88, order: 1, visible: false },
    { key: "type", label: "Reserved", type: "text", width: 50, order: 0, visible: true },
  ]);

  assert.deepEqual(
    columns.map((column) => ({ key: column.key, width: column.width, visible: column.visible })),
    [
      { key: "place", width: 88, visible: false },
      { key: "source", width: 180, visible: true },
    ]
  );
});

test("buildVisibleTimelineColumns and normalizeEventExtra honor custom column visibility and whitelist", () => {
  const topicColumns = normalizeTopicColumns([
    { key: "place", label: "地点", type: "text", width: 92, order: 0, visible: true },
    { key: "source", label: "来源", type: "text", width: 110, order: 1, visible: false },
  ]);
  const columns = buildVisibleTimelineColumns(topicColumns, { type: true, tags: false });
  const extra = normalizeEventExtra({ place: "广州", source: "档案馆", ignored: "drop" }, topicColumns);

  assert.deepEqual(columns.map((column) => column.key), ["time", "title", "type", "place"]);
  assert.equal(buildTimelineGridTemplate(topicColumns, { type: true, tags: false }), "28px 96px minmax(0,1fr) 72px 92px 30px");
  assert.deepEqual(extra, { place: "广州", source: "档案馆" });
});
