"""Integration tests for database indexing, seeding, fulltext search, and foreign keys."""

import asyncio
from pathlib import Path
import sys
import unittest

from sqlalchemy import func, select

from src.core.indexer import (
    index_all_materials,
    lookup_defined_term,
    search_chunks_fulltext,
)
from src.db.database import async_session_factory, engine, init_db
from src.db.models import (
    ApprovalRule,
    DefinedTerm,
    DocumentChunk,
    KnowledgeDocument,
    TemplateModule,
)


class TestIndexerIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests connecting to live PostgreSQL container."""

    async def asyncSetUp(self):
        await init_db()
        async with async_session_factory() as session:
            count = (await session.execute(select(func.count(DefinedTerm.id)))).scalar()
            if not count:
                await index_all_materials(session, reset=False)

    async def test_full_database_seeding_and_counts(self):
        """Verify complete indexing workflow creates all expected records."""
        async with async_session_factory() as session:
            stats = await index_all_materials(session, reset=True)

            self.assertEqual(stats["documents_count"], 10)
            self.assertEqual(stats["chunks_count"], 299)
            self.assertEqual(stats["terms_count"], 30)
            self.assertEqual(stats["approval_rules_count"], 13)
            self.assertEqual(stats["template_modules_count"], 7)

    async def test_tsvector_fulltext_search(self):
        """Verify PostgreSQL tsvector full-text search against Russian documents."""
        async with async_session_factory() as session:
            # 1. Search for linguistic expertise
            matches = await search_chunks_fulltext(session, "лингвистическая экспертиза", top_k=3)
            self.assertGreater(len(matches), 0)
            self.assertTrue(any("лингвистическая экспертиза" in m["content"].lower() for m in matches))

            # 2. Search for IT information systems
            matches_is = await search_chunks_fulltext(session, "ввод в эксплуатацию информационной системы", top_k=3)
            self.assertGreater(len(matches_is), 0)
            self.assertTrue(any("эксплуатаци" in m["content"].lower() for m in matches_is))

            # 3. Search for objection table (Appendix 1)
            matches_table = await search_chunks_fulltext(session, "таблица замечаний", top_k=3)
            self.assertGreater(len(matches_table), 0)

            # 4. Search by clause identifier directly ("10.6" and "п. 4.1.3")
            matches_clause = await search_chunks_fulltext(session, "п. 4.1.3", top_k=3)
            self.assertGreater(len(matches_clause), 0)
            self.assertEqual(matches_clause[0]["clause"], "4.1.3")

            # 5. Search by template code and reg_number
            matches_tmpl = await search_chunks_fulltext(session, "УТВ-01", top_k=3)
            self.assertGreater(len(matches_tmpl), 0)
            self.assertEqual(matches_tmpl[0]["doc_code"], "MOD-ORDER-IS")

            # 6. Empty search query
            empty_matches = await search_chunks_fulltext(session, "   ")
            self.assertEqual(len(empty_matches), 0)

    async def test_defined_terms_glossary(self):
        """Verify glossary lookup for canonical abbreviations and expansions."""
        async with async_session_factory() as session:
            # Exact canonical
            term_iis = await lookup_defined_term(session, "ИИС ДО")
            self.assertIsNotNone(term_iis)
            self.assertIn("Интегрированная", term_iis["expansion"])

            # Lowercase canonical
            term_lna = await lookup_defined_term(session, "лна")
            self.assertIsNotNone(term_lna)
            self.assertIn("Локальный", term_lna["expansion"])

            # Dских
            term_dsp = await lookup_defined_term(session, "ДСП")
            self.assertIsNotNone(term_dsp)
            self.assertIn("служебного", term_dsp["expansion"])

            # SED
            term_sed = await lookup_defined_term(session, "СЭД")
            self.assertIsNotNone(term_sed)
            self.assertIn("электронного", term_sed["expansion"])

            # Expansion query
            term_by_exp = await lookup_defined_term(session, "Локальный нормативный акт")
            self.assertIsNotNone(term_by_exp)
            self.assertEqual(term_by_exp["canonical"], "ЛНА")

            # Non-existent term
            term_unknown = await lookup_defined_term(session, "НЕИЗВЕСТНЫЙ_ТЕРМИН_XYZ")
            self.assertIsNone(term_unknown)

            # Empty term
            term_empty = await lookup_defined_term(session, "   ")
            self.assertIsNone(term_empty)

    async def test_template_module_foreign_keys_and_metadata(self):
        """Verify that every TemplateModule is linked to a valid ApprovalRule and has real file metadata."""
        async with async_session_factory() as session:
            res = await session.execute(select(TemplateModule))
            templates = res.scalars().all()
            self.assertEqual(len(templates), 7)

            for t in templates:
                self.assertIsNotNone(t.default_rule_id)
                rule_res = await session.execute(
                    select(ApprovalRule).where(ApprovalRule.id == t.default_rule_id)
                )
                rule = rule_res.scalar_one_or_none()
                self.assertIsNotNone(rule, f"Template {t.module_code} has broken default_rule_id foreign key")

            # Verify knowledge_documents records for templates have real file_size and sha256
            doc_res = await session.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.doc_type == "template")
            )
            tmpl_docs = doc_res.scalars().all()
            self.assertEqual(len(tmpl_docs), 7)
            for td in tmpl_docs:
                self.assertGreater(td.file_size, 0, f"Template doc {td.doc_code} has zero file_size")
                self.assertIsNotNone(td.sha256)
                self.assertGreater(len(td.sha256), 32, f"Template doc {td.doc_code} has invalid sha256")


if __name__ == "__main__":
    unittest.main()
