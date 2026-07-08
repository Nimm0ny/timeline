import test from "node:test";
import assert from "node:assert/strict";

import {
  buildBookshelfTree,
  buildPropertyUsage,
  buildOptionId,
  buildEditorDraft,
  buildNotePreview,
  buildFavoriteFacetRows,
  buildGlobalFavoriteNotes,
  buildPropertyKey,
  buildPropertyRows,
  buildRecentFavoriteNotes,
  canChangePropertyType,
  classifyNoteDateInput,
  editablePropertyTypeChoices,
  buildReadableDetailGroups,
  buildSearchHighlightSegments,
  buildTimelineGridTemplate,
  buildVisibleTimelineColumns,
  clampTimelineColumnWidth,
  emptyTimelineColumnKeys,
  noteColumnHasValue,
  noteColumnValue,
  noteHasDate,
  formatNoteDate,
  formatNoteDisplayDate,
  filterFavoriteNotesByScope,
  groupNotes,
  isCheckboxChecked,
  mindmapPlainText,
  matchesPropertyFilter,
  normalizeNoteExtra,
  normalizeTopicBookshelf,
  normalizeTopicColumns,
  propertyHref,
  resolveCreateTopicRequest,
  resolveTopicCreateShelfName,
  resolvePropertyChips,
  serializeTopicColumnsDraft,
  mergeTopicNotePage,
  planTopicPageFetch,
  shouldAutoLoadMoreForFilteredNotes,
  shouldRequestMoreOnScroll,
  timelineTimeColumnWidth,
  findBookshelfByName,
  sortBookshelfTree,
  SIDEBAR_SORT_MODES,
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

test("groupNotes sorts events and filters by search query", () => {
  const groups = groupNotes(events, "year", "trade");

  assert.equal(groups.length, 1);
  assert.equal(groups[0].key, "1840");
  assert.deepEqual(groups[0].items.map((event) => event.id), [1]);
});

test("groupNotes keeps chronological order within grouped years", () => {
  const groups = groupNotes(events, "year", "");

  assert.deepEqual(groups.map((group) => group.key), ["1840", "1911"]);
  assert.deepEqual(groups[0].items.map((event) => event.id), [3, 1]);
});

test("groupNotes can search by resolved option label", () => {
  const groups = groupNotes(events, "year", "政治", [tagsColumn]);
  assert.deepEqual(groups.flatMap((group) => group.items.map((event) => event.id)), [2]);
});

test("buildNotePreview strips markdown and truncates to the requested length", () => {
  const preview = buildNotePreview(
    {
      bodyMarkdown: "## Heading\nThis **timeline** entry has enough text for preview trimming.",
      items: [],
    },
    22
  );

  assert.equal(preview, "Heading This timeline...");
});

test("buildNotePreview uses a stable placeholder for markdown images", () => {
  const preview = buildNotePreview(
    {
      bodyMarkdown: "正文前 ![现场照片](/images/site.png) 正文后 [来源](https://example.com)",
      items: [],
    },
    80
  );

  assert.equal(preview, "正文前 [图片] 正文后 来源");
});

test("buildNotePreview and search can use lightweight index preview text", () => {
  const event = { headline: "Index Row", preview: "轻量索引预览文本", extra: {} };

  assert.equal(buildNotePreview(event, 20), "轻量索引预览文本");
  assert.equal(groupNotes([event], "era", "索引").length, 1);
});

test("buildGlobalFavoriteNotes returns live favorites across topics in timeline order", () => {
  const rows = buildGlobalFavoriteNotes([
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

test("buildRecentFavoriteNotes prefers favoriteAt and caps to five", () => {
  const rows = buildRecentFavoriteNotes([
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

test("filterFavoriteNotesByScope supports current notebook, recent, topic, type, and tag scopes", () => {
  const topics = [
    { id: 1, title: "党史", columns: [{ key: "type", label: "类型", type: "select", options: [{ id: "war", label: "战争" }] }, tagsColumn] },
    { id: 2, title: "近代史", columns: [{ key: "type", label: "类型", type: "select", options: [{ id: "reform", label: "改革" }] }, tagsColumn] },
  ];
  const favorites = [
    { id: 1, topicId: 1, dateKey: 18400101, favoriteAt: "2026-06-10T00:00:00Z", extra: { type: "war", tags: ["war"] } },
    { id: 2, topicId: 2, dateKey: 19110101, favoriteAt: "2026-06-30T00:00:00Z", extra: { type: "reform", tags: ["politics"] } },
    { id: 3, topicId: 1, dateKey: 18400201, favoriteAt: "2026-06-29T00:00:00Z", extra: { type: "war", tags: ["politics"] } },
  ];

  assert.deepEqual(filterFavoriteNotesByScope(favorites, { kind: "current-topic" }, topics, 1).map((event) => event.id), [1, 3]);
  assert.deepEqual(filterFavoriteNotesByScope(favorites, { kind: "topic", topicId: 2 }, topics, 1).map((event) => event.id), [2]);
  assert.deepEqual(filterFavoriteNotesByScope(favorites, { kind: "type", value: "war", topicId: 1 }, topics, 1).map((event) => event.id), [1, 3]);
  assert.deepEqual(filterFavoriteNotesByScope(favorites, { kind: "tag", value: "politics", topicId: 1 }, topics, 1).map((event) => event.id), [3]);
  assert.deepEqual(filterFavoriteNotesByScope(favorites, { kind: "recent" }, topics, 1).map((event) => event.id), [2, 3, 1]);
});

test("search can use lightweight index full search text outside preview", () => {
  const event = { headline: "Index Row", preview: "首段摘要", searchText: "首段摘要 附件名 深层正文关键词", extra: {} };

  assert.equal(groupNotes([event], "era", "深层正文关键词").length, 1);
});

test("matchesNoteSearch prefers searchText before rebuilding runtime haystacks", () => {
  const event = {
    headline: "Search Row",
    searchText: "索引关键字",
    bodyMarkdown: "这里没有那个词",
    extra: { place: "上海" },
  };

  assert.equal(groupNotes([event], "era", "索引关键字").length, 1);
  assert.equal(groupNotes([event], "era", "这里没有那个词").length, 0);
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

test("buildNotePreview and search can bridge mindmap bodyJson text", () => {
  const event = {
    headline: "导图检索",
    bodyJson: {
      data: { text: "<p>中心主题</p>" },
      children: [{ data: { text: "<p>分支甲</p>" }, children: [] }],
    },
    extra: {},
  };

  assert.equal(buildNotePreview(event, 40), "中心主题 分支甲");
  assert.equal(groupNotes([event], "era", "分支甲").length, 1);
});

test("noteHasDate/formatNoteDate handle undated notes explicitly", () => {
  const undated = { hasDate: false, dateKey: null, dateParts: { year: null, month: null, day: null } };
  assert.equal(noteHasDate(undated), false);
  assert.equal(formatNoteDate(undated), "");
  assert.equal(formatNoteDisplayDate(undated), "未定时间");
});

test("noteColumnValue falls back to era before using undated display text for title", () => {
  const row = { headline: "", era: "第一章", displayLabel: "未定时间" };
  assert.equal(noteColumnValue(row, { key: "title" }), "第一章");
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

test("buildVisibleTimelineColumns and normalizeNoteExtra honor visibility, whitelist and options", () => {
  const cols = normalizeTopicColumns([
    { key: "type", label: "类型", type: "select", width: 96, order: 0, visible: true, options: [{ id: "a", label: "A" }] },
    { key: "tags", label: "标签", type: "multiselect", width: 150, order: 1, visible: true, options: [{ id: "war", label: "战争" }] },
    { key: "place", label: "地点", type: "text", width: 92, order: 2, visible: true },
    { key: "source", label: "来源", type: "text", width: 110, order: 3, visible: false },
  ]);
  const visible = buildVisibleTimelineColumns(cols);
  // `source` is defined but hidden — its value is still kept; only the unknown
  // `drop` key is filtered out. Visibility controls display, not storage.
  const extra = normalizeNoteExtra({ type: "a", tags: ["war", "ghost", "war"], place: "广州", source: "x", drop: "z" }, cols);

  assert.deepEqual(visible.map((column) => column.key), ["time", "title", "type", "tags", "place"]);
  assert.equal(buildTimelineGridTemplate(cols), "28px 96px minmax(0,1fr) 96px 150px 92px 30px");
  assert.deepEqual(extra, { type: "a", tags: ["war"], place: "广州", source: "x" });
  assert.deepEqual(normalizeNoteExtra({ type: "ghost" }, cols), { type: "" });
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

  // noteColumnHasValue reflects per-type rendering (option / checkbox / text).
  const col = (key) => cols.find((column) => column.key === key);
  assert.equal(noteColumnHasValue(evs[0], col("tags")), true);
  assert.equal(noteColumnHasValue(evs[1], col("tags")), false);
  assert.equal(noteColumnHasValue(evs[0], col("type")), false);
  assert.equal(noteColumnHasValue(evs[1], col("done")), true);
  assert.equal(noteColumnHasValue(evs[0], col("done")), false);
});

test("noteColumnValue and noteColumnHasValue agree on text/number emptiness (whitespace, 0)", () => {
  const cols = normalizeTopicColumns([
    { key: "place", label: "地点", type: "text", width: 92, order: 0, visible: true },
    { key: "count", label: "数量", type: "number", width: 80, order: 1, visible: true },
  ]);
  const place = cols.find((column) => column.key === "place");
  const count = cols.find((column) => column.key === "count");

  // Whitespace-only is treated as empty by BOTH the renderer and the hide-logic.
  assert.equal(noteColumnValue({ extra: { place: "   " } }, place), "—");
  assert.equal(noteColumnHasValue({ extra: { place: "   " } }, place), false);
  // Real text renders verbatim and counts as a value.
  assert.equal(noteColumnValue({ extra: { place: "广州" } }, place), "广州");
  assert.equal(noteColumnHasValue({ extra: { place: "广州" } }, place), true);
  // "0" is a real value — must stay visible (the old truthiness test dropped it).
  assert.equal(noteColumnValue({ extra: { count: "0" } }, count), "0");
  assert.equal(noteColumnHasValue({ extra: { count: "0" } }, count), true);

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
  assert.equal(formatNoteDate(yearOnly), "1840");
  assert.equal(formatNoteDate(firstOfMonth), "1927-08-01");
  assert.equal(formatNoteDate(fullDay), "1921-07-23");
  assert.equal(formatNoteDate(bcYear), "公元前5000");

  // Detail (CJK): same precision rule, BC prefix.
  assert.equal(formatNoteDisplayDate(yearOnly), "1840年");
  assert.equal(formatNoteDisplayDate(firstOfMonth), "1927年8月1日");
  assert.equal(formatNoteDisplayDate(fullDay), "1921年7月23日");
  assert.equal(formatNoteDisplayDate(bcYear), "公元前5000年");

  // BC dates with a real month/day use the CJK form in BOTH panes (the compact
  // timeline would otherwise show a broken-looking "-551-09-28").
  const bcFull = { dateParts: { year: -551, month: 9, day: 28 }, isoDate: "-551-09-28" };
  assert.equal(formatNoteDate(bcFull), "公元前551年9月28日");
  assert.equal(formatNoteDisplayDate(bcFull), "公元前551年9月28日");

  // No usable year → fall back to the precomputed displayLabel (or "").
  assert.equal(formatNoteDisplayDate({ dateParts: { month: 5, day: 1 }, displayLabel: "约公元前" }), "约公元前");
  assert.equal(formatNoteDisplayDate({ displayLabel: "未知" }), "未知");
});

test("groupNotes era subtitle renders BC year ranges as 公元前", () => {
  const groups = groupNotes(
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

test("normalizeNoteExtra coerces checkbox values to canonical true/false", () => {
  const cols = [{ key: "done", label: "完成", type: "checkbox" }];
  assert.deepEqual(normalizeNoteExtra({ done: "true" }, cols), { done: "true" });
  assert.deepEqual(normalizeNoteExtra({ done: "1" }, cols), { done: "true" });
  assert.deepEqual(normalizeNoteExtra({ done: true }, cols), { done: "true" });
  assert.deepEqual(normalizeNoteExtra({ done: "false" }, cols), { done: "false" });
  assert.deepEqual(normalizeNoteExtra({ done: "" }, cols), { done: "false" });
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

test("groupNotes reverses era group order for a descending time sort", () => {
  const events = [
    { id: 1, dateKey: 18000101, dateParts: { year: 1800, month: 1, day: 1 }, era: "清代" },
    { id: 2, dateKey: 19000101, dateParts: { year: 1900, month: 1, day: 1 }, era: "民国" },
  ];
  const asc = groupNotes(events, "era", "", [], { field: "time", dir: 1 });
  const desc = groupNotes(events, "era", "", [], { field: "time", dir: -1 });
  assert.deepEqual(asc.map((group) => group.title), ["清代", "民国"]);
  assert.deepEqual(desc.map((group) => group.title), ["民国", "清代"]);
  assert.deepEqual(desc[0].items.map((event) => event.id), [2]);
});

test("groupNotes by year buckets undated notes into 未定时间, not a null-year group", () => {
  const events = [
    { id: 1, dateKey: 19000101, dateParts: { year: 1900, month: 1, day: 1 } },
    { id: 2, hasDate: false },
    { id: 3, dateKey: 18000101, dateParts: { year: 1800, month: 1, day: 1 } },
  ];
  const groups = groupNotes(events, "year", "", [], { field: "time", dir: 1 });
  const titles = groups.map((group) => group.title);
  assert.ok(titles.includes("1800") && titles.includes("1900") && titles.includes("未定时间"));
  assert.ok(!titles.some((title) => title.includes("null") || title === "")); // no fabricated null-year bucket
  assert.equal(groups[groups.length - 1].title, "未定时间"); // undated sinks last
});

test("normalizeTopicBookshelf falls back to system shelf semantics", () => {
  assert.deepEqual(normalizeTopicBookshelf({}), { id: null, name: "default", title: "编年" });
  assert.deepEqual(normalizeTopicBookshelf({ bookshelfId: 7, bookshelfName: "qstheory", bookshelfTitle: "" }), {
    id: 7,
    name: "qstheory",
    title: "求是",
  });
});

test("buildBookshelfTree keeps empty shelves and groups topic eras chronologically", () => {
  const topics = [
    { id: 1, title: "党史", eventCount: 2, bookshelfId: 10, bookshelfName: "default", bookshelfTitle: "编年" },
    { id: 2, title: "求是网-理论", eventCount: 1, bookshelfId: 11, bookshelfName: "qstheory", bookshelfTitle: "求是" },
  ];
  const bookshelves = [
    { id: 10, name: "default", title: "编年" },
    { id: 11, name: "qstheory", title: "求是" },
    { id: 12, name: "archive", title: "档案" },
  ];
  const allEvents = [
    { id: 101, topicId: 1, dateKey: 18400601, era: "近代中国" },
    { id: 102, topicId: 1, dateKey: 19150504, era: "新文化运动" },
    { id: 201, topicId: 2, dateKey: 20260101, era: "专题" },
  ];

  const tree = buildBookshelfTree(topics, bookshelves, allEvents);

  assert.deepEqual(tree.map((shelf) => [shelf.name, shelf.topicCount]), [
    ["default", 1],
    ["qstheory", 1],
    ["archive", 0],
  ]);
  assert.deepEqual(tree[0].topics[0].eras.map((era) => era.era), ["近代中国", "新文化运动"]);
  assert.equal(tree[2].topics.length, 0);
});

test("resolveTopicCreateShelfName ignores pointer-event-like inputs and falls back deterministically", () => {
  const tree = [{ name: "default" }, { name: "qstheory" }];

  assert.equal(resolveTopicCreateShelfName("qstheory", "default", tree), "qstheory");
  assert.equal(resolveTopicCreateShelfName({ type: "click" }, "default", tree), "default");
  assert.equal(resolveTopicCreateShelfName({ type: "click" }, "", tree), "default");
  assert.equal(resolveTopicCreateShelfName(null, "", []), "");
});

test("findBookshelfByName resolves the shelf-scoped create target by stable name", () => {
  const shelves = [
    { id: 10, name: "default", title: "编年" },
    { id: 11, name: "qstheory", title: "求是" },
  ];
  const synthesized = [{ id: 12, name: "archive", title: "档案" }];

  assert.equal(findBookshelfByName(shelves, " qstheory ").id, 11);
  assert.equal(findBookshelfByName(shelves, "missing"), null);
  assert.equal(findBookshelfByName(shelves, "archive", synthesized).id, 12);
});

test("resolveCreateTopicRequest preserves shelf-scoped notebook creation across emitted input shapes", () => {
  const bookshelves = [{ id: 10, name: "default", title: "编年" }];
  const synthesizedTree = [{ id: 12, name: "archive", title: "档案" }];

  assert.deepEqual(
    resolveCreateTopicRequest({ name: "新笔记", bookshelfName: "archive" }, "default", bookshelves, synthesizedTree),
    { topicName: "新笔记", bookshelfName: "archive", bookshelfId: 12 }
  );
  assert.deepEqual(
    resolveCreateTopicRequest("全局新增", "default", bookshelves, synthesizedTree),
    { topicName: "全局新增", bookshelfName: "default", bookshelfId: 10 }
  );
  assert.deepEqual(
    resolveCreateTopicRequest({ name: "点击事件", bookshelfName: { type: "click" } }, "", [], synthesizedTree),
    { topicName: "点击事件", bookshelfName: "archive", bookshelfId: 12 }
  );
});

test("mergeTopicNotePage replaces on load and de-dupes by id across appended pages", () => {
  const page1 = [{ id: 1, topicId: 7 }, { id: 2, topicId: 7 }];
  // Non-append replaces whatever was there.
  assert.deepEqual(mergeTopicNotePage([{ id: 9 }], page1).map((e) => e.id), [1, 2]);
  // Append de-dupes the overlapping boundary row (id 2) and keeps order, no drop.
  const page2 = [{ id: 2, topicId: 7 }, { id: 3, topicId: 7 }, { id: 4, topicId: 7 }];
  const merged = mergeTopicNotePage(page1, page2, { append: true });
  assert.deepEqual(merged.map((e) => e.id), [1, 2, 3, 4]);
  // A fully-overlapping page adds nothing (idempotent).
  assert.deepEqual(mergeTopicNotePage(merged, page1, { append: true }).map((e) => e.id), [1, 2, 3, 4]);
});

test("planTopicPageFetch decides fetch + threads the cursor across initial/force/append", () => {
  assert.deepEqual(planTopicPageFetch({ loaded: false }, {}), { shouldFetch: true, requestCursor: null });
  assert.deepEqual(planTopicPageFetch({ loaded: true }, {}), { shouldFetch: false, requestCursor: null });
  assert.deepEqual(planTopicPageFetch({ loaded: true }, { force: true }), { shouldFetch: true, requestCursor: null });
  assert.deepEqual(
    planTopicPageFetch({ loaded: true, hasMore: true, nextCursor: "18500101:42" }, { append: true }),
    { shouldFetch: true, requestCursor: "18500101:42" }
  );
  // No more pages -> don't fetch.
  assert.deepEqual(
    planTopicPageFetch({ loaded: true, hasMore: false, nextCursor: "x" }, { append: true }),
    { shouldFetch: false, requestCursor: null }
  );
  // hasMore but no cursor -> skip (never silently refetch page 1).
  assert.deepEqual(
    planTopicPageFetch({ loaded: true, hasMore: true, nextCursor: null }, { append: true }),
    { shouldFetch: false, requestCursor: null }
  );
  // Explicit cursor wins.
  assert.deepEqual(
    planTopicPageFetch({ loaded: true, hasMore: true, nextCursor: "a" }, { append: true, cursor: "b" }),
    { shouldFetch: true, requestCursor: "b" }
  );
});

test("shouldRequestMoreOnScroll fires only near the bottom and honors the guards", () => {
  const near = { scrollHeight: 1000, scrollTop: 700, clientHeight: 100, hasMore: true }; // remaining 200 <= 320
  assert.equal(shouldRequestMoreOnScroll(near), true);
  assert.equal(shouldRequestMoreOnScroll({ scrollHeight: 1000, scrollTop: 100, clientHeight: 100, hasMore: true }), false);
  // Exactly at the threshold still fires.
  assert.equal(shouldRequestMoreOnScroll({ scrollHeight: 1000, scrollTop: 580, clientHeight: 100, hasMore: true }), true);
  assert.equal(shouldRequestMoreOnScroll({ ...near, hasMore: false }), false);
  assert.equal(shouldRequestMoreOnScroll({ ...near, loadingMore: true }), false);
  assert.equal(shouldRequestMoreOnScroll({ ...near, loading: true }), false);
  assert.equal(shouldRequestMoreOnScroll({ ...near, error: true }), false);
  assert.equal(shouldRequestMoreOnScroll({ ...near, globalFavoritesMode: true }), false);
});

test("shouldAutoLoadMoreForFilteredNotes only keeps paging while a filtered topic page is empty", () => {
  assert.equal(
    shouldAutoLoadMoreForFilteredNotes({
      activeTopicId: 1,
      globalFavoritesMode: false,
      hasMore: true,
      eventsLoading: false,
      loadingMore: false,
      visibleCount: 0,
    }),
    true
  );
  assert.equal(
    shouldAutoLoadMoreForFilteredNotes({
      activeTopicId: 1,
      globalFavoritesMode: false,
      hasMore: true,
      eventsLoading: false,
      loadingMore: false,
      visibleCount: 3,
    }),
    false
  );
  assert.equal(
    shouldAutoLoadMoreForFilteredNotes({
      activeTopicId: 1,
      globalFavoritesMode: true,
      hasMore: true,
      eventsLoading: false,
      loadingMore: false,
      visibleCount: 0,
    }),
    false
  );
});

const sidebarSortTree = () => [
  {
    name: "b",
    title: "Beta",
    eventCount: 5,
    updatedAt: "2026-06-01T00:00:00Z",
    topics: [
      { topic: { id: 1, title: "Cat", eventCount: 2, updatedAt: "2026-02-01T00:00:00Z" }, eras: [{ era: "e", count: 2 }] },
      { topic: { id: 2, title: "Dog", eventCount: 9, updatedAt: "2026-03-01T00:00:00Z" }, eras: [] },
    ],
  },
  {
    name: "a",
    title: "Alpha",
    eventCount: 8,
    updatedAt: "2026-05-01T00:00:00Z",
    topics: [{ topic: { id: 3, title: "Ant", eventCount: 1, updatedAt: "2026-04-01T00:00:00Z" }, eras: [] }],
  },
];

const shelfTitles = (tree) => tree.map((shelf) => shelf.title);
const topicTitles = (shelf) => shelf.topics.map((entry) => entry.topic.title);

test("sortBookshelfTree default keeps the backend order untouched", () => {
  const tree = sidebarSortTree();
  const result = sortBookshelfTree(tree, "default");
  assert.equal(result, tree); // same reference, no reordering
  assert.deepEqual(shelfTitles(result), ["Beta", "Alpha"]);
  assert.deepEqual(SIDEBAR_SORT_MODES, ["default", "name", "count", "updated"]);
});

test("sortBookshelfTree name sorts shelves and notebooks by title asc", () => {
  const result = sortBookshelfTree(sidebarSortTree(), "name");
  assert.deepEqual(shelfTitles(result), ["Alpha", "Beta"]);
  const beta = result.find((shelf) => shelf.title === "Beta");
  assert.deepEqual(topicTitles(beta), ["Cat", "Dog"]);
});

test("sortBookshelfTree count sorts by note count desc", () => {
  const result = sortBookshelfTree(sidebarSortTree(), "count");
  assert.deepEqual(shelfTitles(result), ["Alpha", "Beta"]); // 8 before 5
  const beta = result.find((shelf) => shelf.title === "Beta");
  assert.deepEqual(topicTitles(beta), ["Dog", "Cat"]); // 9 before 2
});

test("sortBookshelfTree updated sorts by updatedAt desc", () => {
  const result = sortBookshelfTree(sidebarSortTree(), "updated");
  assert.deepEqual(shelfTitles(result), ["Beta", "Alpha"]); // Jun before May
  const beta = result.find((shelf) => shelf.title === "Beta");
  assert.deepEqual(topicTitles(beta), ["Dog", "Cat"]); // Mar before Feb
});

test("sortBookshelfTree leaves the source tree and era lists untouched", () => {
  const tree = sidebarSortTree();
  const shelfSnapshot = shelfTitles(tree);
  const topicSnapshot = topicTitles(tree[0]);
  const result = sortBookshelfTree(tree, "count");
  assert.deepEqual(shelfTitles(tree), shelfSnapshot);
  assert.deepEqual(topicTitles(tree[0]), topicSnapshot);
  const beta = result.find((shelf) => shelf.title === "Beta");
  assert.deepEqual(beta.topics.find((entry) => entry.topic.title === "Cat").eras, [{ era: "e", count: 2 }]);
});

test("classifyNoteDateInput: full valid triple is dated and carries the fields", () => {
  assert.deepEqual(classifyNoteDateInput("2026", "6", "30"), {
    status: "dated",
    dateFields: { dateYear: 2026, dateMonth: 6, dateDay: 30 },
  });
  // Numbers, negatives (BCE), and padded strings all parse the same way.
  assert.deepEqual(classifyNoteDateInput(-221, 1, 1), {
    status: "dated",
    dateFields: { dateYear: -221, dateMonth: 1, dateDay: 1 },
  });
});

test("classifyNoteDateInput: all-blank is undated with no date fields", () => {
  for (const blank of [["", "", ""], [null, undefined, "  "], [undefined, undefined, undefined]]) {
    assert.deepEqual(classifyNoteDateInput(...blank), { status: "undated", dateFields: {} });
  }
});

test("classifyNoteDateInput: a partially filled date is rejected", () => {
  // Any non-empty part without a full valid triple → partial (the editor blocks it,
  // and no date keys leak into the payload).
  assert.deepEqual(classifyNoteDateInput("2026", "", ""), { status: "partial", dateFields: {} });
  assert.deepEqual(classifyNoteDateInput("2026", "6", ""), { status: "partial", dateFields: {} });
  assert.deepEqual(classifyNoteDateInput("2026", "abc", "30"), { status: "partial", dateFields: {} });
});

test("mindmapPlainText extracts canvas card text so an in-session upsert keeps search/preview", () => {
  const canvas = {
    _fmt: "x6-canvas-v1",
    cells: [
      { id: "n1", shape: "rect", data: { text: "预算 100 万" }, attrs: { label: { text: "预算 100 万" } } },
      { id: "n2", shape: "rect", data: { text: "招聘计划" }, attrs: { label: { text: "招聘计划" } } },
      { id: "e1", shape: "edge", data: { _isCanvasEdge: true } },
    ],
  };
  assert.equal(mindmapPlainText(canvas), "预算 100 万 招聘计划");
  // A mindmap tree still resolves through the legacy path.
  assert.equal(mindmapPlainText({ data: { text: "根" }, children: [{ data: { text: "枝" }, children: [] }] }), "根 枝");
});
