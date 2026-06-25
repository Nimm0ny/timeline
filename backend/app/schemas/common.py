from pydantic import BaseModel, ConfigDict, Field


class EventItemIn(BaseModel):
    tag: str
    text: str


class AttachmentIn(BaseModel):
    id: int | None = None
    name: str
    filename: str
    mimeType: str | None = None


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
    items: list[EventItemIn]
    image: str | None = None


class TopicCreateIn(BaseModel):
    name: str


class TopicMetaUpdateIn(BaseModel):
    title: str | None = None
    subtitle: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
    is_admin: bool


class LoginOut(BaseModel):
    accessToken: str
    user: UserOut


class TopicOut(BaseModel):
    id: int
    name: str
    title: str
    subtitle: str
    updatedAt: str | None = None
    eventCount: int | None = None
    minDateKey: int | None = None
    maxDateKey: int | None = None
    minDate: str | None = None
    maxDate: str | None = None


class ImageUploadOut(BaseModel):
    id: int
    filename: str
