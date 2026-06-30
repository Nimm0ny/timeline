from pydantic import BaseModel, Field


class EventItemIn(BaseModel):
    tag: str
    text: str


class AttachmentIn(BaseModel):
    id: int | None = None
    name: str
    filename: str
    mimeType: str | None = None


class OptionDef(BaseModel):
    id: str
    label: str = ""
    color: str = ""


class ColumnDef(BaseModel):
    key: str
    label: str
    # text | number | date | checkbox | url | email | phone | select | multiselect
    type: str = "text"
    width: int = 96
    order: int = 0
    visible: bool = True
    options: list[OptionDef] = Field(default_factory=list)


class TimelineEventIn(BaseModel):
    id: int | None = None
    # entry requires a concrete date; mindmap may omit it (undated canvas note).
    dateYear: int | None = None
    dateMonth: int | None = None
    dateDay: int | None = None
    headline: str
    era: str = ""
    # Note kind: "entry" (markdown body) or "mindmap" (tree in bodyJson).
    noteType: str = "entry"
    bodyMarkdown: str = ""
    # Structured body for non-entry notes (e.g. mindmap tree); None for entries.
    bodyJson: dict | list | None = None
    attachments: list[AttachmentIn] = Field(default_factory=list)
    relatedEventIds: list[int] = Field(default_factory=list)
    # Property values: free fields -> str, single-select -> str (option id),
    # multi-select -> list[str] (option ids). Type/tags live here too.
    extra: dict[str, str | list[str]] = Field(default_factory=dict)
    items: list[EventItemIn] = Field(default_factory=list)
    image: str | None = None


class TopicCreateIn(BaseModel):
    name: str


class TopicMetaUpdateIn(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    displayStyle: str | None = None
    columns: list[ColumnDef] | None = None


class TopicOut(BaseModel):
    id: int
    name: str
    title: str
    subtitle: str
    columns: list[dict] = Field(default_factory=list)
    displayStyle: str = "timeline"
    # Enabled display styles for this notebook's entries, derived from data
    # capability (see services.timeline.topic_capabilities). FE/BE SSOT.
    capabilities: list[str] = Field(default_factory=list)
    capabilitySignals: dict | None = None
    updatedAt: str | None = None
    eventCount: int | None = None
    minDateKey: int | None = None
    maxDateKey: int | None = None
    minDate: str | None = None
    maxDate: str | None = None


class ImageUploadOut(BaseModel):
    id: int
    filename: str
