"""Unit and integration tests for hybrid retrieval engine (src/core/retriever.py).

Verifies ts_rank_cd full-text search, pg_trgm trigram similarity, clause number boosting,
defined corporate terms detection, RBAC access-level filtering, and relevance normalization.
"""

import asyncio
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.core.retriever import (
    calculate_relevance_pct,
    detect_query_terms,
    extract_clause_identifiers,
    get_allowed_access_levels,
    retrieve_chunks,
)
from src.db.database import async_session_factory, engine
from src.schemas.api_models import DetectedTermRef, SourceRef


class TestRetriever(unittest.IsolatedAsyncioTestCase):
    """Test suite for hybrid retriever with live PostgreSQL connection."""

    @classmethod
    async def asyncTearDownClass(cls):
        await engine.dispose()

    def test_extract_clause_identifiers(self):
        """Verify regex extraction of single and multi-level clause identifiers."""
        self.assertEqual(extract_clause_identifiers("п. 4.1.3"), ["4.1.3"])
        self.assertEqual(extract_clause_identifiers("пункт 10.6 Инструкции"), ["10.6"])
        self.assertEqual(extract_clause_identifiers("Раздел 4"), ["4"])
        self.assertIn("9.16.1", extract_clause_identifiers("согласно п. 9.16.1 и п. 2.3"))
        self.assertIn("2.3", extract_clause_identifiers("согласно п. 9.16.1 и п. 2.3"))
        self.assertEqual(extract_clause_identifiers("пп. 4.1.3, 4.1.4"), ["4.1.3", "4.1.4"])
        self.assertEqual(extract_clause_identifiers("подпункт 2.5"), ["2.5"])
        self.assertEqual(extract_clause_identifiers("согласно п. 4.1.3."), ["4.1.3"])
        self.assertEqual(extract_clause_identifiers("просто текст без пунктов"), [])
        self.assertEqual(extract_clause_identifiers(""), [])

    def test_get_allowed_access_levels(self):
        """Verify RBAC access level mapping based on principle of least privilege."""
        self.assertEqual(get_allowed_access_levels("employee"), ["public"])
        self.assertEqual(get_allowed_access_levels("user"), ["public"])
        self.assertEqual(get_allowed_access_levels("unknown_role"), ["public"])
        self.assertEqual(get_allowed_access_levels(""), ["public"])

        self.assertEqual(get_allowed_access_levels("dou_specialist"), ["dsp", "public"])
        self.assertEqual(get_allowed_access_levels("security_auditor"), ["dsp", "public"])
        self.assertEqual(get_allowed_access_levels("admin"), ["confidential", "dsp", "public", "secret"])

    def test_clause_segment_isolation_no_false_positive(self):
        """Regression test: verify that clause candidate '1' does NOT falsely boost clause '10.6'."""
        score_10_6 = calculate_relevance_pct(
            ts_rank_exact=0.0,
            ts_rank_or=0.0,
            clause_sim=0.0,
            content_sim=0.0,
            chunk_clause="10.6",
            clause_candidates=["1"],
            detected_terms=[],
            chunk_content="Текст документа о других вопросах",
            doc_code="OD-184",
            query="п. 1",
        )
        # Should NOT get clause boost (must be 0.0)
        self.assertEqual(score_10_6, 0.0)

    def test_acronym_word_boundary_isolation(self):
        """Regression test: verify short acronym 'ИС' does not match random words like 'инструкция'."""
        score_unrelated = calculate_relevance_pct(
            ts_rank_exact=0.0,
            ts_rank_or=0.0,
            clause_sim=0.0,
            content_sim=0.0,
            chunk_clause="5.2",
            clause_candidates=[],
            detected_terms=[DetectedTermRef(canonical="ИС", expansion="Информационная система", definition=None)],
            chunk_content="Настоящая инструкция определяет правила делопроизводства.",
            doc_code="OD-184",
            query="Что регламентирует ИС?",
        )
        # Must be 0.0 because chunk does NOT contain the acronym ИС or the expansion
        self.assertEqual(score_unrelated, 0.0)

    def test_calculate_relevance_pct_bounds_and_ranking(self):
        """Verify relevance score normalization strictly between 0.0% and 100.0%."""
        # 1. Zero input -> 0.0%
        zero_score = calculate_relevance_pct(
            ts_rank_exact=0.0,
            ts_rank_or=0.0,
            clause_sim=0.0,
            content_sim=0.0,
            chunk_clause="1.1",
            clause_candidates=[],
            detected_terms=[],
            chunk_content="Текст документа",
            doc_code="OD-184",
            query="нерелевантный запрос",
        )
        self.assertEqual(zero_score, 0.0)

        # 2. Maximum input -> clamped to 100.0%
        max_score = calculate_relevance_pct(
            ts_rank_exact=1.5,
            ts_rank_or=1.5,
            clause_sim=0.9,
            content_sim=0.9,
            chunk_clause="4.1.3",
            clause_candidates=["4.1.3"],
            detected_terms=[DetectedTermRef(canonical="ДОУ", expansion="ДОУ", definition=None)],
            chunk_content="4.1.3. Подразделения ДОУ ведут делопроизводство в OD-184",
            doc_code="OD-184",
            query="п. 4.1.3 OD-184 подразделения ДОУ",
        )
        self.assertEqual(max_score, 100.0)

        # 3. Exact clause match boost gives high score
        clause_score = calculate_relevance_pct(
            ts_rank_exact=0.0,
            ts_rank_or=0.0,
            clause_sim=0.0,
            content_sim=0.0,
            chunk_clause="4.1.3",
            clause_candidates=["4.1.3"],
            detected_terms=[],
            chunk_content="содержимое",
            doc_code="OD-184",
            query="п. 4.1.3",
        )
        self.assertGreaterEqual(clause_score, 65.0)

    async def test_clause_number_boosting_integration(self):
        """Verify that searching for 'п. 4.1.3' and '10.6' ranks the exact clauses first."""
        async with async_session_factory() as session:
            # Test 'п. 4.1.3'
            sources_413 = await retrieve_chunks(session, "п. 4.1.3", user_role="employee", top_k=3)
            self.assertGreater(len(sources_413), 0)
            top_413 = sources_413[0]
            self.assertEqual(top_413.clause, "4.1.3")
            self.assertEqual(top_413.document_code, "OD-184")
            self.assertGreaterEqual(top_413.relevance_pct, 80.0)

            # Test '10.6'
            sources_106 = await retrieve_chunks(session, "10.6", user_role="employee", top_k=3)
            self.assertGreater(len(sources_106), 0)
            top_106 = sources_106[0]
            self.assertEqual(top_106.clause, "10.6")
            self.assertGreaterEqual(top_106.relevance_pct, 80.0)

    async def test_term_detection_and_boosting_integration(self):
        """Verify glossary canonical terms detection and search boosting."""
        async with async_session_factory() as session:
            # Query with abbreviation 'ИИС ДО'
            terms_iis = await detect_query_terms(session, "Что регламентирует ИИС ДО в Организации?")
            canonicals = [t.canonical for t in terms_iis]
            self.assertIn("ИИС ДО", canonicals)

            # Retrieve chunks for ИИС ДО
            sources_iis = await retrieve_chunks(session, "Что такое ИИС ДО?", top_k=3)
            self.assertGreater(len(sources_iis), 0)
            # Must find chunk with glossary definition (clause 1.4 or 2.5)
            self.assertTrue(any("ИИС ДО" in s.quote for s in sources_iis))

            # Query with Russian inflected multi-word term
            terms_ling = await detect_query_terms(session, "Порядок проведения лингвистической экспертизы")
            canonicals_ling = [t.canonical for t in terms_ling]
            self.assertIn("Лингвистическая экспертиза", canonicals_ling)

    async def test_out_of_domain_query_low_relevance(self):
        """Verify that out-of-domain queries produce relevance strictly below MIN_RELEVANCE_THRESHOLD."""
        async with async_session_factory() as session:
            out_of_domain_queries = [
                "Какая сегодня погода в Париже?",
                "Рецепт пиццы с грибами и сыром",
                "Сколько планет в Солнечной системе?",
            ]
            for query in out_of_domain_queries:
                sources = await retrieve_chunks(session, query, top_k=3)
                max_relevance = max((s.relevance_pct for s in sources), default=0.0)
                self.assertLess(
                    max_relevance,
                    settings.MIN_RELEVANCE_THRESHOLD,
                    f"Query '{query}' produced relevance {max_relevance}% >= {settings.MIN_RELEVANCE_THRESHOLD}%",
                )

    async def test_empty_and_whitespace_query(self):
        """Verify empty query handling returns empty list safely."""
        async with async_session_factory() as session:
            self.assertEqual(await retrieve_chunks(session, ""), [])
            self.assertEqual(await retrieve_chunks(session, "   "), [])
            self.assertEqual(await retrieve_chunks(session, "\t\n"), [])

    async def test_template_reg_number_retrieval(self):
        """Verify that searching for template module reg_number (e.g. 'УТВ-01') retrieves the module chunk."""
        async with async_session_factory() as session:
            sources = await retrieve_chunks(session, "УТВ-01", top_k=3)
            self.assertGreater(len(sources), 0)
            top_source = sources[0]
            self.assertEqual(top_source.document_code, "MOD-ORDER-IS")
            self.assertGreaterEqual(top_source.relevance_pct, 40.0)

    async def test_source_ref_structure_compliance(self):
        """Verify that every returned SourceRef adheres to required schema types."""
        async with async_session_factory() as session:
            sources = await retrieve_chunks(
                session, "Порядок подготовки и согласования проектов приказов", top_k=3
            )
            self.assertGreater(len(sources), 0)
            for s in sources:
                self.assertIsInstance(s, SourceRef)
                self.assertIsInstance(s.document_code, str)
                self.assertIsInstance(s.document_title, str)
                self.assertIsInstance(s.chapter, str)
                self.assertIsInstance(s.clause, str)
                self.assertIsInstance(s.page_number, int)
                self.assertIsInstance(s.quote, str)
                self.assertIsInstance(s.relevance_pct, float)
                self.assertIsInstance(s.version, str)
                self.assertIsInstance(s.access_level, str)
                self.assertGreater(len(s.quote), 10)
                self.assertGreater(s.page_number, 0)
                self.assertGreaterEqual(s.relevance_pct, 0.0)
                self.assertLessEqual(s.relevance_pct, 100.0)


if __name__ == "__main__":
    unittest.main()

