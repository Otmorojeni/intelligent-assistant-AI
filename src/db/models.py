import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Computed,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class KnowledgeDocument(Base):
    """Нормативные документы и регламенты (с версионностью)."""
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_code: Mapped[str] = mapped_column(String(64), index=True)  # OD-184, APPROVAL_MATRIX, etc.
    title: Mapped[str] = mapped_column(String(512))
    doc_type: Mapped[str] = mapped_column(String(64), index=True)  # instruction, matrix, guideline, template
    version: Mapped[str] = mapped_column(String(32), default="1.0", index=True)
    access_level: Mapped[str] = mapped_column(String(32), default="public", index=True)  # public, dsp
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    file_name: Mapped[str] = mapped_column(String(256))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """Поисковые фрагменты нормативных документов (с главами, пунктами и страницами)."""
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    chapter: Mapped[str] = mapped_column(String(256), index=True)  # Глава 4. Порядок подготовки...
    clause: Mapped[str] = mapped_column(String(128), index=True)   # Пункт 4.2.3
    page_number: Mapped[int] = mapped_column(Integer, index=True)  # Номер страницы
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Полнотекстовый вектор русского языка
    search_vector = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('russian', coalesce(chapter, '') || ' ' || coalesce(clause, '') || ' ' || coalesce(content, ''))", persisted=True)
    )

    document: Mapped["KnowledgeDocument"] = relationship("KnowledgeDocument", back_populates="chunks")

    __table_args__ = (
        Index("idx_doc_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index("idx_doc_chunks_content_trgm", "content", postgresql_using="gin", postgresql_ops={"content": "gin_trgm_ops"}),
        Index("idx_doc_chunks_clause_trgm", "clause", postgresql_using="gin", postgresql_ops={"clause": "gin_trgm_ops"}),
    )


class DefinedTerm(Base):
    """Глоссарий терминов и сокращений ДОУ Банка России."""
    __tablename__ = "defined_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical: Mapped[str] = mapped_column(String(64), index=True)  # ИИС ДО, ЛНА, ДСП, РО, СП
    expansion: Mapped[str] = mapped_column(String(256))             # Интегрированная информационная система...
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_doc_code: Mapped[str] = mapped_column(String(64), default="OD-184")
    clause: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class ApprovalRule(Base):
    """Правила Матрицы обязательного визирования."""
    __tablename__ = "approval_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(64), default="internal")  # internal, external
    doc_type_name: Mapped[str] = mapped_column(String(512))
    is_modular: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_legal: Mapped[bool] = mapped_column(Boolean, default=True)   # Юр. подразделение
    requires_dou: Mapped[bool] = mapped_column(Boolean, default=True)     # Департамент ДОУ
    requires_hr: Mapped[bool] = mapped_column(Boolean, default=False)     # Кадровое подразделение
    requires_infosec: Mapped[str] = mapped_column(String(128), default="no") # yes, no, conditional
    requires_it: Mapped[str] = mapped_column(String(128), default="no")      # yes, no, conditional
    requires_regional: Mapped[str] = mapped_column(String(128), default="no")
    condition_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signatory: Mapped[str] = mapped_column(String(256), default="Председатель / Заместитель Председателя")
    extra_info: Mapped[dict] = mapped_column(JSONB, default=dict)


class TemplateModule(Base):
    """Реестр 7 утвержденных модулей документов."""
    __tablename__ = "template_modules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    doc_kind: Mapped[str] = mapped_column(String(64))  # Приказ, Распоряжение
    title: Mapped[str] = mapped_column(String(256))
    reg_number: Mapped[str] = mapped_column(String(64), default="УТВ-01")
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    file_name: Mapped[str] = mapped_column(String(256))
    fields_schema: Mapped[list] = mapped_column(JSONB, default=list)  # Спецификация полей ввода
    default_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_rules.id", ondelete="SET NULL"), nullable=True
    )

    projects: Mapped[List["ProjectCard"]] = relationship("ProjectCard", back_populates="template")


class ProjectCard(Base):
    """Регистрационные карточки созданных проектов приказов/распоряжений."""
    __tablename__ = "project_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("template_modules.id"), index=True
    )
    project_title: Mapped[str] = mapped_column(String(512))
    executor_name: Mapped[str] = mapped_column(String(128))
    executor_department: Mapped[str] = mapped_column(String(256))
    signatory_name: Mapped[str] = mapped_column(String(128))
    access_level: Mapped[str] = mapped_column(String(32), default="public")
    note_text: Mapped[str] = mapped_column(Text)  # Регламентированная фраза по п. 2.3
    filled_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    approval_route: Mapped[list] = mapped_column(JSONB, default=list)
    generated_file_name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    template: Mapped["TemplateModule"] = relationship("TemplateModule", back_populates="projects")


class AuditLog(Base):
    """Журнал аудита действий и предотвращения несанкционированного доступа (RBAC)."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    user_role: Mapped[str] = mapped_column(String(64), index=True)  # employee, dou_specialist, security_auditor
    user_name: Mapped[str] = mapped_column(String(128), default="Пользователь")
    action_type: Mapped[str] = mapped_column(String(64), index=True)  # query, generate_doc, upload_version, access_denied
    query_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success", index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
