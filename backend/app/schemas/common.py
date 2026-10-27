from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class NoteItemIn(ContractModel):
    tag: str = "note"
    text: str


class AttachmentIn(ContractModel):
    id: int | None = None
    name: str
    filename: str
    mimeType: str | None = None
    thumbFilename: str | None = None
    originalFilename: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int | None = None


class OptionDef(ContractModel):
    id: str
    label: str = ""
    color: str = ""


class ColumnDef(ContractModel):
    key: str
    label: str
    type: str = "text"
    width: int = 96
    order: int = 0
    visible: bool = True
    options: list[OptionDef] = Field(default_factory=list)


class NoteWriteIn(ContractModel):
    id: int | None = None
    dateYear: int | None = None
    dateMonth: int | None = None
    dateDay: int | None = None
    headline: str
    era: str = ""
    bodyMarkdown: str = ""
    attachments: list[AttachmentIn] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    items: list[NoteItemIn] = Field(default_factory=list)
    image: str | None = None
    favorite: bool | None = None
    deletedAt: str | None = None


class NoteStatePatchIn(ContractModel):
    favorite: bool | None = None
    deletedAt: str | None = None


NoteUpdateIn = NoteWriteIn | NoteStatePatchIn
NoteIn = NoteWriteIn


class TopicCreateIn(ContractModel):
    name: str
    bookshelfId: int | None = None


class SortLevel(ContractModel):
    field: str
    dir: int


class TopicMetaUpdateIn(ContractModel):
    title: str | None = None
    subtitle: str | None = None
    bookshelfId: int | None = None
    displayStyle: str | None = None
    containerType: str | None = None
    sort: list[SortLevel] | None = None
    groupBy: str | None = None
    columns: list[ColumnDef] | None = None


class BookshelfCreateIn(ContractModel):
    name: str
    title: str | None = None


class BookshelfUpdateIn(ContractModel):
    name: str | None = None
    title: str | None = None


class MediaConfigIn(ContractModel):
    compress: bool | None = None
    keepOriginal: bool | None = None
    quality: int | None = None
    maxEdge: int | None = None
    thumbEdge: int | None = None


class AppConfigUpdateIn(BaseModel):
    brandName: str | None = None
    heroTitle: str | None = None
    heroSubtitle: str | None = None
    brandFontSize: str | None = None
    brandColor: str | None = None
    titleFontSize: str | None = None
    titleColor: str | None = None
    subtitleFontSize: str | None = None
    subtitleColor: str | None = None
    layout: str | None = None
    navPosition: str | None = None
    detailPosition: str | None = None
    favoritesSort: list[SortLevel] | None = None
    sidebarSort: str | None = None
    media: MediaConfigIn | None = None

    model_config = ConfigDict(extra="allow")


class AppConfigOut(ResponseModel):
    brandName: str | None = None
    heroTitle: str | None = None
    heroSubtitle: str | None = None
    brandFontSize: str | None = None
    brandColor: str | None = None
    titleFontSize: str | None = None
    titleColor: str | None = None
    subtitleFontSize: str | None = None
    subtitleColor: str | None = None
    layout: str | None = None
    navPosition: str | None = None
    detailPosition: str | None = None
    favoritesSort: list[dict[str, Any]] = Field(default_factory=list)
    sidebarSort: str | None = None
    media: dict[str, Any] = Field(default_factory=dict)


class OkOut(ResponseModel):
    ok: bool


class TopicOut(ResponseModel):
    id: int
    name: str
    title: str
    subtitle: str
    bookshelfId: int | None = None
    bookshelfName: str | None = None
    bookshelfTitle: str | None = None
    columns: list[dict[str, Any]] = Field(default_factory=list)
    displayStyle: str = "timeline"
    containerType: str = "notebook"
    views: list[str] = Field(default_factory=list)
    defaultView: str | None = None
    sort: list[dict[str, Any]] = Field(default_factory=list)
    groupBy: str = "era"
    capabilities: list[str] = Field(default_factory=list)
    capabilitySignals: dict[str, Any] | None = None
    updatedAt: str | None = None
    noteCount: int | None = None
    minDateKey: int | None = None
    maxDateKey: int | None = None
    minDate: str | None = None
    maxDate: str | None = None


class BookshelfOut(ResponseModel):
    id: int | None = None
    name: str
    title: str
    createdAt: str | None = None
    updatedAt: str | None = None
    topicCount: int = 0
    noteCount: int = 0


class EraCount(ResponseModel):
    era: str
    count: int


class BookshelfTopicEntry(ResponseModel):
    topic: TopicOut
    eras: list[EraCount] = Field(default_factory=list)


class BookshelfTreeItem(BookshelfOut):
    topics: list[BookshelfTopicEntry] = Field(default_factory=list)


class NoteDateParts(ResponseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None


class AttachmentOut(ResponseModel):
    id: int | None = None
    name: str
    filename: str
    thumbFilename: str | None = None
    originalFilename: str | None = None
    mimeType: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    url: str
    thumbUrl: str | None = None
    originalUrl: str | None = None
    imageUrl: str | None = None


class NoteItemOut(ResponseModel):
    tag: str
    text: str


class NoteOut(ResponseModel):
    id: int
    topicId: int
    nodeType: str = "note"
    hasDate: bool
    dateKey: int | None = None
    isoDate: str | None = None
    dateParts: NoteDateParts
    displayLabel: str
    sortKey: float
    headline: str
    legacyYear: str
    era: str
    image: str | None = None
    imageUrl: str | None = None
    thumbUrl: str | None = None
    bodyMarkdown: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)
    attachments: list[AttachmentOut] = Field(default_factory=list)
    createdAt: str
    updatedAt: str
    favorite: bool = False
    favoriteAt: str | None = None
    deletedAt: str | None = None
    items: list[NoteItemOut] = Field(default_factory=list)


class NoteListItem(ResponseModel):
    id: int
    topicId: int
    nodeType: Literal["note"] = "note"
    hasDate: bool
    dateKey: int | None = None
    isoDate: str | None = None
    dateParts: NoteDateParts
    displayLabel: str
    sortKey: float
    headline: str
    legacyYear: str
    era: str
    image: str | None = None
    imageUrl: str | None = None
    thumbUrl: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    favorite: bool = False
    favoriteAt: str | None = None
    deletedAt: str | None = None
    createdAt: str
    updatedAt: str
    preview: str = ""
    searchText: str = ""
    attachmentCount: int = 0


class NoteIndexItem(ResponseModel):
    id: int
    topicId: int
    hasDate: bool
    dateKey: int | None = None
    isoDate: str | None = None
    dateParts: NoteDateParts
    displayLabel: str
    headline: str
    era: str
    image: str | None = None
    imageUrl: str | None = None
    thumbUrl: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    favorite: bool = False
    favoriteAt: str | None = None
    deletedAt: str | None = None
    createdAt: str
    updatedAt: str
    preview: str = ""
    searchText: str = ""
    attachmentCount: int = 0


class BoundsOut(ResponseModel):
    noteCount: int = 0
    minDateKey: int | None = None
    maxDateKey: int | None = None
    minDate: str | None = None
    maxDate: str | None = None
    hasImage: bool | None = None
    supportedZoomLevels: list[Any] = Field(default_factory=list)


class NoteRangeOut(ResponseModel):
    from_: int | None = Field(None, alias="from")
    to: int | None = None
    cursor: int | None = None
    limit: int | None = None


class NotePageOut(ResponseModel):
    items: list[NoteListItem]
    bounds: BoundsOut
    range: NoteRangeOut
    hasMore: bool
    nextCursor: str | None = None


class NoteIndexOut(ResponseModel):
    topics: list[TopicOut]
    notes: list[NoteIndexItem]


class NoteSearchItem(ResponseModel):
    id: int
    topicId: int
    headline: str
    snippet: str
    dateKey: int | None = None
    isoDate: str | None = None
    rank: float


class SummaryItemOut(ResponseModel):
    id: str
    nodeType: Literal["summary"]
    groupBy: str
    bucketKey: int
    displayLabel: str
    headline: str
    sortKey: int
    dateKey: int
    rangeStartKey: int
    rangeEndKey: int
    rangeStartDate: str
    rangeEndDate: str
    noteCount: int
    era: str
    image: str | None = None
    items: list[NoteItemOut] = Field(default_factory=list)


class SummaryRangeOut(ResponseModel):
    from_: int | None = Field(None, alias="from")
    to: int | None = None


class TopicSummaryOut(ResponseModel):
    items: list[SummaryItemOut]
    bounds: BoundsOut
    groupBy: str
    range: SummaryRangeOut


class SearchResult(ResponseModel):
    id: int
    topicId: int
    headline: str
    snippet: str
    dateKey: int | None = None
    isoDate: str | None = None
    rank: float


class DeleteOut(ResponseModel):
    ok: bool
    deletedAt: str | None = None
    updatedAt: str | None = None


class ImportOut(ResponseModel):
    ok: bool
    count: int


class TopicExportOut(ResponseModel):
    schemaVersion: int
    title: str
    subtitle: str
    columns: list[dict[str, Any]]
    notes: list[NoteOut]


class ImageUploadOut(ResponseModel):
    id: int
    filename: str
    originalName: str
    mimeType: str | None = None
    url: str
    imageUrl: str | None = None


class RuntimeIdentityOut(ResponseModel):
    databaseIdentity: str


class ApiError(ResponseModel):
    code: str
    message: str
    nextAction: str
    details: Any = None


class ApiErrorOut(ResponseModel):
    error: ApiError


class FeatureUiOut(ResponseModel):
    route: str | None = "/"
    entryPoint: str
    hasWebEntry: bool = True
    contractIds: list[str] = Field(default_factory=list)


class FeatureOperationOut(ResponseModel):
    operationId: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    readOnly: bool = False
    lifecycle: Literal["active", "compatibility", "deprecated"] = "active"
    clientMethod: str | None = None
    cliCommand: str | None = None
    requestSchema: str | None = None
    querySchema: str | None = None
    responseSchema: str | None = None
    requestHeaders: list[str] = Field(default_factory=list)
    contentType: str = "application/json"


class FeatureScenarioStepOut(ResponseModel):
    id: str
    operationId: str
    assertions: list[str] = Field(default_factory=list)
    persistence: str = "read-only"


class FeatureScenarioOut(ResponseModel):
    id: str
    title: str
    summary: str
    inputSchema: str
    readOnly: bool = True
    preconditions: list[str] = Field(default_factory=list)
    steps: list[FeatureScenarioStepOut] = Field(default_factory=list)
    cleanup: str = "No cleanup is required."


class FeatureOut(ResponseModel):
    id: str
    title: str
    summary: str
    ui: FeatureUiOut
    api: list[FeatureOperationOut]
    stateOwner: str
    dataScope: str
    preconditions: list[str]
    permissions: list[str]
    persistedResult: str
    failureRecovery: list[str]
    operationIdentity: str | None = None
    scenarios: list[FeatureScenarioOut]


class FeatureMapOut(ResponseModel):
    version: str
    features: list[FeatureOut]


class NoteReadScenarioInput(ContractModel):
    noteId: int = Field(gt=0)


class EmptyInput(ContractModel):
    pass


class NoteListQuery(ContractModel):
    limit: int = Field(100, ge=1, le=500)
    fromDate: str | None = Field(None, alias="from")
    toDate: str | None = Field(None, alias="to")
    cursor: str | None = None
    direction: int = Field(1, alias="dir", ge=-1, le=1)


class NoteListInput(NoteListQuery):
    topicId: int = Field(gt=0)


class NoteListScenarioInput(NoteListInput):
    containsNoteId: int = Field(gt=0)


class TopicReadInput(ContractModel):
    topicId: int = Field(gt=0)


class NoteSearchQuery(ContractModel):
    query: str = Field("", alias="q")
    limit: int = Field(20, ge=1, le=50)


class NoteSearchInput(NoteSearchQuery):
    query: str = Field(min_length=1, alias="q")


class NoteSearchScenarioInput(NoteSearchInput):
    expectedNoteId: int = Field(gt=0)


class TopicSummaryQuery(ContractModel):
    groupBy: Literal["year", "month"]
    fromDate: str | None = Field(None, alias="from")
    toDate: str | None = Field(None, alias="to")


class TopicExportQuery(ContractModel):
    fromDate: str | None = Field(None, alias="from")
    toDate: str | None = Field(None, alias="to")


def model_payload(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)
