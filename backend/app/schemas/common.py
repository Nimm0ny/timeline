from pydantic import BaseModel, Field


class EventItemIn(BaseModel):
    tag: str
    text: str


class AttachmentIn(BaseModel):
    id: int | None = None
    name: str
    filename: str
    mimeType: str | None = None


class ColumnDef(BaseModel):
    key: str
    label: str
    type: str = "text"
    width: int = 96
    order: int = 0
    visible: bool = True


class TimelineEventIn(BaseModel):
    id: int | None = None
    dateYear: int
    dateMonth: int
    dateDay: int
    headline: str
    era: str
    bodyMarkdown: str = ""
    tags: list[str] = Field(default_factory=list)
    attachments: list[AttachmentIn] = Field(default_factory=list)
    relatedEventIds: list[int] = Field(default_factory=list)
    extra: dict[str, str] = Field(default_factory=dict)
    items: list[EventItemIn]
    image: str | None = None


class TopicCreateIn(BaseModel):
    name: str


class TopicMetaUpdateIn(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    columns: list[ColumnDef] | None = None


class TopicOut(BaseModel):
    id: int
    name: str
    title: str
    subtitle: str
    columns: list[dict] = Field(default_factory=list)
    updatedAt: str | None = None
    eventCount: int | None = None
    minDateKey: int | None = None
    maxDateKey: int | None = None
    minDate: str | None = None
    maxDate: str | None = None


class ImageUploadOut(BaseModel):
    id: int
    filename: str
