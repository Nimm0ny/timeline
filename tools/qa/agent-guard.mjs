import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const uiSrc = path.join(root, "ui", "src");
const allowedLucideFile = path.normalize(path.join(uiSrc, "components", "notes", "LucideIcon.vue"));

const TARGET_EXTENSIONS = new Set([".vue", ".css", ".js"]);

function walk(dir) {
  if (!fs.existsSync(dir)) return [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walk(fullPath));
    } else if (TARGET_EXTENSIONS.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }
  return files;
}

function lineNumber(source, index) {
  return source.slice(0, index).split(/\r?\n/).length;
}

function vueStyleRanges(source) {
  const ranges = [];
  const styleBlockPattern = /<style\b[^>]*>([\s\S]*?)<\/style>/gi;
  for (const match of source.matchAll(styleBlockPattern)) {
    const content = match[1];
    ranges.push({
      source: content,
      start: match.index + match[0].indexOf(content),
    });
  }

  const staticStylePattern = /\bstyle\s*=\s*(["'])([\s\S]*?)\1/gi;
  for (const match of source.matchAll(staticStylePattern)) {
    const content = match[2];
    ranges.push({
      source: content,
      start: match.index + match[0].indexOf(content),
    });
  }

  return ranges;
}

function fontCheckRanges(file, source) {
  const extension = path.extname(file);
  if (extension === ".css") {
    return [{ source, start: 0 }];
  }
  if (extension === ".vue") {
    return vueStyleRanges(source);
  }
  return [];
}

const checks = [
  {
    name: "Lucide imports must stay centralized",
    test(file, source) {
      if (path.normalize(file) === allowedLucideFile) return [];
      return [...source.matchAll(/from\s+["']@lucide\/vue["']/g)].map((match) => ({
        file,
        line: lineNumber(source, match.index),
        message: "Import Lucide only inside LucideIcon.vue, then consume icons by name.",
      }));
    },
  },
  {
    name: "No scattered inline SVG in timeline UI",
    test(file, source) {
      if (path.normalize(file) === allowedLucideFile) return [];
      if (!file.includes(path.join("components", "notes"))) return [];
      return [...source.matchAll(/<svg\b/gi)].map((match) => ({
        file,
        line: lineNumber(source, match.index),
        message: "Use LucideIcon.vue or CSS DOM primitives instead of inline SVG.",
      }));
    },
  },
  {
    name: "No browser confirm for unsaved changes",
    test(file, source) {
      return [...source.matchAll(/\b(?:window\.)?confirm\s*\(/g)].map((match) => ({
        file,
        line: lineNumber(source, match.index),
        message: "Use an in-app confirmation modal, never browser confirm().",
      }));
    },
  },
  {
    name: "No outer transform scale layout",
    test(file, source) {
      return [...source.matchAll(/transform\s*:\s*[^;{}]*\bscale(?:3d|X|Y)?\s*\(/gi)].map((match) => ({
        file,
        line: lineNumber(source, match.index),
        message: "Responsive layout and visual fixes must use real dimensions, not transform scale().",
      }));
    },
  },
  {
    name: "Runtime UI font declarations must use project font tokens",
    test(file, source) {
      const failures = [];
      for (const range of fontCheckRanges(file, source)) {
        for (const match of range.source.matchAll(/font-family\s*:\s*([^;\n}]+)/gi)) {
          const value = match[1];
          if (value.includes("Noto Sans SC") || value.includes("var(--tn-font")) {
            continue;
          }
          failures.push({
            file,
            line: lineNumber(source, range.start + match.index),
            message: `Font declaration must use the project font (Noto Sans SC) or --tn font tokens: ${value.trim()}`,
          });
        }
      }
      return failures;
    },
  },
  {
    name: "Timeline Pretext presets must use project font",
    test(file, source) {
      if (path.normalize(file) !== path.normalize(path.join(uiSrc, "services", "pretextLayout.js"))) {
        return [];
      }
      const requiredPresets = ["timelineCardTitle", "timelineCardPreview", "timelineCardChip"];
      const failures = [];
      for (const preset of requiredPresets) {
        const presetPattern = new RegExp(`${preset}\\s*:\\s*([^\\n,]+),`);
        const match = source.match(presetPattern);
        if (!match || !match[1].includes("Noto Sans SC")) {
          failures.push({
            file,
            line: match ? lineNumber(source, match.index) : 1,
            message: `${preset} must use Noto Sans SC so Pretext matches the runtime UI font.`,
          });
        }
      }
      return failures;
    },
  },
];

const files = walk(uiSrc);
const failures = [];

for (const file of files) {
  const source = fs.readFileSync(file, "utf8");
  for (const check of checks) {
    failures.push(...check.test(file, source).map((failure) => ({ ...failure, check: check.name })));
  }
}

if (failures.length > 0) {
  console.error("AGENTS guard failed:");
  for (const failure of failures) {
    const relative = path.relative(root, failure.file);
    console.error(`- ${relative}:${failure.line} [${failure.check}] ${failure.message}`);
  }
  process.exit(1);
}

console.log(`AGENTS guard passed (${files.length} files checked).`);
