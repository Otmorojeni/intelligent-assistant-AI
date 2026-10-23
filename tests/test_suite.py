"""Comprehensive unit and integration test suite using standard library unittest."""

import asyncio
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy import func, select
from src.config import settings
from src.core.extractor import (
    extract_approval_matrix_data,
    extract_defined_terms,
    extract_guidelines_document,
    extract_pdf_instruction,
    extract_template_modules,
)
from src.core.indexer import (
    index_all_materials,
    lookup_defined_term,
    search_chunks_fulltext,
)
from src.db.database import async_session_factory, init_db
from src.db.models import (
    ApprovalRule,
    DefinedTerm,
    DocumentChunk,
    KnowledgeDocument,
    TemplateModule,
)


class TestExtractorUnit(unittest.TestCase):
    """Unit tests for extractor parsing of PDF, Word, terms, and templates."""

    def test_pdf_instruction_extraction(self):
        pdf_files = list(settings.MATERIALS_DIR.glob("*.pdf"))
        self.assertGreaterEqual(len(pdf_files), 1, "PDF instruction file not found")

        doc = extract_pdf_instruction(pdf_files[0])
        self.assertEqual(doc.doc_code, "OD-184")
        self.assertEqual(doc.doc_type, "instruction")
        self.assertEqual(doc.version, "1.0")
        self.assertGreaterEqual(len(doc.chunks), 250)

        watermark = "УЧЕБНЫЙ ПРИМЕР ДЛЯ ИТ-СОРЕВНОВАНИЙ"
        for c in doc.chunks:
            self.assertNotIn(watermark, c.content)
            self.assertGreater(len(c.content), 10)
            self.assertGreaterEqual(c.page_number, 1)

        clauses = {c.clause for c in doc.chunks}
        self.assertIn("1.1", clauses)
        self.assertIn("1.4", clauses)
        self.assertIn("10.6", clauses)
        self.assertIn("12.16", clauses)

    def test_defined_terms_extraction(self):
        pdf_files = list(settings.MATERIALS_DIR.glob("*.pdf"))
        doc = extract_pdf_instruction(pdf_files[0])
        terms = extract_defined_terms(doc)

        self.assertGreaterEqual(len(terms), 25)
        canonical_set = {t.canonical for t in terms}

        expected_canonicals = [
            "ИИС ДО", "ДОУ", "ЭД", "ЭКД", "ПД", "РК", "ЭП", "РБД",
            "ЛНА", "ДСП", "РО", "СП", "ЦА"
        ]
        for exp in expected_canonicals:
            self.assertIn(exp, canonical_set, f"Missing canonical term: {exp}")

        for t in terms:
            self.assertTrue(len(t.canonical) > 0)
            self.assertTrue(len(t.expansion) > 0)
            self.assertEqual(t.source_doc_code, "OD-184")
            self.assertIsNotNone(t.page_number)
            self.assertGreaterEqual(t.page_number, 1)

    def test_guidelines_extraction(self):
        guide_files = [
            f for f in settings.MATERIALS_DIR.iterdir()
            if "методические" in f.name.lower() and f.suffix == ".docx"
        ]
        self.assertGreaterEqual(len(guide_files), 1)

        doc = extract_guidelines_document(guide_files[0])
        self.assertEqual(doc.doc_code, "METHOD-GUIDELINES")
        self.assertGreaterEqual(len(doc.chunks), 20)

        clauses = {c.clause for c in doc.chunks}
        self.assertIn("1.1", clauses)
        self.assertIn("2.3", clauses)
        self.assertIn("3.3", clauses)
        self.assertIn("4.2", clauses)

    def test_approval_matrix_rules(self):
        matrix_files = [
            f for f in settings.MATERIALS_DIR.iterdir()
            if "матрица" in f.name.lower() and f.suffix == ".docx"
        ]
        self.assertGreaterEqual(len(matrix_files), 1)

        doc, rules = extract_approval_matrix_data(matrix_files[0])
        self.assertEqual(doc.doc_code, "APPROVAL-MATRIX")
        self.assertEqual(len(rules), 13)

        r1 = next(r for r in rules if r.rule_number == 1)
        self.assertTrue(r1.is_modular)
        self.assertTrue(r1.requires_legal)
        self.assertTrue(r1.requires_dou)
        self.assertTrue(r1.requires_hr)

        r3 = next(r for r in rules if r.rule_number == 3)
        self.assertEqual(r3.requires_infosec, "yes")

        r4 = next(r for r in rules if r.rule_number == 4)
        self.assertEqual(r4.requires_infosec, "yes")
        self.assertEqual(r4.requires_it, "yes")

        r8 = next(r for r in rules if r.rule_number == 8)
        self.assertEqual(r8.requires_it, "yes")

        r13 = next(r for r in rules if r.rule_number == 13)
        self.assertEqual(r13.requires_regional, "yes")

    def test_template_modules_schema(self):
        templates = extract_template_modules(settings.MATERIALS_DIR)
        self.assertEqual(len(templates), 7)

        module_codes = {t.module_code for t in templates}
        expected_codes = {
            "MOD-ORDER-IS",
            "MOD-ORDER-DOU",
            "MOD-ORDER-PROP",
            "MOD-ORDER-LNA",
            "MOD-DISP-AUDIT",
            "MOD-DISP-PROJECT",
            "MOD-DISP-WORKGROUP",
        }
        self.assertEqual(module_codes, expected_codes)

        for tm in templates:
            self.assertIn(tm.doc_kind, ("Приказ", "Распоряжение"))
            self.assertGreaterEqual(len(tm.fields_schema), 5)
            for f in tm.fields_schema:
                self.assertIn("name", f)
                self.assertIn("label", f)
                self.assertIn("type", f)
                self.assertIn("required", f)


class TestIndexerIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests connecting to PostgreSQL."""

    async def asyncSetUp(self):
        await init_db()

    async def test_full_seeding_and_counts(self):
        async with async_session_factory() as session:
            stats = await index_all_materials(session, reset=True)
            self.assertEqual(stats["documents_count"], 10)
            self.assertEqual(stats["chunks_count"], 302)
            self.assertEqual(stats["terms_count"], 29)
            self.assertEqual(stats["approval_rules_count"], 13)
            self.assertEqual(stats["template_modules_count"], 7)

    async def test_tsvector_fulltext_search(self):
        async with async_session_factory() as session:
            matches = await search_chunks_fulltext(session, "лингвистическая экспертиза", top_k=3)
            self.assertGreater(len(matches), 0)
            self.assertTrue(any("лингвистическая экспертиза" in m["content"].lower() for m in matches))

            matches_is = await search_chunks_fulltext(session, "ввод в эксплуатацию информационной системы", top_k=3)
            self.assertGreater(len(matches_is), 0)

            matches_table = await search_chunks_fulltext(session, "таблица замечаний", top_k=3)
            self.assertGreater(len(matches_table), 0)

    async def test_glossary_term_lookup(self):
        async with async_session_factory() as session:
            t_iis = await lookup_defined_term(session, "ИИС ДО")
            self.assertIsNotNone(t_iis)
            self.assertIn("Интегрированная", t_iis["expansion"])

            t_lna = await lookup_defined_term(session, "лна")
            self.assertIsNotNone(t_lna)
            self.assertIn("Локальный", t_lna["expansion"])

            t_dsp = await lookup_defined_term(session, "ДСП")
            self.assertIsNotNone(t_dsp)
            self.assertIn("служебного", t_dsp["expansion"])

            t_unknown = await lookup_defined_term(session, "НЕИЗВЕСТНО")
            self.assertIsNone(t_unknown)

    async def test_template_foreign_keys(self):
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
                self.assertIsNotNone(rule, f"Template {t.module_code} has invalid rule reference")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    unittest.main()
