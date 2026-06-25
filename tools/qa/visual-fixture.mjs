const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:8000";
const DEFAULT_HEADLINE_TEXT = "\u9e26\u7247\u6218\u4e89";

function fail(message) {
  console.error(`Visual fixture check failed: ${message}`);
  process.exit(1);
}

if (typeof fetch !== "function") fail("global fetch is not available. Use Node.js 18 or newer.");

function readPositiveInt(name, fallback, max = Number.MAX_SAFE_INTEGER) {
  const raw = process.env[name] || String(fallback);
  const value = Number.parseInt(raw, 10);
  if (!/^\d+$/.test(raw) || value < 1 || value > max) {
    fail(`${name} must be an integer between 1 and ${max}. Received: ${raw}`);
  }
  return value;
}

function readBackendOrigin() {
  const raw = process.env.TIMELINE_BACKEND_URL || DEFAULT_BACKEND_ORIGIN;
  try {
    return new URL(raw).origin;
  } catch {
    fail(`TIMELINE_BACKEND_URL must be a valid URL. Received: ${raw}`);
  }
}

async function getJson(origin, pathname) {
  const url = new URL(pathname, `${origin}/`);
  let response;
  try {
    response = await fetch(url);
  } catch (error) {
    fail(`GET ${url.href} failed. Is the backend running? ${error.message}`);
  }
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    fail(`GET ${url.pathname} returned HTTP ${response.status}. ${body}`.trim());
  }
  try {
    return await response.json();
  } catch (error) {
    fail(`GET ${url.pathname} did not return valid JSON. ${error.message}`);
  }
}

const backendOrigin = readBackendOrigin();
const topicId = readPositiveInt("TIMELINE_VISUAL_TOPIC_ID", 1);
const eventId = readPositiveInt("TIMELINE_VISUAL_EVENT_ID", 1);
const visualPort = readPositiveInt("TIMELINE_VISUAL_PORT", process.env.PORT || 8798, 65535);
const expectedHeadline = (process.env.TIMELINE_VISUAL_EVENT_HEADLINE ?? DEFAULT_HEADLINE_TEXT).trim();
const topics = await getJson(backendOrigin, "/api/topics");
if (!Array.isArray(topics)) fail("GET /api/topics must return an array.");

const ids = (items) => items.map((item) => item?.id).join(", ") || "none";
const topic = topics.find((item) => Number(item?.id) === topicId);
if (!topic) fail(`Topic ${topicId} was not found. Available topic ids: ${ids(topics)}.`);

const payload = await getJson(backendOrigin, `/api/topics/${topicId}/events`);
if (!Array.isArray(payload?.items)) {
  fail(`GET /api/topics/${topicId}/events must return an object with an items array.`);
}

const event = payload.items.find((item) => Number(item?.id) === eventId);
if (!event) fail(`Event ${eventId} was not found in topic ${topicId}. Available event ids: ${ids(payload.items)}.`);
if (event.deletedAt) fail(`Event ${eventId} is deleted. deletedAt=${event.deletedAt}`);

const actualText = `${event.headline ?? ""} ${event.displayLabel ?? ""}`;
if (expectedHeadline && !actualText.includes(expectedHeadline)) {
  fail(
    `Event ${eventId} headline/displayLabel does not include "${expectedHeadline}". `
      + `headline="${event.headline ?? ""}", displayLabel="${event.displayLabel ?? ""}".`,
  );
}

console.log(`Visual fixture URL: http://127.0.0.1:${visualPort}/?topic=${topicId}&event=${eventId}&mode=edit`);
console.log(`Topic: id=${topic.id}, name="${topic.name ?? ""}", title="${topic.title ?? ""}", eventCount=${topic.eventCount ?? "unknown"}`);
console.log(`Event: id=${event.id}, headline="${event.headline ?? ""}", displayLabel="${event.displayLabel ?? ""}", deletedAt=${event.deletedAt ?? "null"}`);
