export const TAG_OPTIONS = [
  { value: "war", label: "战争", color: "var(--t-war)" },
  { value: "politics", label: "政治", color: "var(--t-politics)" },
  { value: "culture", label: "文化", color: "var(--t-culture)" },
  { value: "science", label: "科技", color: "var(--t-science)" },
  { value: "explore", label: "探索", color: "var(--t-science)" },
  { value: "disaster", label: "灾难", color: "var(--t-war)" },
  { value: "reform", label: "改革", color: "var(--t-reform)" },
  { value: "diplomacy", label: "外交", color: "var(--t-diplomacy)" },
  { value: "economy", label: "经济", color: "var(--t-economy)" },
  { value: "summary", label: "Summary", color: "var(--accent)" },
];

const TAG_LABEL_MAP = Object.fromEntries(
  TAG_OPTIONS.map((option) => [option.value, option.label])
);

export function getTagLabel(tag) {
  return TAG_LABEL_MAP[tag] || tag;
}

const TAG_COLOR_MAP = Object.fromEntries(
  TAG_OPTIONS.map((option) => [option.value, option.color || "var(--accent)"])
);

export function getTagColor(tag) {
  return TAG_COLOR_MAP[tag] || "var(--accent)";
}

// Palette tokens cycled when a brand-new option is created in the OptionPicker.
export const OPTION_PALETTE = [
  "var(--t-war)",
  "var(--t-politics)",
  "var(--t-culture)",
  "var(--t-science)",
  "var(--t-reform)",
  "var(--t-diplomacy)",
  "var(--t-economy)",
];
