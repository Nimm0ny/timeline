import { buildSvgTextBlock, requirePretextSupport } from "@/services/pretextLayout";
import { normalizeDisplayNodes } from "@/models/noteNodes";

function escapeXml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function svgTextLines(lines, x, y, lineHeight, options = {}) {
  const anchor = options.anchor || "start";
  const fill = options.fill || "#f5f7ff";
  const size = options.size || 14;
  const weight = options.weight || 500;
  return [
    `<text x="${x}" y="${y}" text-anchor="${anchor}" fill="${fill}" font-size="${size}" font-weight="${weight}" font-family="Segoe UI, Microsoft YaHei, PingFang SC, sans-serif">`,
    ...lines.map(
      (line, index) =>
        `<tspan x="${x}" dy="${index === 0 ? 0 : lineHeight}">${escapeXml(line)}</tspan>`
    ),
    "</text>",
  ].join("");
}

export function buildTimelineExportSvg({
  title,
  subtitle,
  from,
  to,
  items,
}) {
  requirePretextSupport();
  const nodes = normalizeDisplayNodes(items);
  const width = 1280;
  const paddingX = 80;
  const headerWidth = width - paddingX * 2;
  const titleBlock = buildSvgTextBlock(title || "Timeline", "exportTitle", headerWidth, 38, 2);
  const subtitleBlock = buildSvgTextBlock(subtitle || "", "exportBody", headerWidth, 24, 2);
  const rangeLabel = `${from || ""}${from && to ? " to " : ""}${to || ""}`.trim();
  const metaBlock = buildSvgTextBlock(rangeLabel || "Full range", "exportBody", headerWidth, 22, 2);

  let y = 90 + titleBlock.height + subtitleBlock.height + metaBlock.height;
  const bodyParts = [];

  for (const [index, node] of nodes.entries()) {
    const cardX = index % 2 === 0 ? paddingX : width / 2 + 40;
    const cardWidth = width / 2 - paddingX - 60;
    const header = buildSvgTextBlock(node.displayLabel || node.headline || "", "exportHeading", cardWidth - 40, 24, 2);
    const era = buildSvgTextBlock(node.era || "", "exportBody", cardWidth - 40, 20, 2);
    const snippet = buildSvgTextBlock(
      (node.items || []).slice(0, 3).map((item) => `${item.tag}: ${item.text}`).join(" "),
      "exportBody",
      cardWidth - 40,
      20,
      5
    );
    const cardHeight = 72 + header.height + era.height + snippet.height;
    const axisX = width / 2;
    const cardY = y;

    bodyParts.push(
      `<line x1="${axisX}" y1="${cardY + 8}" x2="${axisX}" y2="${cardY + cardHeight + 48}" stroke="#3a3f5c" stroke-width="2" />`
    );
    bodyParts.push(
      `<circle cx="${axisX}" cy="${cardY + 24}" r="8" fill="#55b5ff" stroke="#99d0ff" stroke-width="3" />`
    );
    bodyParts.push(
      `<rect x="${cardX}" y="${cardY}" rx="16" ry="16" width="${cardWidth}" height="${cardHeight}" fill="#1b2036" stroke="#353c5d" />`
    );
    bodyParts.push(svgTextLines(header.lines, cardX + 20, cardY + 34, 24, { size: 18, weight: 700 }));
    bodyParts.push(svgTextLines(era.lines, cardX + 20, cardY + 34 + header.height + 8, 20, { size: 13, fill: "#aeb6d6" }));
    bodyParts.push(
      svgTextLines(snippet.lines, cardX + 20, cardY + 34 + header.height + era.height + 18, 20, {
        size: 14,
        fill: "#d8def6",
      })
    );
    y += cardHeight + 40;
  }

  const height = Math.max(720, y + 60);

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="${width}" height="${height}" fill="#111323" />
  ${svgTextLines(titleBlock.lines, paddingX, 90, 38, { size: 30, weight: 700 })}
  ${svgTextLines(subtitleBlock.lines, paddingX, 90 + titleBlock.height + 10, 24, { size: 18, fill: "#bac3e6" })}
  ${svgTextLines(metaBlock.lines, paddingX, 90 + titleBlock.height + subtitleBlock.height + 22, 22, { size: 14, fill: "#8b95bb" })}
  ${bodyParts.join("\n  ")}
</svg>`;
}

export function downloadSvg(svgText, filename) {
  const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function downloadPngFromSvg(svgText, filename) {
  const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const image = new Image();
  image.decoding = "async";
  image.src = url;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  const context = canvas.getContext("2d");
  context.drawImage(image, 0, 0);
  URL.revokeObjectURL(url);
  return await new Promise((resolve) => {
    canvas.toBlob((result) => {
      const pngUrl = URL.createObjectURL(result);
      const link = document.createElement("a");
      link.href = pngUrl;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(pngUrl);
      resolve();
    }, "image/png");
  });
}
