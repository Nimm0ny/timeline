import { computed, nextTick, ref } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";

export const FEED_LINEAR_DESKTOP_ROW_HEIGHT = 33;
export const FEED_LINEAR_MOBILE_ROW_HEIGHT = 44;
export const FEED_GROUP_DESKTOP_HEIGHT = 40;
export const FEED_GROUP_MOBILE_HEIGHT = 44;
export const FEED_LINEAR_DESKTOP_OVERSCAN = 12;
export const FEED_LINEAR_MOBILE_OVERSCAN = 8;
export const FEED_GALLERY_DESKTOP_OVERSCAN = 6;
export const FEED_GALLERY_MOBILE_OVERSCAN = 4;
export const FEED_BOARD_COLUMN_OVERSCAN = 4;
export const FEED_LOAD_MORE_REMAINING = 12;

function clampCount(count) {
  const next = Number.parseInt(count, 10);
  return Number.isFinite(next) && next > 0 ? next : 0;
}

export function flattenGroupedRows(groups = []) {
  return (Array.isArray(groups) ? groups : []).flatMap((group) => [
    {
      kind: "group-header",
      key: `group:${group.key}`,
      groupKey: group.key,
      title: group.title,
      subtitle: group.subtitle,
    },
    ...((group.items || []).map((event) => ({
      kind: "event-row",
      key: `event:${event.id}`,
      groupKey: group.key,
      event,
    })) || []),
  ]);
}

export function chunkGalleryRows(items = [], perRow = 1) {
  const width = Math.max(1, Number.parseInt(perRow, 10) || 1);
  const rows = [];
  for (let index = 0; index < items.length; index += width) {
    rows.push({
      kind: "gallery-row",
      key: `gallery:${index}`,
      items: items.slice(index, index + width),
    });
  }
  return rows;
}

export function shouldRequestMoreForVirtualItems({
  count = 0,
  lastVisibleIndex = -1,
  hasMore = false,
  loading = false,
  loadingMore = false,
  globalFavoritesMode = false,
  error = false,
  threshold = FEED_LOAD_MORE_REMAINING,
} = {}) {
  const total = clampCount(count);
  if (!total || !hasMore || loading || loadingMore || globalFavoritesMode || error) return false;
  return Number(lastVisibleIndex) >= total - 1 - Math.max(1, Number.parseInt(threshold, 10) || FEED_LOAD_MORE_REMAINING);
}

export function sliceVirtualWindow({
  count = 0,
  scrollTop = 0,
  viewportHeight = 0,
  estimateSize = 0,
  overscan = FEED_BOARD_COLUMN_OVERSCAN,
} = {}) {
  const total = clampCount(count);
  const size = Math.max(1, Number(estimateSize) || 1);
  if (!total) {
    return { startIndex: 0, endIndex: -1, topSpacerPx: 0, bottomSpacerPx: 0, totalSize: 0 };
  }
  const safeTop = Math.max(0, Number(scrollTop) || 0);
  const safeHeight = Math.max(size, Number(viewportHeight) || size);
  const extra = Math.max(0, Number.parseInt(overscan, 10) || 0);
  const startIndex = Math.max(0, Math.floor(safeTop / size) - extra);
  const endIndex = Math.min(total - 1, Math.ceil((safeTop + safeHeight) / size) + extra);
  const topSpacerPx = startIndex * size;
  const totalSize = total * size;
  const bottomSpacerPx = Math.max(0, totalSize - ((endIndex + 1) * size));
  return { startIndex, endIndex, topSpacerPx, bottomSpacerPx, totalSize };
}

export function useFeedVirtualRows(options) {
  const rememberedScrollTop = ref(0);
  const virtualizerOptions = computed(() => {
    const items = options.items?.value || [];
    const overscan = options.overscan?.value ?? options.overscan ?? FEED_LINEAR_DESKTOP_OVERSCAN;
    return {
      count: items.length,
      getScrollElement: () => options.scrollElement?.value || null,
      estimateSize: (index) => options.estimateSize(index, items[index]),
      overscan,
      getItemKey: (index) => {
        const item = items[index];
        if (options.getItemKey) return options.getItemKey(item, index);
        return item?.key ?? index;
      },
    };
  });

  const virtualizer = useVirtualizer(virtualizerOptions);

  const virtualItems = computed(() => virtualizer.value.getVirtualItems());
  const totalSize = computed(() => virtualizer.value.getTotalSize());
  const topSpacerPx = computed(() => virtualItems.value[0]?.start || 0);
  const bottomSpacerPx = computed(() => {
    const last = virtualItems.value.at(-1);
    if (!last) return 0;
    return Math.max(0, totalSize.value - last.end);
  });
  const lastVisibleIndex = computed(() => virtualItems.value.at(-1)?.index ?? -1);

  function scrollToIndex(index, align = "auto") {
    if (!Number.isInteger(index) || index < 0) return;
    virtualizer.value.scrollToIndex(index, { align });
  }

  async function restoreScroll(value = rememberedScrollTop.value) {
    const target = options.scrollElement?.value;
    if (!target) return;
    await nextTick();
    target.scrollTop = Math.max(0, Number(value) || 0);
  }

  function rememberScroll() {
    rememberedScrollTop.value = Math.max(0, Number(options.scrollElement?.value?.scrollTop) || 0);
    return rememberedScrollTop.value;
  }

  function measureElement(element) {
    if (!element) return;
    virtualizer.value.measureElement(element);
  }

  function maybeRequestMore() {
    return shouldRequestMoreForVirtualItems({
      count: options.items?.value?.length || 0,
      lastVisibleIndex: lastVisibleIndex.value,
      hasMore: options.hasMore?.value ?? options.hasMore ?? false,
      loading: options.loading?.value ?? options.loading ?? false,
      loadingMore: options.loadingMore?.value ?? options.loadingMore ?? false,
      globalFavoritesMode: options.globalFavoritesMode?.value ?? options.globalFavoritesMode ?? false,
      error: options.error?.value ?? options.error ?? false,
      threshold: options.threshold?.value ?? options.threshold ?? FEED_LOAD_MORE_REMAINING,
    });
  }

  return {
    virtualizer,
    virtualItems,
    totalSize,
    topSpacerPx,
    bottomSpacerPx,
    lastVisibleIndex,
    scrollToIndex,
    rememberScroll,
    restoreScroll,
    measureElement,
    maybeRequestMore,
  };
}
