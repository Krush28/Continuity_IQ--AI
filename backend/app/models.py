from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="member")  # manager | member | incoming
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    members = relationship("ProjectMember", cascade="all, delete-orphan", back_populates="project")


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_role: Mapped[str] = mapped_column(String(20), default="member")  # manager | member | incoming
    project = relationship("Project", back_populates="members")
    user = relationship("User")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded | processed | failed
    error: Mapped[str] = mapped_column(Text, default="")
    extracted_by: Mapped[str] = mapped_column(String(40), default="")
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    chunks = relationship("Chunk", cascade="all, delete-orphan", back_populates="document")


class Chunk(Base):
    """A located piece of source text: a page/section paragraph the records point back to."""
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text)
    document = relationship("Document", back_populates="chunks")


class Record(Base):
    """A structured piece of project knowledge, always linked to its source."""
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True)
    # task | decision | issue | dependency | contact | note
    category: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(500))
    detail: Mapped[str] = mapped_column(Text, default="")
    # tasks: completed | ongoing | pending ; issues: open | resolved ; else ""
    status: Mapped[str] = mapped_column(String(20), default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    priority: Mapped[str] = mapped_column(String(20), default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_location: Mapped[str] = mapped_column(String(255), default="")
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    extracted_by: Mapped[str] = mapped_column(String(20), default="rules")  # rules | ai | manual | agent
    review_state: Mapped[str] = mapped_column(String(20), default="unreviewed")  # unreviewed | approved | rejected
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class GapQuestion(Base):
    """A question the Gap Auditor agent raises for the outgoing member before handover."""
    __tablename__ = "gap_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    record_id: Mapped[int | None] = mapped_column(ForeignKey("records.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), default="missing_info")
    question: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # high | medium | low
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | answered | dismissed
    answered_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Handover(Base):
    __tablename__ = "handovers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    outgoing_name: Mapped[str] = mapped_column(String(120), default="")
    incoming_name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    readiness: Mapped[int] = mapped_column(Integer, default=0)
    generated_by: Mapped[str] = mapped_column(String(40), default="templates")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manager_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentRun(Base):
    """Every agent run is logged with its full step-by-step trace for transparency."""
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(20), default="running")
    input: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    started_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    user_name: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
