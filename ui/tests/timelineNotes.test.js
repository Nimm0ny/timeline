import test from "node:test";
import assert from "node:assert/strict";

import {
  buildPropertyUsage,
  buildOptionId,
  buildEditorDraft,
  buildEventPreview,
  buildFavoriteFacetRows,
  buildGlobalFavoriteEvents,
  buildPropertyKey,
  buildPropertyRows,
  buildRecentFavoriteEvents,
  canChangePropertyType,
  editablePropertyTypeChoices,
  buildReadableDetailGroups,
  buildSearchHighlightSegments,
  buildTimelineGridTemplate,
  buildVisibleTimelineColumns,
  clampTimelineColumnWidth,
  emptyTimelineColumnKeys,
  eventColumnHasValue,
  eventColumnValue,
  eventHasDate,
  formatEventDate,
  formatEventDisplayDate,
  filterFavoriteEventsByScope,
  groupTimelineEvents,
  isCheckboxChecked,
  mindmapPlainText,
  matchesPropertyFilter,
  normalizeEventExtra,
  normalizeTopicColumns,
  propertyHref,
  resolvePropertyChips,
  serializeTopicColumnsDraft,
  timelineTimeColumnWidth,
} from "../src/utils/timelineNotes.js";

const tagsColumn = {
  key: "tags",
  label: "标签",
  type: "multiselect",
  order: 1,
  visible: true,
  options: [
    { id: "war", label: "战争", color: "var(--t-war)" },
    { id: "politics", label: "政治", color: "var(--t-politics)" },
    { id: "reform", label: "改革", color: "var(--t-reform)" },
  ],
};

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
    extra: { tags: ["politics", "reform"] },
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
    extra: { tags: ["war"] },
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
    extra: { tags: [] },
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

test("groupTimelineEvents can search by resolved option label", () => {
  const groups = groupTimelineEvents(events, "year", "政治", [tagsColumn]);
  assert.deepEqual(groups.flatMap((group) => group.items.map((event) => event.id)), [2]);
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

test("buildEventPreview uses a stable placeholder for markdown images", () => {
  const preview = buildEventPreview(
    {
      bodyMarkdown: "正文前 ![现场照片](/images/site.png) 正文后 [来源](https://example.com)",
      items: [],
    },
    80
  );

  assert.equal(preview, "正文前 [图片] 正文后 来源");
});

test("buildEventPreview and search can use lightweight index preview text", () => {
  const event = { headline: "Index Row", preview: "轻量索引预览文本", extra: {} };

  assert.equal(buildEventPreview(event, 20), "轻量索引预览文本");
  assert.equal(groupTimelineEvents([event], "era", "索引").length, 1);
});

test("buildGlobalFavoriteEvents returns live favorites across topics in timeline order", () => {
  const rows = buildGlobalFavoriteEvents([
    { id: 5, topicId: 2, dateKey: 19110101, favorite: true },
    { id: 2, topicId: 1, dateKey: 18400101, favorite: true },
    { id: 3, topicId: 1, dateKey: 18400201, favorite: false },
    { id: 4, topicId: 3, dateKey: 18400301, favorite: true, deletedAt: "2026-01-01T00:00:00Z" },
  ]);

  assert.deepEqual(rows.map((event) => [event.id, event.topicId]), [
    [2, 1],
    [5, 2],
  ]);
});

test("buildRecentFavoriteEvents prefers favoriteAt and caps to five", () => {
  const rows = buildRecentFavoriteEvents([
    { id: 1, favoriteAt: "2026-06-20T00:00:00Z" },
    { id: 2, favoriteAt: "2026-06-30T00:00:00Z" },
    { id: 3, favoriteAt: "2026-06-25T00:00:00Z" },
    { id: 4, favoriteAt: "2026-06-29T00:00:00Z" },
    { id: 5, favoriteAt: "2026-06-28T00:00:00Z" },
    { id: 6, favoriteAt: "2026-06-27T00:00:00Z" },
  ]);

  assert.deepEqual(rows.map((event) => event.id), [2, 4, 5, 6, 3]);
});

test("buildFavoriteFacetRows aggregates type and tag usage across notebooks", () => {
  const topics = [
    {
      id: 1,
      title: "党史",
      columns: [
        {
          key: "type",
          label: "类型",
          type: "select",
          options: [
            { id: "war", label: "战争", color: "var(--t-war)" },
            { id: "politics", label: "政治", color: "var(--t-politics)" },
          ],
        },
        tagsColumn,
      ],
    },
    {
      id: 2,
      title: "近代史",
      columns: [
        {
          key: "type",
          label: "类型",
          type: "select",
          options: [{ id: "reform", label: "改革", color: "var(--t-reform)" }],
        },
        tagsColumn,
      ],
    },
  ];
  const favorites = [
    { id: 1, topicId: 1, extra: { type: "war", tags: ["war", "politics"] } },
    { id: 2, topicId: 1, extra: { type: "politics", tags: ["politics"] } },
    { id: 3, topicId: 2, extra: { type: "reform", tags: ["reform", "politics"] } },
  ];

  assert.deepEqual(
    Object.fromEntries(
      buildFavoriteFacetRows(favorites, topics, "type").map((row) => [row.key, { label: row.label, displayLabel: row.displayLabel, count: row.count }])
    ),
    {
      "1:politics": { label: "政治", displayLabel: "政治", count: 1 },
      "1:war": { label: "战争", displayLabel: "战争", count: 1 },
      "2:reform": { label: "改革", displayLabel: "改革", count: 1 },
    }
  );
  assert.deepEqual(
    Object.fromEntries(
      buildFavoriteFacetRows(favorites, topics, "tags").map((row) => [row.key, { label: row.label, displayLabel: row.displayLabel, count: row.count }])
    ),
    {
      "1:politics": { label: "政治", displayLabel: "政治 · 党史", count: 2 },
      "1:war": { label: "战争", displayLabel: "战争", count: 1 },
      "2:politics": { label: "政治", displayLabel: "政治 · 近代史", count: 1 },
      "2:reform": { label: "改革", displayLabel: "改革", count: 1 },
    }
  );
});

test("filterFavoriteEventsByScope supports current notebook, recent, topic, type, and tag scopes", () => {
  const topics = [
    { id: 1, title: "党史", columns: [{ key: "type", label: "类型", type: "select", options: [{ id: "war", label: "战争" }] }, tagsColumn] },
    { id: 2, title: "近代史", columns: [{ key: "type", label: "类型", type: "select", options: [{ id: "reform", label: "改革" }] }, tagsColumn] },
  ];
  const favorites = [
    { id: 1, topicId: 1, dateKey: 18400101, favoriteAt: "2026-06-10T00:00:00Z", extra: { type: "war", tags: ["war"] } },
    { id: 2, topicId: 2, dateKey: 19110101, favoriteAt: "2026-06-30T00:00:00Z", extra: { type: "reform", tags: ["politics"] } },
    { id: 3, topicId: 1, dateKey: 18400201, favoriteAt: "2026-06-29T00:00:00Z", extra: { type: "war", tags: ["politics"] } },
  ];

  assert.deepEqual(filterFavoriteEventsByScope(favorites, { kind: "current-topic" }, topics, 1).map((event) => event.id), [1, 3]);
  assert.deepEqual(filterFavoriteEventsByScope(favorites, { kind: "topic", topicId: 2 }, topics, 1).map((event) => event.id), [2]);
  assert.deepEqual(filterFavoriteEventsByScope(favorites, { kind: "type", value: "war", topicId: 1 }, topics, 1).map((event) => event.id), [1, 3]);
  assert.deepEqual(filterFavoriteEventsByScope(favorites, { kind: "tag", value: "politics", topicId: 1 }, topics, 1).map((event) => event.id), [3]);
  assert.deepEqual(filterFavoriteEventsByScope(favorites, { kind: "recent" }, topics, 1).map((event) => event.id), [2, 3, 1]);
});

test("search can use lightweight index full search text outside preview", () => {
  const event = { headline: "Index Row", preview: "首段摘要", searchText: "首段摘要 附件名 深层正文关键词", extra: {} };

  assert.equal(groupTimelineEvents([event], "era", "深层正文关键词").length, 1);
});

test("mindmapPlainText flattens a snapshot tree into searchable text", () => {
  const snapshot = {
    root: {
      data: { text: "<p>中心主题</p>" },
      children: [{ data: { text: "<p>分支甲</p>", note: "<p>细节点</p>" }, children: [] }],
    },
  };

  assert.equal(mindmapPlainText(snapshot), "中心主题 分支甲 细节点");
});

test("mindmapPlainText flattens an X6 snapshot into searchable text", () => {
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

  assert.equal(mindmapPlainText(snapshot), "中心主题 分支甲 细节点");
});

test("buildEventPreview and search can bridge mindmap bodyJson text", () => {
  const event = {
    headline: "导图检索",
    bodyJson: {
      data: { text: "<p>中心主题</p>" },
      children: [{ data: { text: "<p>分支甲</p>" }, children: [] }],
    },
    extra: {},
  };

  assert.equal(buildEventPreview(event, 40), "中心主题 分支甲");
  assert.equal(groupTimelineEvents([event], "era", "分支甲").length, 1);
});

test("eventHasDate/formatEventDate handle undated notes explicitly", () => {
  const undated = { hasDate: false, dateKey: null, dateParts: { year: null, month: null, day: null } };
  assert.equal(eventHasDate(undated), false);
  assert.equal(formatEventDate(undated), "未定时间");
  assert.equal(formatEventDisplayDate(undated), "未定时间");
});

test("resolvePropertyChips maps option ids to labels and colors, keeping unknown ids", () => {
  const chips = resolvePropertyChips({ extra: { tags: ["war", "politics", "ghost"] } }, tagsColumn);
  assert.deepEqual(chips.map((chip) => chip.value), ["war", "politics", "ghost"]);
  assert.deepEqual(chips.map((chip) => chip.label), ["战争", "政治", "ghost"]);
  assert.equal(chips[0].color, "var(--t-war)");
});

test("buildEditorDraft clones event DTO fields and seeds property values", () => {
  const event = {
    id: 99,
    dateParts: { year: 1949, month: 10, day: 1 },
    headline: "Founding Note",
    era: "Modern",
    bodyMarkdown: "",
    attachments: [{ id: 7, name: "source.pdf", filename: "source.pdf" }],
    relatedEventIds: [1],
    relatedEvents: [{ id: 1, headline: "Trade Conflict" }],
    items: [{ tag: "note", text: "Fallback body" }],
    extra: { tags: ["politics"] },
  };
  const draft = buildEditorDraft(event, [tagsColumn]);

  assert.equal(draft.dateYear, 1949);
  assert.equal(draft.bodyMarkdown, "Fallback body");
  assert.deepEqual(draft.extra.tags, ["politics"]);
  assert.deepEqual(draft.relatedEventIds, [1]);
  assert.equal(draft.tags, undefined);

  draft.attachments[0].name = "changed.pdf";
  assert.equal(draft.attachments[0].name, "changed.pdf");
  assert.equal(event.attachments[0].name, "source.pdf");
});

test("buildReadableDetailGroups removes empty read-mode support groups", () => {
  const groups = buildReadableDetailGroups({
    attachments: [{ name: "  " }, { filename: "source.pdf" }],
    relatedEvents: [{ id: 1, headline: "" }, { id: 2, headline: "Trade Conflict" }],
  });

  assert.equal(groups.tags, undefined);
  assert.deepEqual(groups.attachments.map((attachment) => attachment.filename), ["source.pdf"]);
  assert.deepEqual(groups.relatedEvents.map((event) => event.id), [2]);
});

test("normalizeTopicColumns validates, sorts, dedups options, and reserves only title/time", () => {
  const columns = normalizeTopicColumns([
    { key: "source", label: "来源", type: "text", width: 180, order: 2, visible: true },
    { key: "place", label: "地点", type: "text", width: 88, order: 1, visible: false },
    { key: "title", label: "Reserved", type: "text", width: 50, order: 0, visible: true },
    {
      key: "tags",
      label: "标签",
      type: "multiselect",
      order: 3,
      visible: true,
      options: [
        { id: "war", label: "战争", color: "x" },
        { id: "war", label: "dup" },
      ],
    },
  ]);

  assert.deepEqual(columns.map((column) => column.key), ["place", "source", "tags"]);
  const tags = columns.find((column) => column.key === "tags");
  assert.equal(tags.options.length, 1);
  assert.equal(tags.options[0].id, "war");
});

test("serializeTopicColumnsDraft preserves persisted columns during partial key/label edits", () => {
  const persisted = normalizeTopicColumns([
    { key: "place", label: "地点", type: "text", width: 92, order: 0, visible: true },
    { key: "source", label: "来源", type: "text", width: 110, order: 1, visible: false },
  ]);

  const draft = [
    { persistedKey: "place", key: "place", label: "", type: "text", width: 120, order: 0, visible: true, options: [] },
    { persistedKey: "source", key: "origin", label: "来源", type: "text", width: 118, order: 1, visible: true, options: [] },
    { persistedKey: "", key: "", label: "", type: "text", width: 96, order: 2, visible: true, options: [] },
  ];

  assert.deepEqual(serializeTopicColumnsDraft(draft, persisted), [
    { key: "place", label: "地点", type: "text", width: 120, order: 0, visible: true, options: [] },
    { key: "origin", label: "来源", type: "text", width: 118, order: 1, visible: true, options: [] },
  ]);
});

test("serializeTopicColumnsDraft falls back when a draft key is invalid or temporarily duplicated", () => {
  const persisted = normalizeTopicColumns([
    { key: "place", label: "地点", type: "text", width: 92, order: 0, visible: true },
    { key: "source", label: "来源", type: "text", width: 110, order: 1, visible: false },
  ]);

  const draft = [
    { persistedKey: "place", key: "Source", label: "地点", type: "text", width: 120, order: 0, visible: true, options: [] },
    { persistedKey: "source", key: "place", label: "来源", type: "text", width: 118, order: 1, visible: true, options: [] },
    { persistedKey: "", key: "place", label: "重复新列", type: "text", width: 96, order: 2, visible: true, options: [] },
  ];

  assert.deepEqual(serializeTopicColumnsDraft(draft, persisted), [
    { key: "place", label: "地点", type: "text", width: 120, order: 0, visible: true, options: [] },
    { key: "source", label: "来源", type: "text", width: 118, order: 1, visible: true, options: [] },
  ]);
});

test("clampTimelineColumnWidth keeps dragged widths inside the supported range", () => {
  assert.equal(clampTimelineColumnWidth(40), 72);
  assert.equal(clampTimelineColumnWidth(156), 156);
  assert.equal(clampTimelineColumnWidth(999), 220);
  assert.equal(clampTimelineColumnWidth("bad", 96), 96);
});

test("buildVisibleTimelineColumns and normalizeEventExtra honor visibility, whitelist and options", () => {
  const cols = normalizeTopicColumns([
    { key: "type", label: "类型", type: "select", width: 96, order: 0, visible: true, options: [{ id: "a", label: "A" }] },
    { key: "tags", label: "标签", type: "multiselect", width: 150, order: 1, visible: true, options: [{ id: "war", label: "战争" }] },
    { key: "place", label: "地点", type: "text", width: 92, order: 2, visible: true },
    { key: "source", label: "来源", type: "text", width: 110, order: 3, visible: false },
  ]);
  const visible = buildVisibleTimelineColumns(cols);
  // `source` is defined but hidden — its value is still kept; only the unknown
  // `drop` key is filtered out. Visibility controls display, not storage.
  const extra = normalizeEventExtra({ type: "a", tags: ["war", "ghost", "war"], place: "广州", source: "x", drop: "z" }, cols);

  assert.deepEqual(visible.map((column) => column.key), ["time", "title", "type", "tags", "place"]);
  assert.equal(buildTimelineGridTemplate(cols), "28px 96px minmax(0,1fr) 96px 150px 92px 30px");
  assert.deepEqual(extra, { type: "a", tags: ["war"], place: "广州", source: "x" });
  assert.deepEqual(normalizeEventExtra({ type: "ghost" }, cols), { type: "" });
});

test("buildSearchHighlightSegments marks query hits case-insensitively, preserving source case", () => {
  // No query → one plain segment (uniform shape for v-for); empty string → none.
  assert.deepEqual(buildSearchHighlightSegments("孔子诞生", ""), [{ text: "孔子诞生", hit: false }]);
  assert.deepEqual(buildSearchHighlightSegments("孔子诞生", "   "), [{ text: "孔子诞生", hit: false }]);
  assert.deepEqual(buildSearchHighlightSegments("", "孔子"), []);

  // Body-only match (the demonstrated 儒家 → 孔子诞生 case): the hit slice keeps
  // the source's original characters, splitting the surrounding text out.
  assert.deepEqual(buildSearchHighlightSegments("孔子创立儒家学说", "儒家"), [
    { text: "孔子创立", hit: false },
    { text: "儒家", hit: true },
    { text: "学说", hit: false },
  ]);

  // Multiple + case-insensitive: matches found regardless of case, output keeps case.
  assert.deepEqual(buildSearchHighlightSegments("Tang and TANG", "tang"), [
    { text: "Tang", hit: true },
    { text: " and ", hit: false },
    { text: "TANG", hit: true },
  ]);

  // Leading/trailing hits don't emit empty neighbor segments.
  assert.deepEqual(buildSearchHighlightSegments("孔子", "孔子"), [{ text: "孔子", hit: true }]);
});

test("timelineTimeColumnWidth widens only for BC dates carrying a real month/day", () => {
  const adFull = { dateParts: { year: 1921, month: 7, day: 23 } };
  const bcYearOnly = { dateParts: { year: -1700000, month: 1, day: 1 } }; // collapses to "公元前1700000"
  const bcFull = { dateParts: { year: -551, month: 9, day: 28 } }; // "公元前551年9月28日" ≈ 117px > 96

  // AD dates and year-only BC stay in the compact track.
  assert.equal(timelineTimeColumnWidth([adFull, bcYearOnly]), 96);
  assert.equal(timelineTimeColumnWidth([]), 96);
  assert.equal(timelineTimeColumnWidth(null), 96);

  // A single BC date with month/day widens the whole track so it stays visible.
  assert.equal(timelineTimeColumnWidth([adFull, bcFull]), 128);

  // The widened width threads through to the grid template's time slot.
  assert.equal(buildTimelineGridTemplate([], null, 128), "28px 128px minmax(0,1fr) 30px");
  assert.equal(buildVisibleTimelineColumns([], null, 128)[0].width, 128);
});

test("emptyTimelineColumnKeys hides columns with no value anywhere; built-ins and populated columns stay", () => {
  const cols = normalizeTopicColumns([
    { key: "type", label: "类型", type: "select", width: 96, order: 0, visible: true, options: [{ id: "a", label: "A" }] },
    { key: "tags", label: "标签", type: "multiselect", width: 150, order: 1, visible: true, options: [{ id: "war", label: "战争" }] },
    { key: "place", label: "地点", type: "text", width: 92, order: 2, visible: true },
    { key: "done", label: "完成", type: "checkbox", width: 80, order: 3, visible: true },
  ]);
  const evs = [
    { extra: { type: "", tags: ["war"], place: "", done: "false" } },
    { extra: { type: "", tags: [], place: "", done: "true" } },
  ];

  // type & place are empty across every event; tags & done each have one value.
  assert.deepEqual(emptyTimelineColumnKeys(cols, evs).sort(), ["place", "type"]);
  // With no events, every visible property column counts as empty.
  assert.deepEqual(emptyTimelineColumnKeys(cols, []).sort(), ["done", "place", "tags", "type"]);

  // Built-ins always survive; hidden property columns drop, populated ones stay.
  const hidden = emptyTimelineColumnKeys(cols, evs);
  assert.deepEqual(
    buildVisibleTimelineColumns(cols, hidden).map((column) => column.key),
    ["time", "title", "tags", "done"]
  );
  // The grid loses exactly the dropped columns' tracks (type 96px, place 92px).
  assert.equal(buildTimelineGridTemplate(cols, hidden), "28px 96px minmax(0,1fr) 150px 80px 30px");
  // No hiddenKeys → unchanged (back-compat with existing callers/tests).
  assert.deepEqual(
    buildVisibleTimelineColumns(cols).map((column) => column.key),
    ["time", "title", "type", "tags", "place", "done"]
  );

  // eventColumnHasValue reflects per-type rendering (option / checkbox / text).
  const col = (key) => cols.find((column) => column.key === key);
  assert.equal(eventColumnHasValue(evs[0], col("tags")), true);
  assert.equal(eventColumnHasValue(evs[1], col("tags")), false);
  assert.equal(eventColumnHasValue(evs[0], col("type")), false);
  assert.equal(eventColumnHasValue(evs[1], col("done")), true);
  assert.equal(eventColumnHasValue(evs[0], col("done")), false);
});

test("eventColumnValue and eventColumnHasValue agree on text/number emptiness (whitespace, 0)", () => {
  const cols = normalizeTopicColumns([
    { key: "place", label: "地点", type: "text", width: 92, order: 0, visible: true },
    { key: "count", label: "数量", type: "number", width: 80, order: 1, visible: true },
  ]);
  const place = cols.find((column) => column.key === "place");
  const count = cols.find((column) => column.key === "count");

  // Whitespace-only is treated as empty by BOTH the renderer and the hide-logic.
  assert.equal(eventColumnValue({ extra: { place: "   " } }, place), "—");
  assert.equal(eventColumnHasValue({ extra: { place: "   " } }, place), false);
  // Real text renders verbatim and counts as a value.
  assert.equal(eventColumnValue({ extra: { place: "广州" } }, place), "广州");
  assert.equal(eventColumnHasValue({ extra: { place: "广州" } }, place), true);
  // "0" is a real value — must stay visible (the old truthiness test dropped it).
  assert.equal(eventColumnValue({ extra: { count: "0" } }, count), "0");
  assert.equal(eventColumnHasValue({ extra: { count: "0" } }, count), true);

  // A column of only-whitespace/blank values hides; one real value keeps both shown.
  assert.deepEqual(emptyTimelineColumnKeys(cols, [{ extra: { place: "  ", count: "" } }]).sort(), ["count", "place"]);
  assert.deepEqual(emptyTimelineColumnKeys(cols, [{ extra: { place: "广州", count: "0" } }]), []);
});

test("date formatters collapse year-only precision but keep genuine days (and BC years)", () => {
  const yearOnly = { dateParts: { year: 1840, month: 1, day: 1 }, isoDate: "1840-01-01" };
  const firstOfMonth = { dateParts: { year: 1927, month: 8, day: 1 }, isoDate: "1927-08-01" };
  const fullDay = { dateParts: { year: 1921, month: 7, day: 23 }, isoDate: "1921-07-23" };
  const bcYear = { dateParts: { year: -5000, month: 1, day: 1 }, isoDate: "-5000-01-01" };

  // Timeline (compact): year-only collapses; genuine 1st-of-month and full days stay.
  assert.equal(formatEventDate(yearOnly), "1840");
  assert.equal(formatEventDate(firstOfMonth), "1927-08-01");
  assert.equal(formatEventDate(fullDay), "1921-07-23");
  assert.equal(formatEventDate(bcYear), "公元前5000");

  // Detail (CJK): same precision rule, BC prefix.
  assert.equal(formatEventDisplayDate(yearOnly), "1840年");
  assert.equal(formatEventDisplayDate(firstOfMonth), "1927年8月1日");
  assert.equal(formatEventDisplayDate(fullDay), "1921年7月23日");
  assert.equal(formatEventDisplayDate(bcYear), "公元前5000年");

  // BC dates with a real month/day use the CJK form in BOTH panes (the compact
  // timeline would otherwise show a broken-looking "-551-09-28").
  const bcFull = { dateParts: { year: -551, month: 9, day: 28 }, isoDate: "-551-09-28" };
  assert.equal(formatEventDate(bcFull), "公元前551年9月28日");
  assert.equal(formatEventDisplayDate(bcFull), "公元前551年9月28日");

  // No usable year → fall back to the precomputed displayLabel (or "").
  assert.equal(formatEventDisplayDate({ dateParts: { month: 5, day: 1 }, displayLabel: "约公元前" }), "约公元前");
  assert.equal(formatEventDisplayDate({ displayLabel: "未知" }), "未知");
});

test("groupTimelineEvents era subtitle renders BC year ranges as 公元前", () => {
  const groups = groupTimelineEvents(
    [
      { id: 1, era: "史前时期", dateParts: { year: -1700000, month: 1, day: 1 }, dateKey: -17000000101 },
      { id: 2, era: "史前时期", dateParts: { year: -700000, month: 1, day: 1 }, dateKey: -7000000101 },
    ],
    "era"
  );
  assert.equal(groups.length, 1);
  assert.equal(groups[0].subtitle, "公元前1700000–公元前700000 · 2 条");
});

test("matchesPropertyFilter matches scalar and multi-value properties", () => {
  assert.equal(matchesPropertyFilter({ extra: { tags: ["war"] } }, { key: "tags", value: "war" }), true);
  assert.equal(matchesPropertyFilter({ extra: { tags: ["politics"] } }, { key: "tags", value: "war" }), false);
  assert.equal(matchesPropertyFilter({ extra: { type: "a" } }, { key: "type", value: "a" }), true);
  assert.equal(matchesPropertyFilter({ extra: {} }, { key: "", value: "" }), true);
});

test("buildPropertyRows reports option usage counts across events", () => {
  const rows = buildPropertyRows([tagsColumn], events);
  const tags = rows.find((row) => row.key === "tags");
  assert.equal(tags.isOption, true);
  assert.equal(tags.filledCount, 2);
  assert.equal(tags.totalCount, 3);
  assert.equal(tags.options.find((option) => option.value === "war").count, 1);
  assert.equal(tags.options.find((option) => option.value === "politics").count, 1);
  assert.equal(tags.options.find((option) => option.value === "reform").count, 1);
});

test("buildPropertyRows reports free-value fill counts and samples", () => {
  const rows = buildPropertyRows(
    [
      { key: "place", label: "地点", type: "text", visible: true },
      { key: "done", label: "完成", type: "checkbox", visible: true },
    ],
    [
      { extra: { place: "广州", done: "true" } },
      { extra: { place: "上海", done: "false" } },
      { extra: { place: " ", done: "" } },
    ]
  );
  const place = rows.find((row) => row.key === "place");
  const done = rows.find((row) => row.key === "done");
  assert.equal(place.filledCount, 2);
  assert.deepEqual(place.sampleValues, ["广州", "上海"]);
  assert.equal(done.filledCount, 2);
  assert.equal(done.checkedCount, 1);
});

test("buildPropertyUsage keeps type changes locked when only orphan option ids remain", () => {
  const columns = [
    {
      key: "tags",
      label: "标签",
      type: "multiselect",
      visible: true,
      options: [{ id: "war", label: "战争", color: "var(--t-war)" }],
    },
  ];
  const usage = buildPropertyUsage(columns, [
    { extra: { tags: ["ghost"] } },
    { extra: { tags: [] } },
  ]);

  assert.equal(usage.rows.get("tags").filledCount, 1);
  assert.equal(usage.rawValueCounts.get("tags"), 1);
  assert.equal(usage.orphanOptionIds.get("tags").has("ghost"), true);
  assert.equal(canChangePropertyType(usage, "tags"), false);
  assert.equal(canChangePropertyType(usage, "unknown"), true);
});

test("editablePropertyTypeChoices hides email and phone from normal creation flows", () => {
  const values = editablePropertyTypeChoices().map((item) => item.value);
  assert.deepEqual(values, ["text", "number", "date", "checkbox", "url", "select", "multiselect"]);
});

test("editablePropertyTypeChoices keeps a legacy current type representable", () => {
  const choices = editablePropertyTypeChoices("email");
  assert.equal(choices.at(-1).value, "email");
  assert.equal(choices.at(-1).legacy, true);
  assert.equal(choices.at(-1).label, "邮箱（旧）");
});

test("buildPropertyKey and buildOptionId generate stable ASCII fallbacks", () => {
  assert.equal(buildPropertyKey("属性", ["property"]), "property_2");
  assert.equal(buildPropertyKey("Source Name", ["source_name"]), "source_name_2");
  assert.equal(buildOptionId("颜色标签", ["option"]), "option_2");
  assert.equal(buildOptionId("Treaty Option", ["treaty_option"]), "treaty_option_2");
});

test("normalizeEventExtra coerces checkbox values to canonical true/false", () => {
  const cols = [{ key: "done", label: "完成", type: "checkbox" }];
  assert.deepEqual(normalizeEventExtra({ done: "true" }, cols), { done: "true" });
  assert.deepEqual(normalizeEventExtra({ done: "1" }, cols), { done: "true" });
  assert.deepEqual(normalizeEventExtra({ done: true }, cols), { done: "true" });
  assert.deepEqual(normalizeEventExtra({ done: "false" }, cols), { done: "false" });
  assert.deepEqual(normalizeEventExtra({ done: "" }, cols), { done: "false" });
});

test("isCheckboxChecked reads canonical and loose truthy strings", () => {
  assert.equal(isCheckboxChecked("true"), true);
  assert.equal(isCheckboxChecked("YES"), true);
  assert.equal(isCheckboxChecked(true), true);
  assert.equal(isCheckboxChecked("false"), false);
  assert.equal(isCheckboxChecked(""), false);
  assert.equal(isCheckboxChecked(undefined), false);
});

test("propertyHref builds safe hrefs and neutralizes script schemes", () => {
  assert.equal(propertyHref("url", "example.com"), "https://example.com");
  assert.equal(propertyHref("url", "http://a.test"), "http://a.test");
  assert.equal(propertyHref("url", "javascript:alert(1)"), "https://javascript:alert(1)");
  assert.equal(propertyHref("email", "a@b.com"), "mailto:a@b.com");
  assert.equal(propertyHref("phone", "+1 (415) 555-0172"), "tel:+14155550172");
  assert.equal(propertyHref("url", ""), "");
  assert.equal(propertyHref("text", "x"), "");
});

test("groupTimelineEvents reverses era group order for a descending time sort", () => {
  const events = [
    { id: 1, dateKey: 18000101, dateParts: { year: 1800, month: 1, day: 1 }, era: "清代" },
    { id: 2, dateKey: 19000101, dateParts: { year: 1900, month: 1, day: 1 }, era: "民国" },
  ];
  const asc = groupTimelineEvents(events, "era", "", [], { field: "time", dir: 1 });
  const desc = groupTimelineEvents(events, "era", "", [], { field: "time", dir: -1 });
  assert.deepEqual(asc.map((group) => group.title), ["清代", "民国"]);
  assert.deepEqual(desc.map((group) => group.title), ["民国", "清代"]);
  assert.deepEqual(desc[0].items.map((event) => event.id), [2]);
});

test("groupTimelineEvents by year buckets undated notes into 未定时间, not a null-year group", () => {
  const events = [
    { id: 1, dateKey: 19000101, dateParts: { year: 1900, month: 1, day: 1 } },
    { id: 2, hasDate: false },
    { id: 3, dateKey: 18000101, dateParts: { year: 1800, month: 1, day: 1 } },
  ];
  const groups = groupTimelineEvents(events, "year", "", [], { field: "time", dir: 1 });
  const titles = groups.map((group) => group.title);
  assert.ok(titles.includes("1800") && titles.includes("1900") && titles.includes("未定时间"));
  assert.ok(!titles.some((title) => title.includes("null") || title === "")); // no fabricated null-year bucket
  assert.equal(groups[groups.length - 1].title, "未定时间"); // undated sinks last
});
