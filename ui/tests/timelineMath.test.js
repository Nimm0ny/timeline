import test from "node:test";
import assert from "node:assert/strict";

import {
  bucketKeyToUnit,
  buildWindowRange,
  clampWindowStart,
  computeWindowPlan,
  partsToSortKey,
  sortKeyToIso,
  sortKeyToUnit,
} from "../src/utils/timelineMath.js";

test("computeWindowPlan expands with viewport width", () => {
  const compact = computeWindowPlan(420, "year");
  const wide = computeWindowPlan(1440, "year");
  assert.ok(wide.visibleUnits >= compact.visibleUnits);
  assert.ok(wide.loadedUnits >= wide.visibleUnits);
});

test("clampWindowStart keeps window within bounds", () => {
  const bounds = { minSortKey: 18400101, maxSortKey: 18491231 };
  const minUnit = sortKeyToUnit(bounds.minSortKey, "year");
  const start = clampWindowStart(minUnit - 10, bounds, 12, "year");
  assert.equal(start, minUnit);
});

test("buildWindowRange returns ISO-compatible edges", () => {
  const range = buildWindowRange(sortKeyToUnit(18400101, "month"), 3, "month");
  assert.equal(sortKeyToIso(range.fromSortKey), "1840-01-01");
  assert.equal(sortKeyToIso(range.toSortKey), "1840-03-31");
});

test("negative year sort keys preserve chronological order", () => {
  const start = partsToSortKey(-1, 1, 1);
  const later = partsToSortKey(-1, 1, 31);
  assert.ok(later > start);
  assert.equal(sortKeyToIso(start), "-0001-01-01");
  assert.ok(sortKeyToUnit(later, "day") > sortKeyToUnit(start, "day"));
  assert.equal(bucketKeyToUnit(-99, "month"), -12);
});
