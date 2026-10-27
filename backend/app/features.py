from copy import deepcopy


FEATURE_MAP_VERSION = "2.4"

_UI_CONTRACTS = {
    "notes.browse": ["notes.browse"],
    "notes.read": ["notes.read"],
    "notes.search": ["notes.search"],
    "notes.analysis": ["notes.analysis"],
    "notes.create": ["notes.create"],
    "notes.update": ["notes.update"],
    "topics.manage": ["topics.manage"],
    "bookshelves.manage": ["bookshelves.manage"],
    "notes.transfer": ["notes.transfer"],
    "media.manage": ["media.manage"],
    "app.settings": ["app.settings"],
    "app.themes": ["app.themes"],
}


def _operation(
    operation_id: str,
    method: str,
    path: str,
    response_schema: str,
    *,
    read_only: bool = False,
    lifecycle: str = "active",
    client_method: str | None = None,
    request_schema: str | None = None,
    query_schema: str | None = None,
    request_headers: tuple[str, ...] = (),
    content_type: str = "application/json",
) -> dict:
    operation = {
        "operationId": operation_id,
        "method": method,
        "path": path,
        "readOnly": read_only,
        "lifecycle": lifecycle,
        "requestHeaders": list(request_headers),
        "contentType": content_type,
    }
    if client_method:
        operation["clientMethod"] = client_method
    operation["cliCommand"] = f"api call {operation_id} --input-file <input.json>"
    if response_schema == "Binary":
        operation["cliCommand"] += " --output-file <path>"
    if not read_only:
        operation["cliCommand"] += " --confirm"
    if request_schema:
        operation["requestSchema"] = request_schema
    if query_schema:
        operation["querySchema"] = query_schema
    if response_schema:
        operation["responseSchema"] = response_schema
    return operation


def _scenario(
    scenario_id: str,
    title: str,
    summary: str,
    input_schema: str,
    steps: list[dict],
    *,
    preconditions: list[str] | None = None,
    read_only: bool = True,
) -> dict:
    return {
        "id": scenario_id,
        "title": title,
        "summary": summary,
        "inputSchema": input_schema,
        "readOnly": read_only,
        "preconditions": preconditions or [],
        "steps": steps,
        "cleanup": "No writes; no cleanup is required." if read_only else "Requires user confirmation.",
    }


_FEATURES = [
    {
        "id": "app.discovery",
        "title": "发现应用能力",
        "summary": "读取全应用 Feature Map 和单项能力说明。",
        "ui": {"route": None, "entryPoint": "CLI Feature Map discovery", "hasWebEntry": False},
        "api": [
            _operation("features_list", "GET", "/api/features", "FeatureMapOut", read_only=True, client_method="listFeatures"),
            _operation("features_get", "GET", "/api/features/{feature_id}", "FeatureOut", read_only=True, client_method="getFeature"),
        ],
        "stateOwner": "Feature registry in backend.app.features",
        "dataScope": "Static capability metadata; no note data is read or changed.",
        "preconditions": [],
        "permissions": ["features:read"],
        "persistedResult": "None; the Feature Map is returned from the registered application capability catalog.",
        "failureRecovery": ["For unknown_feature, list the Feature Map and select a registered id."],
        "scenarios": [],
    },
    {
        "id": "app.diagnostics",
        "title": "检查应用 API",
        "summary": "核验服务身份、API 契约覆盖和主要只读应用入口。",
        "ui": {"route": None, "entryPoint": "CLI doctor and scenario commands", "hasWebEntry": False},
        "api": [
            _operation("runtime_identity", "GET", "/api/runtime/identity", "RuntimeIdentityOut", read_only=True),
        ],
        "stateOwner": "FastAPI runtime and OpenAPI description",
        "dataScope": "Service metadata and read-only application health requests.",
        "preconditions": ["The Chronicle HTTP service is running."],
        "permissions": ["runtime:read"],
        "persistedResult": "None; diagnostics issue read-only HTTP requests.",
        "failureRecovery": ["Use the per-check failure and nextAction; diagnostics do not change service data."],
        "scenarios": [
            _scenario(
                "app.read-smoke",
                "检查主要应用读取能力",
                "通过正式 HTTP API 读取服务身份、笔记本、索引、分组、设置和主题，并校验响应 schema。",
                "EmptyInput",
                [
                    {"id": "runtime", "operationId": "runtime_identity", "assertions": ["response validates as RuntimeIdentityOut"]},
                    {"id": "topics", "operationId": "topics_list", "assertions": ["response validates as TopicOut[]"]},
                    {"id": "index", "operationId": "notes_index", "assertions": ["response validates as NoteIndexOut"]},
                    {"id": "bookshelves", "operationId": "bookshelves_tree", "assertions": ["response validates as BookshelfTreeItem[]"]},
                    {"id": "config", "operationId": "config_get", "assertions": ["response validates as AppConfigOut"]},
                    {"id": "themes", "operationId": "themes_list", "assertions": ["response is a string array"]},
                ],
            ),
        ],
    },
    {
        "id": "notes.browse",
        "title": "浏览笔记",
        "summary": "读取笔记本目录、全局索引和指定笔记本中的分页笔记。",
        "ui": {"route": "/", "entryPoint": "NotesPage 的笔记本目录、列表和时间线"},
        "api": [
            _operation("topics_list", "GET", "/api/topics", "TopicOut[]", read_only=True, client_method="listTopics"),
            _operation("notes_index", "GET", "/api/index", "NoteIndexOut", read_only=True, client_method="getIndex"),
            _operation("notes_list", "GET", "/api/topics/{topic_id}/notes", "NotePageOut", read_only=True, client_method="getNotes", query_schema="NoteListQuery"),
        ],
        "stateOwner": "FastAPI note query and topic read models",
        "dataScope": "Visible notes in the selected topic and the current page range.",
        "preconditions": ["topicId refers to an existing topic"],
        "permissions": ["notes:read"],
        "persistedResult": "None; list and index operations read current persisted state.",
        "failureRecovery": ["For not_found, refresh the topic list and select a current topic."],
        "scenarios": [
            _scenario(
                "notes.list-readback",
                "读取笔记本并核对笔记身份",
                "读取指定笔记本的一页，并确认目标笔记在返回页中。",
                "NoteListScenarioInput",
                [{"id": "list-notes", "operationId": "notes_list", "assertions": ["response.items contains input.containsNoteId"]}],
                preconditions=["topicId exists", "containsNoteId is in the requested page"],
            ),
        ],
    },
    {
        "id": "notes.read",
        "title": "读取笔记详情",
        "summary": "读取笔记正文、属性、附件和当前版本。",
        "ui": {"route": "/", "entryPoint": "NotesPage 的笔记选择和 NoteDetailPane"},
        "api": [_operation("notes_get", "GET", "/api/notes/{note_id}", "NoteOut", read_only=True, client_method="getNote")],
        "stateOwner": "Note row and its attachment and property data",
        "dataScope": "One note selected by noteId.",
        "preconditions": ["noteId refers to an existing note"],
        "permissions": ["notes:read"],
        "persistedResult": "None; updatedAt is the version token for a later conditional write.",
        "failureRecovery": ["For not_found, refresh the note list before retrying."],
        "scenarios": [
            _scenario(
                "notes.readback",
                "读取并核对笔记身份和版本",
                "通过正式详情 API 读取笔记，确认身份和版本可用于后续建议。",
                "NoteReadScenarioInput",
                [{"id": "read-note", "operationId": "notes_get", "assertions": ["response.id equals input.noteId", "response.updatedAt is present"]}],
                preconditions=["noteId refers to an existing note"],
            ),
        ],
    },
    {
        "id": "notes.search",
        "title": "搜索笔记",
        "summary": "通过正式搜索 API 检索笔记并返回跳转身份和摘要。",
        "ui": {
            "route": "/",
            "entryPoint": "NotesPage 全局搜索命令面板（Ctrl+K）",
            "contractIds": ["notes.search"],
        },
        "api": [_operation("notes_search", "GET", "/api/search", "NoteSearchItem[]", read_only=True, client_method="search", query_schema="NoteSearchQuery")],
        "stateOwner": "FastAPI search index and live note rows",
        "dataScope": "Search results across live notes.",
        "preconditions": ["query is non-empty", "limit is between 1 and 50"],
        "permissions": ["notes:read"],
        "persistedResult": "None; search reads the current index and note state.",
        "failureRecovery": ["For stale results, read the note detail again before acting on a result."],
        "scenarios": [
            _scenario(
                "notes.search-readback",
                "搜索并核对目标笔记",
                "执行正式搜索，并确认目标笔记出现在结果中。",
                "NoteSearchScenarioInput",
                [{"id": "search-notes", "operationId": "notes_search", "assertions": ["response contains input.expectedNoteId"]}],
                preconditions=["query matches expectedNoteId"],
            ),
        ],
    },
    {
        "id": "notes.analysis",
        "title": "浏览笔记本摘要",
        "summary": "读取指定笔记本的分组摘要。",
        "ui": {"route": "/", "entryPoint": "NotesPage 的分组笔记视图"},
        "api": [
            _operation("topics_summary", "GET", "/api/topics/{topic_id}/summary", "TopicSummaryOut", read_only=True, client_method="getNotesSummary", query_schema="TopicSummaryQuery"),
        ],
        "stateOwner": "Topic summary query",
        "dataScope": "The selected topic and date range.",
        "preconditions": ["The topic exists"],
        "permissions": ["notes:read"],
        "persistedResult": "None; the summary reflects current note data.",
        "failureRecovery": ["Refresh the topic and request the summary again."],
        "scenarios": [],
    },
    {
        "id": "notes.create",
        "title": "创建笔记",
        "summary": "在指定笔记本中新建 Markdown 笔记。",
        "ui": {"route": "/", "entryPoint": "NoteDetailPane 的新建笔记操作"},
        "api": [
            _operation("notes_create", "POST", "/api/topics/{topic_id}/notes", "NoteOut", client_method="createTopicNote", request_schema="NoteWriteIn"),
        ],
        "stateOwner": "Notes API and note read models",
        "dataScope": "The target topic and the new note created within it.",
        "preconditions": ["The user confirms the creation"],
        "permissions": ["notes:write", "user:confirm"],
        "persistedResult": "A new note with a stable numeric id and updatedAt version.",
        "failureRecovery": ["If the result is unknown, read the topic notes and reconcile before retrying."],
        "scenarios": [],
    },
    {
        "id": "notes.update",
        "title": "更新和删除笔记",
        "summary": "按笔记身份和读取时的 updatedAt 条件更新或删除笔记；过期版本会被拒绝。CLI 不绕过用户确认直接执行写入。",
        "ui": {"route": "/", "entryPoint": "NoteDetailPane 的保存和回收站操作"},
        "api": [
            _operation("notes_update", "PUT", "/api/notes/{note_id}", "NoteOut", client_method="updateNote", request_schema="NoteWriteIn | NoteStatePatchIn", request_headers=("If-Match: updatedAt",)),
            _operation("notes_delete", "DELETE", "/api/notes/{note_id}", "DeleteOut", client_method="deleteNote", request_headers=("If-Match: updatedAt",)),
        ],
        "stateOwner": "Note row and its updatedAt version",
        "dataScope": "One note or a new note in one selected topic.",
        "preconditions": ["The user confirms a scoped proposal", "Updates and deletes include the current If-Match version"],
        "permissions": ["notes:write", "user:confirm"],
        "persistedResult": "The note is changed only after confirmation and returned with its new version.",
        "failureRecovery": ["For version_conflict, reread and reconcile; never retry a stale payload."],
        "operationIdentity": "A conditional write is identified by resource id, source updatedAt, and canonical request body.",
        "scenarios": [],
    },
    {
        "id": "topics.manage",
        "title": "管理筆記本",
        "summary": "讀取筆記本與元數據，並管理筆記本名稱、視圖和分組。",
        "ui": {"route": "/", "entryPoint": "NotesPage 的筆記本側欄、筆記本設定和創建操作"},
        "api": [
            _operation("topics_list", "GET", "/api/topics", "TopicOut[]", read_only=True, client_method="listTopics"),
            _operation("topics_get", "GET", "/api/topics/{topic_id}", "TopicOut", read_only=True),
            _operation("topics_create", "POST", "/api/topics", "TopicOut", client_method="createTopic", request_schema="TopicCreateIn"),
            _operation("topics_delete", "DELETE", "/api/topics/{topic_id}", "DeleteOut", client_method="deleteTopic"),
            _operation("topics_meta_get", "GET", "/api/topics/{topic_id}/meta", "TopicOut", read_only=True, client_method="getTopicMeta"),
            _operation("topics_meta_update", "PUT", "/api/topics/{topic_id}/meta", "TopicOut", client_method="updateTopicMeta", request_schema="TopicMetaUpdateIn"),
        ],
        "stateOwner": "Topic, TopicStat and topic metadata records",
        "dataScope": "A selected topic and its note summary fields.",
        "preconditions": ["Topic mutations require user confirmation"],
        "permissions": ["topics:read", "topics:write", "user:confirm"],
        "persistedResult": "Topic metadata and note counts are returned by the formal TopicOut DTO.",
        "failureRecovery": ["Reread topic metadata after an unknown write result."],
        "scenarios": [],
    },
    {
        "id": "bookshelves.manage",
        "title": "管理笔记本分组",
        "summary": "读取分组树，创建、改名或删除空分组。",
        "ui": {"route": "/", "entryPoint": "NotesPage 的分组侧栏"},
        "api": [
            _operation("bookshelves_list", "GET", "/api/bookshelves", "BookshelfOut[]", read_only=True, client_method="listBookshelves"),
            _operation("bookshelves_tree", "GET", "/api/bookshelves/tree", "BookshelfTreeItem[]", read_only=True, client_method="listBookshelfTree"),
            _operation("bookshelves_create", "POST", "/api/bookshelves", "BookshelfOut", client_method="createBookshelf", request_schema="BookshelfCreateIn"),
            _operation("bookshelves_update", "PUT", "/api/bookshelves/{bookshelf_id}", "BookshelfOut", client_method="updateBookshelf", request_schema="BookshelfUpdateIn"),
            _operation("bookshelves_delete", "DELETE", "/api/bookshelves/{bookshelf_id}", "DeleteOut", client_method="deleteBookshelf"),
        ],
        "stateOwner": "Bookshelf and topic assignment records",
        "dataScope": "One bookshelf and its assigned topics.",
        "preconditions": ["A bookshelf can be deleted only while empty", "Mutations require user confirmation"],
        "permissions": ["bookshelves:read", "bookshelves:write", "user:confirm"],
        "persistedResult": "Updated bookshelf DTO or an empty successful delete result.",
        "failureRecovery": ["For conflict, reread the bookshelf tree and resolve topic assignments first."],
        "scenarios": [],
    },
    {
        "id": "notes.transfer",
        "title": "导入和导出笔记本数据",
        "summary": "按指定笔记本和日期范围读取导出数据，或从 JSON 文件导入。",
        "ui": {"route": "/", "entryPoint": "NotesPage 的导入和导出操作"},
        "api": [
            _operation("topics_export", "GET", "/api/topics/{topic_id}/export", "TopicExportOut", read_only=True, client_method="getTopicExportData", query_schema="TopicExportQuery"),
            _operation("topics_import", "POST", "/api/topics/{topic_id}/import", "ImportOut", client_method="importData", request_schema="MultipartFileIn", content_type="multipart/form-data"),
        ],
        "stateOwner": "Topic records and imported note rows",
        "dataScope": "Export reads the selected topic; import writes only into the selected topic.",
        "preconditions": ["Import requires a valid JSON export and user confirmation"],
        "permissions": ["notes:read", "notes:write", "user:confirm"],
        "persistedResult": "Export data or the count of imported notes.",
        "failureRecovery": ["Validate export JSON before import; after an unknown import result, reread the target topic before retrying."],
        "scenarios": [],
    },
    {
        "id": "media.manage",
        "title": "管理附件和图片",
        "summary": "上传图片资产并安全删除未被笔记引用的资产。",
        "ui": {"route": "/", "entryPoint": "NoteDetailPane 的图片和附件操作"},
        "api": [
            _operation("media_read", "GET", "/api/media/by-filename/{filename}", "Binary", read_only=True),
            _operation("media_upload", "POST", "/api/media/upload", "ImageUploadOut", client_method="uploadImage", request_schema="MultipartFileIn", content_type="multipart/form-data"),
            _operation("media_delete", "DELETE", "/api/media/by-filename/{filename}", "OkOut", client_method="deleteImage"),
        ],
        "stateOwner": "ImageAsset records and files in the configured media directory",
        "dataScope": "A single uploaded asset; deletion is allowed only when no note references it.",
        "preconditions": ["The user starts an upload or confirms removal of an unused asset"],
        "permissions": ["media:write", "user:confirm"],
        "persistedResult": "Asset metadata with URLs, or a successful removal result.",
        "failureRecovery": ["For in_use, keep the asset and remove its note references first."],
        "scenarios": [],
    },
    {
        "id": "app.settings",
        "title": "读取和更新应用设置",
        "summary": "读取配置，并通过有类型的部分更新契约写入设置。",
        "ui": {"route": "/", "entryPoint": "NotesPage 的设置面板"},
        "api": [
            _operation("config_get", "GET", "/api/config", "AppConfigOut", read_only=True, client_method="getConfig"),
            _operation("config_update", "PUT", "/api/config", "AppConfigOut", client_method="updateConfig", request_schema="AppConfigUpdateIn"),
        ],
        "stateOwner": "AppConfigEntry records and current application defaults",
        "dataScope": "Global application settings.",
        "preconditions": ["Updates contain only fields being changed and require user confirmation"],
        "permissions": ["config:read", "config:write", "user:confirm"],
        "persistedResult": "The merged application configuration is returned after commit.",
        "failureRecovery": ["Reread /api/config after an unknown update result."],
        "scenarios": [],
    },
    {
        "id": "app.themes",
        "title": "读取和更新主题",
        "summary": "列出主题并读取或更新具名主题变量。",
        "ui": {"route": "/", "entryPoint": "NotesPage 的主题设置"},
        "api": [
            _operation("themes_list", "GET", "/api/themes", "string[]", read_only=True, client_method="listThemes"),
            _operation("themes_vars_get", "GET", "/api/themes/{name}/vars", "Record<string,string>", read_only=True, client_method="getThemeVars"),
            _operation("themes_vars_update", "PUT", "/api/themes/{name}/vars", "OkOut", client_method="updateThemeVars", request_schema="Record<string,string>"),
        ],
        "stateOwner": "Theme variable files in the configured theme directory",
        "dataScope": "Only the named theme variable set.",
        "preconditions": ["Theme updates require user confirmation"],
        "permissions": ["themes:read", "themes:write", "user:confirm"],
        "persistedResult": "Theme variables are written to the selected theme stylesheet.",
        "failureRecovery": ["Reread theme variables after an unknown update result."],
        "scenarios": [],
    },
]


def list_features() -> dict:
    return {"version": FEATURE_MAP_VERSION, "features": [_feature_payload(item) for item in _FEATURES]}


def get_feature(feature_id: str) -> dict | None:
    for feature in _FEATURES:
        if feature["id"] == feature_id:
            return _feature_payload(feature)
    return None


def _feature_payload(feature: dict) -> dict:
    payload = deepcopy(feature)
    contract_ids = _UI_CONTRACTS.get(payload["id"])
    if contract_ids:
        payload.setdefault("ui", {})["contractIds"] = list(contract_ids)
    return payload
