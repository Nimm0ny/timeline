/** @typedef {import("../types/api.generated").ApiError} ApiErrorShape */
/** @typedef {Partial<ApiErrorShape> & {status?: number}} ApiErrorInit */

const noteVersions = new Map();

const NOTE_RESOURCE_PATH = /^\/api\/notes\/(\d+)\/?$/;

export class ApiError extends Error {
  /** @param {ApiErrorInit} input */
  constructor({ message, status = 0, code = "request_failed", nextAction = "检查服务状态后重试。", details = null }) {
    super(`${message || "请求失败"} 下一步：${nextAction}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.nextAction = nextAction;
    this.details = details;
  }
}

function makeRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function rememberNoteVersions(value, seen = new Set()) {
  if (!value || typeof value !== "object" || seen.has(value)) return;
  seen.add(value);
  if (
    !Array.isArray(value) &&
    Number.isInteger(Number(value.id)) &&
    Number.isInteger(Number(value.topicId)) &&
    typeof value.updatedAt === "string" &&
    value.updatedAt
  ) {
    noteVersions.set(String(value.id), value.updatedAt);
  }
  for (const child of Array.isArray(value) ? value : Object.values(value)) {
    rememberNoteVersions(child, seen);
  }
}

function noteMutation(path, method) {
  if (method !== "PUT" && method !== "DELETE") return null;
  const pathname = String(path).split("?", 1)[0];
  const match = NOTE_RESOURCE_PATH.exec(pathname);
  return match ? { id: match[1], method } : null;
}

function isReadOnlyRequest(path, method) {
  return method === "GET" || method === "HEAD";
}

function attachNoteVersion(path, method, headers) {
  const mutation = noteMutation(path, method);
  if (!mutation || headers.has("If-Match")) return mutation;

  const version = noteVersions.get(mutation.id);
  if (!version) {
    throw new ApiError({
      status: 428,
      code: "precondition_required",
      message: "先读取笔记详情，再保存更改。",
      nextAction: "读取笔记并使用它的 updatedAt 版本；不要发送无版本条件的写入。",
      details: { resourceType: "note", resourceId: Number(mutation.id) },
    });
  }
  headers.set("If-Match", `"${version}"`);
  return mutation;
}

function errorFromResponse(status, data, fallbackMessage) {
  const error = data?.error;
  if (error && typeof error === "object") {
    return new ApiError({
      status,
      code: error.code,
      message: error.message || fallbackMessage,
      nextAction: error.nextAction,
      details: error.details,
    });
  }
  return new ApiError({
    status,
    code: status === 404 ? "not_found" : status === 409 ? "conflict" : "request_failed",
    message: data?.detail || fallbackMessage,
    nextAction: status === 409 ? "重新读取当前状态并协调后重试。" : "检查请求后重试。",
  });
}

async function parseResponse(response) {
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

/**
 * @template Result
 * @param {string} path
 * @param {RequestInit} [options]
 * @returns {Promise<Result>}
 */
async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const method = String(options.method || "GET").toUpperCase();
  const noteMutationInfo = attachNoteVersion(path, method, headers);
  let response;

  try {
    response = await fetch(path, { ...options, method, headers });
  } catch (cause) {
    const isWrite = !isReadOnlyRequest(path, method);
    throw new ApiError({
      code: isWrite ? "unknown_result" : "network_error",
      message: isWrite ? "连接中断，写入结果未知。" : "无法连接到编年服务。",
      nextAction: noteMutationInfo
        ? "先重新读取这篇笔记并比较目标内容；确认结果前不要重放旧请求。"
        : isWrite
          ? "读取对应目录或资源，确认写入结果后再决定是否重试。"
          : "确认服务已启动并检查基础地址。",
      details: {
        resourceId: noteMutationInfo ? Number(noteMutationInfo.id) : undefined,
        method,
        path,
        cause: cause?.message || String(cause),
        requestId: makeRequestId(),
      },
    });
  }

  const data = await parseResponse(response).catch(() => null);
  if (!response.ok) {
    if (noteMutationInfo && response.status === 409) noteVersions.delete(noteMutationInfo.id);
    throw errorFromResponse(response.status, data, response.statusText || "请求失败");
  }

  rememberNoteVersions(data);
  return data;
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function noteMatchesWrite(note, payload) {
  if (!note || !payload || typeof payload !== "object") return false;
  const hasDateInput = ["dateYear", "dateMonth", "dateDay"].some((key) =>
    Object.prototype.hasOwnProperty.call(payload, key),
  );
  if (
    Object.prototype.hasOwnProperty.call(payload, "headline") &&
    !hasDateInput &&
    (note.dateParts?.year != null || note.dateParts?.month != null || note.dateParts?.day != null)
  ) {
    return false;
  }
  const mapped = {
    dateYear: note.dateParts?.year ?? null,
    dateMonth: note.dateParts?.month ?? null,
    dateDay: note.dateParts?.day ?? null,
  };
  for (const [key, expected] of Object.entries(payload)) {
    const actual = Object.prototype.hasOwnProperty.call(mapped, key) ? mapped[key] : note[key];
    if (key === "items" && Array.isArray(expected) && expected.length === 0) continue;
    if (key === "attachments" && Array.isArray(actual) && Array.isArray(expected)) {
      const writableAttachment = ({ id, name, filename, mimeType, thumbFilename, originalFilename, width, height, bytes }) => ({
        id: id ?? null,
        name,
        filename,
        mimeType: mimeType ?? null,
        thumbFilename: thumbFilename ?? null,
        originalFilename: originalFilename ?? null,
        width: width ?? null,
        height: height ?? null,
        bytes: bytes ?? null,
      });
      const actualFiles = actual.map(writableAttachment);
      const expectedFiles = expected.map(writableAttachment);
      if (stableJson(actualFiles) !== stableJson(expectedFiles)) return false;
      continue;
    }
    if (stableJson(actual) !== stableJson(expected)) return false;
  }
  return true;
}

function noteWritePayload(payload) {
  if (!payload || typeof payload !== "object") return payload;
  const result = { ...payload };
  if (Array.isArray(result.attachments)) {
    result.attachments = result.attachments.map((item) => ({
      id: item?.id ?? null,
      name: item?.name,
      filename: item?.filename,
      mimeType: item?.mimeType ?? null,
      thumbFilename: item?.thumbFilename ?? null,
      originalFilename: item?.originalFilename ?? null,
      width: item?.width ?? null,
      height: item?.height ?? null,
      bytes: item?.bytes ?? null,
    }));
  }
  if (Array.isArray(result.items)) {
    result.items = result.items.map((item) => ({ tag: item?.tag || "note", text: item?.text || "" }));
  }
  return result;
}

async function rereadAfterUncertainWrite(noteId, payload, error) {
  try {
    const current = await request(`/api/notes/${encodeURIComponent(noteId)}`);
    if (noteMatchesWrite(current, payload)) return current;
    error.details = { ...(error.details || {}), currentVersion: current.updatedAt };
    error.nextAction = "已回读笔记；当前内容未与本次目标完全一致，请协调差异后再保存。";
  } catch (readError) {
    error.details = { ...(error.details || {}), readbackError: readError.message };
  }
  throw error;
}

export const api = {
  /** @returns {Promise<import("../types/api.generated").FeatureMapOut>} */
  listFeatures() {
    return request("/api/features");
  },
  /** @param {string} featureId @returns {Promise<import("../types/api.generated").FeatureOut>} */
  getFeature(featureId) {
    return request(`/api/features/${encodeURIComponent(featureId)}`);
  },
  /** @returns {Promise<Array<import("../types/api.generated").TopicOut>>} */
  listTopics() {
    return request("/api/topics");
  },
  /** @returns {Promise<Array<import("../types/api.generated").BookshelfOut>>} */
  listBookshelves() {
    return request("/api/bookshelves");
  },
  /** @returns {Promise<Array<import("../types/api.generated").BookshelfTreeItem>>} */
  listBookshelfTree() {
    return request("/api/bookshelves/tree");
  },
  /** @param {string} name @returns {Promise<import("../types/api.generated").BookshelfOut>} */
  createBookshelf(name) {
    return request("/api/bookshelves", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, title: name }),
    });
  },
  /** @param {number} bookshelfId @param {import("../types/api.generated").BookshelfUpdateIn} payload @returns {Promise<import("../types/api.generated").BookshelfOut>} */
  updateBookshelf(bookshelfId, payload) {
    return request(`/api/bookshelves/${encodeURIComponent(bookshelfId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  /** @param {number} bookshelfId @returns {Promise<import("../types/api.generated").DeleteOut>} */
  deleteBookshelf(bookshelfId) {
    return request(`/api/bookshelves/${encodeURIComponent(bookshelfId)}`, { method: "DELETE" });
  },
  /** @returns {Promise<import("../types/api.generated").NoteIndexOut>} */
  getIndex() {
    return request("/api/index");
  },
  /** @param {string} query @param {Pick<import("../types/api.generated").NotesSearchParams, "limit">} [params] @returns {Promise<Array<import("../types/api.generated").NoteSearchItem>>} */
  search(query, params = {}) {
    const search = new URLSearchParams();
    search.set("q", query || "");
    if (params.limit) search.set("limit", String(params.limit));
    return request(`/api/search?${search.toString()}`);
  },
  /** @param {number} id @param {{signal?: AbortSignal}} [options] @returns {Promise<import("../types/api.generated").NoteOut>} */
  getNote(id, { signal } = {}) {
    return request(`/api/notes/${encodeURIComponent(id)}`, signal ? { signal } : {});
  },
  /** @param {string} name @param {number|null} [bookshelfId] @returns {Promise<import("../types/api.generated").TopicOut>} */
  createTopic(name, bookshelfId = null) {
    return request("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bookshelfId ? { name, bookshelfId } : { name }),
    });
  },
  /** @param {number} topicId @returns {Promise<import("../types/api.generated").DeleteOut>} */
  deleteTopic(topicId) {
    return request(`/api/topics/${encodeURIComponent(topicId)}`, { method: "DELETE" });
  },
  /** @param {number} topicId @returns {Promise<import("../types/api.generated").TopicOut>} */
  getTopicMeta(topicId) {
    return request(`/api/topics/${encodeURIComponent(topicId)}/meta`);
  },
  /** @param {number} topicId @param {import("../types/api.generated").TopicMetaUpdateIn} payload @returns {Promise<import("../types/api.generated").TopicOut>} */
  updateTopicMeta(topicId, payload) {
    return request(`/api/topics/${encodeURIComponent(topicId)}/meta`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  /** @param {number} topicId @param {import("../types/api.generated").NotesListParams} [params] @returns {Promise<import("../types/api.generated").NotePageOut>} */
  getNotes(topicId, params = {}) {
    const search = new URLSearchParams();
    if (params.from) search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    if (params.cursor) search.set("cursor", params.cursor);
    if (params.limit) search.set("limit", String(params.limit));
    if (Number(params.dir) < 0) search.set("dir", "-1");
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return request(`/api/topics/${encodeURIComponent(topicId)}/notes${suffix}`);
  },
  /** @param {number} topicId @param {Partial<import("../types/api.generated").TopicSummaryParams>} [params] @returns {Promise<import("../types/api.generated").TopicSummaryOut>} */
  getNotesSummary(topicId, params = {}) {
    const search = new URLSearchParams();
    search.set("groupBy", params.groupBy || "year");
    if (params.from) search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    return request(`/api/topics/${encodeURIComponent(topicId)}/summary?${search.toString()}`);
  },
  /** @param {number} topicId @param {import("../types/api.generated").NoteWriteIn} payload @returns {Promise<import("../types/api.generated").NoteOut>} */
  createTopicNote(topicId, payload) {
    return request(`/api/topics/${encodeURIComponent(topicId)}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(noteWritePayload(payload)),
    });
  },
  /** @param {number} id @param {import("../types/api.generated").NoteWriteIn | import("../types/api.generated").NoteStatePatchIn} payload @returns {Promise<import("../types/api.generated").NoteOut>} */
  async updateNote(id, payload) {
    try {
      return await request(`/api/notes/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(noteWritePayload(payload)),
      });
    } catch (error) {
      if (error.code === "unknown_result" || error.code === "version_conflict") {
        return rereadAfterUncertainWrite(id, noteWritePayload(payload), error);
      }
      throw error;
    }
  },
  /** @param {number} id @param {{permanent?: boolean}} [options] @returns {Promise<import("../types/api.generated").DeleteOut>} */
  async deleteNote(id, { permanent = false } = {}) {
    const search = permanent ? "?permanent=true" : "";
    try {
      const result = await request(`/api/notes/${encodeURIComponent(id)}${search}`, { method: "DELETE" });
      if (permanent) noteVersions.delete(String(id));
      else if (result?.updatedAt) noteVersions.set(String(id), result.updatedAt);
      return result;
    } catch (error) {
      if (error.code !== "unknown_result" && error.code !== "version_conflict") throw error;
      if (permanent) {
        try {
          await request(`/api/notes/${encodeURIComponent(id)}`);
        } catch (readError) {
          if (readError.code === "not_found") {
            noteVersions.delete(String(id));
            return { ok: true };
          }
        }
      } else {
        try {
          const current = await request(`/api/notes/${encodeURIComponent(id)}`);
          if (current.deletedAt) return { ok: true, deletedAt: current.deletedAt };
        } catch (readError) {
          error.details = { ...(error.details || {}), readbackError: readError.message };
        }
      }
      throw error;
    }
  },
  /** @param {number} id @returns {Promise<import("../types/api.generated").DeleteOut>} */
  softDeleteNote(id) {
    return api.deleteNote(id);
  },
  /** @param {number} id @returns {Promise<import("../types/api.generated").DeleteOut>} */
  permanentlyDeleteNote(id) {
    return api.deleteNote(id, { permanent: true });
  },
  /** @param {number} id @returns {Promise<import("../types/api.generated").NoteOut>} */
  restoreNote(id) {
    return api.updateNote(id, { deletedAt: null });
  },
  /** @param {number} id @param {boolean} favorite @returns {Promise<import("../types/api.generated").NoteOut>} */
  updateNoteFavorite(id, favorite) {
    return api.updateNote(id, { favorite });
  },
  /** @param {number} topicId @param {File} file @returns {Promise<import("../types/api.generated").ImportOut>} */
  importData(topicId, file) {
    const formData = new FormData();
    formData.append("file", file);
    return request(`/api/topics/${encodeURIComponent(topicId)}/import`, {
      method: "POST",
      body: formData,
    });
  },
  /** @returns {Promise<import("../types/api.generated").AppConfigOut>} */
  getConfig() {
    return request("/api/config");
  },
  /** @param {import("../types/api.generated").AppConfigUpdateIn} payload @returns {Promise<import("../types/api.generated").AppConfigOut>} */
  updateConfig(payload) {
    return request("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  /** @returns {Promise<Array<string>>} */
  listThemes() {
    return request("/api/themes");
  },
  /** @param {string} name @returns {Promise<Record<string, string>>} */
  getThemeVars(name) {
    return request(`/api/themes/${encodeURIComponent(name)}/vars`);
  },
  /** @param {string} name @param {Record<string, string>} payload @returns {Promise<import("../types/api.generated").OkOut>} */
  updateThemeVars(name, payload) {
    return request(`/api/themes/${encodeURIComponent(name)}/vars`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  /** @param {File} file @returns {Promise<import("../types/api.generated").ImageUploadOut>} */
  uploadImage(file) {
    const formData = new FormData();
    formData.append("file", file);
    return request("/api/media/upload", { method: "POST", body: formData });
  },
  /** @param {string} filename @returns {Promise<import("../types/api.generated").OkOut>} */
  deleteImage(filename) {
    return request(`/api/media/by-filename/${encodeURIComponent(filename)}`, { method: "DELETE" });
  },
  /** @param {number} topicId @param {Partial<import("../types/api.generated").TopicExportParams>} [params] @returns {Promise<import("../types/api.generated").TopicExportOut>} */
  getTopicExportData(topicId, params = {}) {
    const search = new URLSearchParams();
    if (params.from) search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return request(`/api/topics/${encodeURIComponent(topicId)}/export${suffix}`);
  },
  /** @param {number} topicId @returns {void} */
  exportCurrentData(topicId) {
    return api.exportCurrentDataRange(topicId, {});
  },
  /** @param {number} topicId @param {Partial<import("../types/api.generated").TopicExportParams>} [params] @returns {void} */
  exportCurrentDataRange(topicId, params = {}) {
    if (!topicId) return;
    const search = new URLSearchParams();
    if (params.from) search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    const query = search.toString();
    const url = `/api/topics/${encodeURIComponent(topicId)}/export${query ? `?${query}` : ""}`;
    window.open(url, "_blank", "noopener");
  },
};
