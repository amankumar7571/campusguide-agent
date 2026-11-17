"""Database models (SQLAlchemy).

Same schema on SQLite (local default) and Postgres (deploy target).
Vectors are NOT stored as a pgvector column here: the dense index is a
TF-IDF model rebuilt from the chunk table at ingest/startup (see
retrieval.py), so the schema is portable. For a Postgres deployment, run
the optional migration in README (adds a pgvector `embedding` column and
an ivfflat index) — the app works without it.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DATABASE_URL

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(512), nullable=False)
    role = Column(String(20), nullable=False, default="student")  # student|admin
    created_at = Column(DateTime, default=_now)


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    is_sample = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    chunks = relationship("Chunk", back_populates="document",
                          cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    section = Column(String(255), nullable=False, default="")
    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    document = relationship("Document", back_populates="chunks")


class PlacementStat(Base):
    __tablename__ = "placement_stats"
    id = Column(Integer, primary_key=True)
    company = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False)
    role = Column(String(255), nullable=False)
    offers = Column(Integer, nullable=False, default=0)
    ctc_lpa = Column(Float, nullable=True)
    is_sample = Column(Boolean, default=True)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    vote = Column(String(10), nullable=False)  # up|down
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    kind = Column(String(50), nullable=False)  # ingest|eval
    status = Column(String(20), nullable=False, default="pending")
    rows_processed = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    finished_at = Column(DateTime, nullable=True)


class Draft(Base):
    __tablename__ = "drafts"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    sources = Column(Text, nullable=True)  # JSON list of citations
    status = Column(String(20), nullable=False, default="pending_approval")
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_now)


def get_engine(url: str = DATABASE_URL):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
