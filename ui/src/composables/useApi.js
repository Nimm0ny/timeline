async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});

  const response = await fetch(path, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const fallbackMessage = response.statusText || "请求失败";
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || fallbackMessage);
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
}

export const api = {
  request,
  listTopics() {
    return request("/api/topics");
  },
  listBookshelves() {
    return request("/api/bookshelves");
  },
  getIndex() {
    return request("/api/index");
  },
  search(query, params = {}) {
    const search = new URLSearchParams();
    search.set("q", query || "");
    if (params.limit) search.set("limit", String(params.limit));
    return request(`/api/search?${search.toString()}`);
  },
  getEvent(id) {
    return request(`/api/events/${encodeURIComponent(id)}`);
  },
  createTopic(name, bookshelfId = null) {
    return request("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bookshelfId ? { name, bookshelfId } : { name }),
    });
  },
  deleteTopic(topicId) {
    return request(`/api/topics/${encodeURIComponent(topicId)}`, {
      method: "DELETE",
    });
  },
  getTopicMeta(topicId) {
    return request(`/api/topics/${encodeURIComponent(topicId)}/meta`);
  },
  updateTopicMeta(topicId, payload) {
    return request(`/api/topics/${encodeURIComponent(topicId)}/meta`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  getTimelineEvents(topicId, params = {}) {
    const search = new URLSearchParams();
    if (params.from) search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    if (params.cursor) search.set("cursor", params.cursor);
    if (params.limit) search.set("limit", String(params.limit));
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return request(`/api/topics/${encodeURIComponent(topicId)}/events${suffix}`);
  },
  getTimelineSummary(topicId, params = {}) {
    const search = new URLSearchParams();
    search.set("groupBy", params.groupBy || "year");
    if (params.from) search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    return request(`/api/topics/${encodeURIComponent(topicId)}/summary?${search.toString()}`);
  },
  createTopicEvent(topicId, payload) {
    return request(`/api/topics/${encodeURIComponent(topicId)}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  getEvents(topicId) {
    return request(`/api/topics/${encodeURIComponent(topicId)}/events`);
  },
  createEvent(topicId, payload) {
    return api.createTopicEvent(topicId, payload);
  },
  updateEvent(id, payload) {
    return request(`/api/events/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  deleteEvent(id) {
    return request(`/api/events/${id}`, { method: "DELETE" });
  },
  softDeleteEvent(id) {
    return api.deleteEvent(id);
  },
  permanentlyDeleteEvent(id) {
    return request(`/api/events/${id}?permanent=true`, { method: "DELETE" });
  },
  restoreEvent(id) {
    return api.updateEvent(id, { deletedAt: null });
  },
  updateEventFavorite(id, favorite) {
    return api.updateEvent(id, { favorite });
  },
  importData(topicId, file) {
    const formData = new FormData();
    formData.append("file", file);
    return request(`/api/topics/${encodeURIComponent(topicId)}/import`, {
      method: "POST",
      body: formData,
    });
  },
  getConfig() {
    return request("/api/config");
  },
  updateConfig(payload) {
    return request("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  getDataMeta(topicId) {
    return api.getTopicMeta(topicId);
  },
  updateDataMeta(topicId, payload) {
    return api.updateTopicMeta(topicId, payload);
  },
  listDataFiles() {
    return api.listTopics();
  },
  createDataFile(name) {
    return api.createTopic(name);
  },
  deleteDataFile(topicId) {
    return api.deleteTopic(topicId);
  },
  listThemes() {
    return request("/api/themes");
  },
  getThemeVars(name) {
    return request(`/api/themes/${encodeURIComponent(name)}/vars`);
  },
  updateThemeVars(name, payload) {
    return request(`/api/themes/${encodeURIComponent(name)}/vars`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  uploadImage(file) {
    const formData = new FormData();
    formData.append("file", file);
    return request("/api/media/upload", {
      method: "POST",
      body: formData,
    });
  },
  deleteImage(filename) {
    return request(`/api/media/by-filename/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    });
  },
  getTopicExportData(topicId, params = {}) {
    const search = new URLSearchParams();
    if (params.from) search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return request(`/api/topics/${encodeURIComponent(topicId)}/export${suffix}`);
  },
  exportCurrentData(topicId) {
    return api.exportCurrentDataRange(topicId, {});
  },
  exportCurrentDataRange(topicId, params = {}) {
    if (!topicId) {
      return;
    }
    const search = new URLSearchParams();
    if (params.from) search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    const query = search.toString();
    const url = `/api/topics/${encodeURIComponent(topicId)}/export${query ? `?${query}` : ""}`;
    window.open(url, "_blank", "noopener");
  },
};
