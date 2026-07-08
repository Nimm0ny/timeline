from collections.abc import Generator
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.api.bookshelves import router as bookshelves_router
from backend.app.api.topics import router as topics_router
from backend.app.db.session import Base, get_db
from backend.app.models.entities import Bookshelf, NoteItem, Note, Topic
from backend.app.services.date_utils import build_display_label, date_key_to_parts, make_date_key
from backend.app.services.timeline import backfill_note_text_fields, rebuild_topic_read_models


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(bookshelves_router)
    app.include_router(topics_router)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def seeded_topic(db_session: Session) -> Topic:
    bookshelf = Bookshelf(name="default", title="编年")
    db_session.add(bookshelf)
    db_session.flush()

    topic = Topic(name="history", title="History", subtitle="Daily history", bookshelf_id=bookshelf.id)
    db_session.add(topic)
    db_session.flush()

    rows = [
        (make_date_key(1840, 1, 1), "Opium War Begins", "Modern China", [("war", "Conflict begins.")]),
        (make_date_key(1840, 1, 2), "Second Entry", "Modern China", [("politics", "Diplomatic fallout.")]),
        (make_date_key(1841, 2, 1), "Another Year", "Modern China", [("war", "Escalation.")]),
        (make_date_key(1841, 2, 15), "Mid Month", "Modern China", [("economy", "Trade pressure.")]),
    ]

    for date_key, headline, era, items in rows:
        year, month, day = date_key_to_parts(date_key)
        event = Note(
            topic_id=topic.id,
            year=build_display_label(year, month, day, headline),
            sort_key=float(date_key),
            date_key=date_key,
            date_year=year,
            date_month=month,
            date_day=day,
            headline=headline,
            era=era,
        )
        db_session.add(event)
        db_session.flush()
        for index, item in enumerate(items):
            db_session.add(NoteItem(note_id=event.id, tag=item[0], text=item[1], sort_order=index))

    backfill_note_text_fields(db_session)
    rebuild_topic_read_models(db_session)
    db_session.commit()
    db_session.refresh(topic)
    return topic
