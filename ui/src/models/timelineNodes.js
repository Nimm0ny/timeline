/**
 * @typedef {Object} NoteNode
 * @property {number} id
 * @property {"event"} nodeType
 * @property {number} dateKey
 * @property {number} sortKey
 * @property {string} isoDate
 * @property {{year:number, month:number, day:number}} dateParts
 * @property {string} headline
 * @property {string} displayLabel
 * @property {string} era
 * @property {string|null} image
 * @property {Array<{tag:string,text:string}>} items
 */

/**
 * @typedef {Object} TimelineSummaryNode
 * @property {string} id
 * @property {"summary"} nodeType
 * @property {"year"|"month"} groupBy
 * @property {number} bucketKey
 * @property {number} dateKey
 * @property {number} sortKey
 * @property {string} displayLabel
 * @property {string} headline
 * @property {string} era
 * @property {number} eventCount
 * @property {number} rangeStartKey
 * @property {number} rangeEndKey
 * @property {string} rangeStartDate
 * @property {string} rangeEndDate
 * @property {Array<{tag:string,text:string}>} items
 */

export function normalizeNoteNode(node) {
  return {
    id: Number(node.id),
    nodeType: "event",
    dateKey: Number(node.dateKey),
    sortKey: Number(node.sortKey ?? node.dateKey),
    isoDate: String(node.isoDate || ""),
    dateParts: {
      year: Number(node.dateParts?.year),
      month: Number(node.dateParts?.month),
      day: Number(node.dateParts?.day),
    },
    headline: String(node.headline || ""),
    displayLabel: String(node.displayLabel || ""),
    era: String(node.era || ""),
    image: node.image || null,
    items: Array.isArray(node.items) ? node.items : [],
  };
}

export function normalizeSummaryNode(node) {
  return {
    id: String(node.id),
    nodeType: "summary",
    groupBy: node.groupBy,
    bucketKey: Number(node.bucketKey),
    dateKey: Number(node.dateKey ?? node.rangeStartKey),
    sortKey: Number(node.sortKey ?? node.rangeStartKey),
    displayLabel: String(node.displayLabel || ""),
    headline: String(node.headline || node.displayLabel || ""),
    era: String(node.era || ""),
    eventCount: Number(node.eventCount || 0),
    rangeStartKey: Number(node.rangeStartKey),
    rangeEndKey: Number(node.rangeEndKey),
    rangeStartDate: String(node.rangeStartDate || ""),
    rangeEndDate: String(node.rangeEndDate || ""),
    items: Array.isArray(node.items) ? node.items : [],
  };
}

export function normalizeDisplayNode(node) {
  return node.nodeType === "summary" ? normalizeSummaryNode(node) : normalizeNoteNode(node);
}

export function normalizeDisplayNodes(nodes) {
  return (nodes || []).map(normalizeDisplayNode);
}
