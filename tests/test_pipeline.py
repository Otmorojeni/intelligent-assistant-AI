"""Unit and integration tests for orchestration pipeline (src/core/pipeline.py).

Verifies Zero-Hallucination Guard, stage latencies profiling, approval routing recommendation,
Ollama grounded generation, offline fallback behavior, and audit logging.
"""

import asyncio
from pathlib import Path
import sys
import unittest
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from src.config import settings
from src.core.llm_client import OllamaClient, build_offline_fallback_answer
from src.core.pipeline import ZERO_HALLUCINATION_REFUSAL, match_approval_recommendation, process_query
from src.db.database import async_session_factory, engine
from src.db.models import AuditLog
from src.schemas.api_models import DetectedTermRef, QueryRequest, QueryResponse, SourceRef


class TestPipeline(unittest.IsolatedAsyncioTestCase):
    """Integration test suite for question answering pipeline and safety guards."""

    @classmethod
    async def asyncTearDownClass(cls):
        await engine.dispose()

    async def test_zero_hallucination_guard_refusal(self):
        """Verify that out-of-domain query is blocked from LLM and receives official refusal."""
        async with async_session_factory() as session:
            out_of_domain_queries = [
                "Какая сегодня погода в Париже?",
                "Как испечь домашний яблочный пирог?",
                "Кто победил на чемпионате мира по футболу?",
            ]

            for query in out_of_domain_queries:
                req = QueryRequest(query=query, user_role="employee")
                resp = await process_query(session, req)

                self.assertIsInstance(resp, QueryResponse)
                self.assertTrue(resp.zero_hallucination_triggered)
                self.assertEqual(resp.answer, ZERO_HALLUCINATION_REFUSAL)
                self.assertEqual(len(resp.sources), 0)
                self.assertEqual(resp.t_llm_ms, 0.0)
                self.assertLess(resp.relevance_score, settings.MIN_RELEVANCE_THRESHOLD)
                self.assertGreater(resp.latency_ms, 0.0)

    async def test_llm_client_offline_fallback(self):
        """Verify that OllamaClient handles unreachable servers with deterministic fallback."""
        dummy_client = OllamaClient(
            base_url="http://127.0.0.1:59999/v1",  # Unused port
            timeout=1.0,
        )

        sources = [
            SourceRef(
                document_code="OD-184",
                document_title="Инструкция по ДОУ Организации",
                chapter="Глава 4. Полномочия участников",
                clause="4.1.3",
                page_number=12,
                quote="Подразделения ДОУ осуществляют методическое руководство делопроизводством.",
                relevance_pct=85.0,
                version="1.0",
                access_level="public",
            )
        ]
        terms = [
            DetectedTermRef(
                canonical="ДОУ",
                expansion="Документационное обеспечение управления",
                definition=None,
            )
        ]

        # 1. Direct fallback function check
        fallback_text = build_offline_fallback_answer("п. 4.1.3", sources, terms)
        self.assertIn("Инструкция по ДОУ Организации", fallback_text)
        self.assertIn("OD-184", fallback_text)
        self.assertIn("п. 4.1.3", fallback_text)
        self.assertIn("стр. 12", fallback_text)
        self.assertIn("ДОУ", fallback_text)

        # 2. Client generate_answer with unreachable host
        answer = await dummy_client.generate_answer(
            query="Каковы полномочия подразделений ДОУ?",
            sources=sources,
            detected_terms=terms,
            allow_fallback=True,
        )
        self.assertIsNotNone(answer)
        self.assertIn("OD-184", answer)
        self.assertIn("п. 4.1.3", answer)
        self.assertIn("стр. 12", answer)

    async def test_match_approval_recommendation(self):
        """Verify routing rule detection for IT, personnel, working groups, letters, and business trips."""
        async with async_session_factory() as session:
            # 1. IT information system order -> Rule 4
            rec_it = await match_approval_recommendation(
                session, "С кем согласовать приказ о вводе в эксплуатацию информационной системы?"
            )
            self.assertIsNotNone(rec_it)
            self.assertEqual(rec_it.rule_number, 4)
            dept_names = [stage.department for stage in rec_it.stages]
            self.assertTrue(any("информационных технологий" in d.lower() for d in dept_names))
            self.assertTrue(any("информационной безопасности" in d.lower() for d in dept_names))

            # 2. Personnel order -> Rule 2 or 3 (requires HR)
            rec_hr = await match_approval_recommendation(
                session, "С кем согласовать приказ по личному составу?"
            )
            self.assertIsNotNone(rec_hr)
            self.assertIn(rec_hr.rule_number, (2, 3))
            dept_names_hr = [stage.department for stage in rec_hr.stages]
            self.assertTrue(any("кадр" in d.lower() for d in dept_names_hr))

            # 3. Working group disposition -> Rule 7
            rec_wg = await match_approval_recommendation(
                session, "Порядок согласования распоряжения о создании рабочей группы"
            )
            self.assertIsNotNone(rec_wg)
            self.assertEqual(rec_wg.rule_number, 7)

            # 4. Business trip order -> Rule 5 (other orders)
            rec_trip = await match_approval_recommendation(
                session, "Маршрут согласования приказа о командировании"
            )
            self.assertIsNotNone(rec_trip)
            self.assertEqual(rec_trip.rule_number, 5)

            # 5. Letter to Accounts Chamber / State Authorities -> Rule 10
            rec_acc = await match_approval_recommendation(
                session, "С кем согласовывать письмо в Счетную палату РФ?"
            )
            self.assertIsNotNone(rec_acc)
            self.assertEqual(rec_acc.rule_number, 10)

            # 6. Non-approval query -> None
            rec_none = await match_approval_recommendation(session, "Что такое ИИС ДО?")
            self.assertIsNone(rec_none)

    async def test_zero_hallucination_blocks_llm_invocation(self):
        """Verify that out-of-domain query NEVER invokes LLM client methods."""
        class ExplodingLLMClient(OllamaClient):
            async def generate_answer(self, *args, **kwargs):
                raise AssertionError("LLM generate_answer MUST NOT be called when Zero-Hallucination Guard triggers!")

        async with async_session_factory() as session:
            req = QueryRequest(query="Рецепт шарлотки с яблоками", user_role="employee")
            resp = await process_query(session, req, llm_client=ExplodingLLMClient())
            self.assertTrue(resp.zero_hallucination_triggered)
            self.assertEqual(resp.answer, ZERO_HALLUCINATION_REFUSAL)
            self.assertEqual(resp.sources, [])
            self.assertEqual(resp.t_llm_ms, 0.0)

    async def test_end_to_end_process_query(self):
        """Verify full pipeline execution, latencies breakdown, terms, sources, and audit trail."""
        async with async_session_factory() as session:
            req_id = str(uuid.uuid4())
            req = QueryRequest(
                query="Порядок проведения лингвистической экспертизы",
                request_id=req_id,
                user_role="employee",
                top_k=3,
            )

            # Client configured with reasonable timeout
            client = OllamaClient(timeout=30.0)
            resp = await process_query(session, req, llm_client=client, ip_address="127.0.0.1")

            self.assertEqual(resp.request_id, req_id)
            self.assertFalse(resp.zero_hallucination_triggered)
            self.assertGreaterEqual(resp.relevance_score, settings.MIN_RELEVANCE_THRESHOLD)
            self.assertGreater(len(resp.sources), 0)
            self.assertTrue(any("экспертиз" in s.quote.lower() for s in resp.sources))
            self.assertGreater(len(resp.answer), 20)

            # Latencies check
            self.assertGreater(resp.t_match_ms, 0.0)
            self.assertGreater(resp.t_retriever_ms, 0.0)
            self.assertGreater(resp.latency_ms, 0.0)

            # Check audit log was written
            stmt = select(AuditLog).where(AuditLog.query_text == req.query).order_by(AuditLog.timestamp.desc())
            audit_res = await session.execute(stmt)
            audit_entry = audit_res.scalars().first()
            self.assertIsNotNone(audit_entry)
            self.assertEqual(audit_entry.action_type, "query")
            self.assertEqual(audit_entry.status, "success")
            self.assertEqual(audit_entry.user_role, "employee")
            self.assertGreater(audit_entry.latency_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
