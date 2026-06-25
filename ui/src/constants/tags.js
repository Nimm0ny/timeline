export const TAG_OPTIONS = [
  { value: "war", label: "战争" },
  { value: "politics", label: "政治" },
  { value: "culture", label: "文化" },
  { value: "science", label: "科技" },
  { value: "explore", label: "探索" },
  { value: "disaster", label: "灾难" },
  { value: "reform", label: "改革" },
  { value: "diplomacy", label: "外交" },
  { value: "economy", label: "经济" },
  { value: "summary", label: "Summary" },
];

const TAG_LABEL_MAP = Object.fromEntries(
  TAG_OPTIONS.map((option) => [option.value, option.label])
);

export function getTagLabel(tag) {
  return TAG_LABEL_MAP[tag] || tag;
}
