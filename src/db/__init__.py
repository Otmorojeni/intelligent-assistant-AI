"""
Модуль базы данных PostgreSQL (SQLAlchemy 2.0 async + asyncpg).
"""
from src.db.database import get_db, init_db, async_session_factory, engine
from src.db.models import (
    Base,
    KnowledgeDocument,
    DocumentChunk,
    DefinedTerm,
    ApprovalRule,
    TemplateModule,
    ProjectCard,
    AuditLog,
)

__all__ = [
    "get_db",
    "init_db",
    "async_session_factory",
    "engine",
    "Base",
    "KnowledgeDocument",
    "DocumentChunk",
    "DefinedTerm",
    "ApprovalRule",
    "TemplateModule",
    "ProjectCard",
    "AuditLog",
]
