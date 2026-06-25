export const ZOOM_CONFIG = {
  year: {
    key: "year",
    label: "Year",
    groupBy: "year",
    unitWidth: 96,
    minVisibleUnits: 8,
    minLoadedUnits: 24,
  },
  month: {
    key: "month",
    label: "Month",
    groupBy: "month",
    unitWidth: 84,
    minVisibleUnits: 10,
    minLoadedUnits: 30,
  },
  day: {
    key: "day",
    label: "Day",
    groupBy: null,
    unitWidth: 72,
    minVisibleUnits: 12,
    minLoadedUnits: 48,
  },
};

export const ZOOM_LEVELS = Object.keys(ZOOM_CONFIG);

function floorDiv(value, divisor) {
  return Math.floor(value / divisor);
}

export function normalizeSortKey(value) {
  return Math.round(Number(value || 0));
}

export function sortKeyToParts(sortKey) {
  const normalized = normalizeSortKey(sortKey);
  const year = floorDiv(normalized, 10000);
  const remainder = normalized - year * 10000;
  return {
    year,
    month: floorDiv(remainder, 100),
    day: remainder % 100,
  };
}

export function partsToSortKey(year, month, day) {
  return year * 10000 + month * 100 + day;
}

export function sortKeyToIso(sortKey) {
  const { year, month, day } = sortKeyToParts(sortKey);
  const sign = year < 0 ? "-" : "";
  return `${sign}${String(Math.abs(year)).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function sortKeyToDayLabel(sortKey) {
  const { month, day } = sortKeyToParts(sortKey);
  return `${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function daysFromCivil(year, month, day) {
  const adjustedYear = year - (month <= 2 ? 1 : 0);
  const era = floorDiv(adjustedYear >= 0 ? adjustedYear : adjustedYear - 399, 400);
  const yoe = adjustedYear - era * 400;
  const mp = month + (month > 2 ? -3 : 9);
  const doy = floorDiv(153 * mp + 2, 5) + day - 1;
  const doe = yoe * 365 + floorDiv(yoe, 4) - floorDiv(yoe, 100) + doy;
  return era * 146097 + doe - 719468;
}

export function civilFromDays(z) {
  const shifted = z + 719468;
  const era = floorDiv(shifted >= 0 ? shifted : shifted - 146096, 146097);
  const doe = shifted - era * 146097;
  const yoe = floorDiv(
    doe - floorDiv(doe, 1460) + floorDiv(doe, 36524) - floorDiv(doe, 146096),
    365
  );
  const yearOfEra = yoe + era * 400;
  const doy = doe - (365 * yoe + floorDiv(yoe, 4) - floorDiv(yoe, 100));
  const mp = floorDiv(5 * doy + 2, 153);
  const day = doy - floorDiv(153 * mp + 2, 5) + 1;
  const month = mp < 10 ? mp + 3 : mp - 9;
  const year = yearOfEra + (month <= 2 ? 1 : 0);
  return { year, month, day };
}

export function sortKeyToUnit(sortKey, zoomLevel) {
  const { year, month, day } = sortKeyToParts(sortKey);
  if (zoomLevel === "year") {
    return year;
  }
  if (zoomLevel === "month") {
    return year * 12 + (month - 1);
  }
  return daysFromCivil(year, month, day);
}

export function bucketKeyToUnit(bucketKey, groupBy) {
  if (groupBy === "year") {
    return Number(bucketKey);
  }
  const value = Number(bucketKey);
  const year = floorDiv(value, 100);
  const month = value - year * 100;
  return year * 12 + (month - 1);
}

export function unitToSortKey(unit, zoomLevel, edge = "start") {
  if (zoomLevel === "year") {
    return partsToSortKey(unit, edge === "end" ? 12 : 1, edge === "end" ? 31 : 1);
  }
  if (zoomLevel === "month") {
    const year = floorDiv(unit, 12);
    const month = unit - year * 12 + 1;
    return partsToSortKey(year, month, edge === "end" ? 31 : 1);
  }
  const parts = civilFromDays(unit);
  return partsToSortKey(parts.year, parts.month, parts.day);
}

export function computeWindowPlan(viewportWidth, zoomLevel) {
  const config = ZOOM_CONFIG[zoomLevel] || ZOOM_CONFIG.year;
  const safeWidth = Math.max(Number(viewportWidth) || 0, 320);
  const visibleUnits = Math.max(
    config.minVisibleUnits,
    Math.ceil(Math.max(safeWidth - 160, 160) / config.unitWidth)
  );
  const loadedUnits = Math.max(config.minLoadedUnits, visibleUnits * 3);
  return {
    unitWidth: config.unitWidth,
    visibleUnits,
    loadedUnits,
    shiftUnits: visibleUnits,
  };
}

export function clampWindowStart(startUnit, bounds, loadedUnits, zoomLevel) {
  if (!bounds?.minSortKey || !bounds?.maxSortKey) {
    return startUnit;
  }
  const minUnit = sortKeyToUnit(bounds.minSortKey, zoomLevel);
  const maxUnit = sortKeyToUnit(bounds.maxSortKey, zoomLevel);
  const maxStart = Math.max(minUnit, maxUnit - loadedUnits + 1);
  return Math.min(Math.max(startUnit, minUnit), maxStart);
}

export function buildWindowRange(startUnit, loadedUnits, zoomLevel) {
  return {
    fromSortKey: unitToSortKey(startUnit, zoomLevel, "start"),
    toSortKey: unitToSortKey(startUnit + loadedUnits - 1, zoomLevel, "end"),
  };
}

export function buildWindowLabel(fromSortKey, toSortKey, zoomLevel) {
  if (zoomLevel === "year") {
    const fromYear = sortKeyToParts(fromSortKey).year;
    const toYear = sortKeyToParts(toSortKey).year;
    return `${fromYear} to ${toYear}`;
  }
  if (zoomLevel === "month") {
    const from = sortKeyToIso(fromSortKey).slice(0, 7);
    const to = sortKeyToIso(toSortKey).slice(0, 7);
    return `${from} to ${to}`;
  }
  return `${sortKeyToIso(fromSortKey)} to ${sortKeyToIso(toSortKey)}`;
}
