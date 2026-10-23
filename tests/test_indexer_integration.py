"""Integration tests for database indexing, seeding, fulltext search, and foreign keys."""

import asyncio
import sys
import pytest
from sqlalchemy import func, select

from src.db.database import async_session_factory, init_db
from src.core.indexer import (
    index_all_materials,
    lookup_defined_term,
    search_chunks_fulltext,
)
from src.db.models import (
    ApprovalRule,
    DefinedTerm,
    DocumentChunk,
    KnowledgeDocument,
    TemplateModule,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop with SelectorEventLoop on Windows for asyncpg/psycopg compatibility."""
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_full_database_seeding_and_counts():
    """Verify complete indexing workflow creates all expected records."""
    await init_db()
    async with async_session_factory() as session:
        stats = await index_all_materials(session, reset=True)

        assert stats["documents_count"] == 10
        assert stats["chunks_count"] == 302
        assert stats["terms_count"] == 29
        assert stats["approval_rules_count"] == 13
        assert stats["template_modules_count"] == 7


@pytest.mark.asyncio
async def test_tsvector_fulltext_search():
    """Verify PostgreSQL tsvector full-text search against Russian documents."""
    async with async_session_factory() as session:
        # Search for linguistic expertise
        matches = await search_chunks_fulltext(session, "лингвистическая экспертиза", top_k=3)
        assert len(matches) > 0
        assert any("лингвистическая экспертиза" in m["content"].lower() for m in matches)

        # Search for IT information systems
        matches_is = await search_chunks_fulltext(session, "ввод в эксплуатацию информационной системы", top_k=3)
        assert len(matches_is) > 0
        assert any("эксплуатаци" in m["content"].lower() for m in matches_is)

        # Search for objection table
        matches_table = await search_chunks_fulltext(session, "таблица замечаний", top_k=3)
        assert len(matches_table) > 0


@pytest.mark.asyncio
async def test_defined_terms_glossary():
    """Verify glossary lookup for canonical abbreviations."""
    async with async_session_factory() as session:
        term_iis = await lookup_defined_term(session, "ИИС ДО")
        assert term_iis is not None
        assert "Интегрированная" in term_iis["expansion"]

        term_lna = await lookup_defined_term(session, "лна")
        assert term_lna is not None
        assert "Локальный" in term_lna["expansion"]

        term_dsp = await lookup_defined_term(session, "ДСП")
        assert term_dsp is not None
        assert "служебного" in term_dsp["expansion"]

        # Non-existent term
        term_unknown = await lookup_defined_term(session, "НЕИЗВЕСТНЫЙ_ТЕРМИН_XYZ")
        assert term_unknown is None


@pytest.mark.asyncio
async def test_template_module_foreign_keys():
    """Verify that every TemplateModule is linked to a valid ApprovalRule."""
    async with async_session_factory() as session:
        res = await session.execute(select(TemplateModule))
        templates = res.scalars().all()
        assert len(templates) == 7

        for t in templates:
            assert t.default_rule_id is not None
            rule_res = await session.execute(
                select(ApprovalRule).where(ApprovalRule.id == t.default_rule_id)
            )
            rule = rule_res.scalar_one_or_none()
            assert rule is not None, f"Template {t.module_code} has broken default_rule_id foreign key"
