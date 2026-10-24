"""Unit and integration tests for compliance checker improvements, Auto-Fix, and retriever calibration."""

import io
from pathlib import Path
import unittest

import docx
from docx.shared import Cm, Mm, Pt
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.core.compliance_checker import check_docx_compliance, remediate_docx
from src.core.llm_client import build_offline_fallback_answer
from src.core.retriever import calculate_relevance_pct, retrieve_chunks
from src.db.database import async_session_factory
from src.main import app


class TestComplianceImprovements(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying physical formatting checks, Auto-Fix remediation, and retriever calibration."""

    async def test_ordinary_draft_receives_realistic_score_not_100_percent(self) -> None:
        """Ordinary unformatted document must fail physical checks (margins, font, indent) rather than getting 100%."""
        doc = docx.Document()
        # Non-standard margins (e.g. 10mm all around)
        for s in doc.sections:
            s.left_margin = Mm(10)
            s.right_margin = Mm(10)
            s.top_margin = Mm(10)
            s.bottom_margin = Mm(10)

        # Non-standard font (Calibri) and no paragraph indent
        p = doc.add_paragraph("Служебная записка о согласовании бюджета на командировочные расходы сотрудников отдела.")
        for r in p.runs:
            r.font.name = "Calibri"
            r.font.size = Pt(11)

        p2 = doc.add_paragraph(
            "Прошу согласовать выделение денежных средств на проведение рабочей встречи в региональном филиале Организации. "
            "Смета расходов и обоснование целесообразности командировки прилагаются в приложении к настоящей записке."
        )
        for r in p2.runs:
            r.font.name = "Calibri"
            r.font.size = Pt(11)

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        file_bytes = buf.getvalue()

        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, file_bytes, "memo.docx")

            # Must not be 100% compliant!
            self.assertFalse(resp.is_compliant)
            self.assertLess(resp.score_pct, 100.0)
            self.assertGreater(len(resp.issues), 0)

            rule_ids = {iss.rule_id for iss in resp.issues}
            # Margins must be flagged (10mm < 30mm)
            self.assertIn("CHK-MARG", rule_ids)
            # Font must be flagged (Calibri 11pt)
            self.assertIn("CHK-FONT", rule_ids)
            # Auto-Fix URL must be generated
            self.assertIsNotNone(resp.fixed_file_url)
            self.assertTrue(resp.fixed_file_url.startswith("/v1/documents/download/fixed_"))

    async def test_auto_fix_remediation_generates_valid_formatted_docx(self) -> None:
        """Auto-fix must clean template artifacts, standardize margins to 30/15/20/20, font to Times New Roman."""
        doc = docx.Document()
        doc.add_paragraph("МОДУЛЬНЫЙ ДОКУМЕНТ")
        doc.add_paragraph("УТВЕРЖДЕНО Приказом № УТВ-01 от 12.01.2026")
        doc.add_paragraph("ПРИКАЗ О вводе в эксплуатацию [1] информационной системы")
        doc.add_paragraph("1. Назначить ____ ответственным [2] за эксплуатацию ИС.")
        doc.add_paragraph("Примечания по заполнению: данный блок необходимо удалить.")

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        file_bytes = buf.getvalue()

        download_url = remediate_docx(file_bytes, "draft.docx")
        self.assertIsNotNone(download_url)
        self.assertTrue(download_url.startswith("/v1/documents/download/fixed_"))

        file_name = download_url.split("/")[-1]
        fixed_path = settings.GENERATED_DOCS_DIR / file_name
        self.assertTrue(fixed_path.exists())

        # Inspect resulting fixed DOCX
        fixed_doc = docx.Document(str(fixed_path))
        # 1. Margins
        sec = fixed_doc.sections[0]
        self.assertAlmostEqual(sec.left_margin.mm, 30.0, delta=0.5)
        self.assertAlmostEqual(sec.right_margin.mm, 15.0, delta=0.5)
        self.assertAlmostEqual(sec.top_margin.mm, 20.0, delta=0.5)
        self.assertAlmostEqual(sec.bottom_margin.mm, 20.0, delta=0.5)

        # 2. Text cleanups
        fixed_text = "\n".join(p.text for p in fixed_doc.paragraphs)
        self.assertNotIn("МОДУЛЬНЫЙ ДОКУМЕНТ", fixed_text)
        self.assertNotIn("УТВ-01", fixed_text)
        self.assertNotIn("Примечания по заполнению", fixed_text)
        self.assertNotIn("[1]", fixed_text)
        self.assertNotIn("[2]", fixed_text)

        # Clean up generated file
        try:
            fixed_path.unlink()
        except Exception:
            pass

    async def test_endpoint_check_compliance_returns_fixed_file_url(self) -> None:
        """HTTP POST /v1/documents/check-compliance returns fixed_file_url in response."""
        doc = docx.Document()
        doc.add_paragraph("ДЕПАРТАМЕНТ ИНФОРМАЦИОННЫХ ТЕХНОЛОГИЙ")
        doc.add_paragraph("СЛУЖЕБНАЯ ЗАПИСКА")
        doc.add_paragraph("Прошу согласовать проведение тестовых испытаний системы.")
        doc.add_paragraph("Руководитель проекта (подпись) И.И. Иванов")

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/documents/check-compliance",
                files={
                    "file": (
                        "test_memo.docx",
                        buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            body = resp.json()
            self.assertIn("fixed_file_url", body)
            self.assertIsNotNone(body["fixed_file_url"])
            self.assertTrue(body["fixed_file_url"].startswith("/v1/documents/download/fixed_"))

            # Clean up generated fixed file
            fname = body["fixed_file_url"].split("/")[-1]
            fpath = settings.GENERATED_DOCS_DIR / fname
            if fpath.exists():
                fpath.unlink()

    async def test_retriever_conversational_synonyms_and_calibration(self) -> None:
        """Verify conversational query expansions for 'от руки', 'черновики', 'полужирным', 'колонтитулы'."""
        async with async_session_factory() as session:
            # Query with conversational filler and synonym 'от руки'
            q1 = "Коллега сказал, что черновики можно писать от руки, правда ли?"
            sources1 = await retrieve_chunks(session, q1, user_role="employee", top_k=3)
            self.assertGreater(len(sources1), 0)
            clauses1 = [s.clause for s in sources1]
            # Must find clause 2.1, 2.1.4 or 5.1 (Drafts and document preparation rules)
            self.assertTrue(any(c in ("2.1", "2.1.4", "5.1") for c in clauses1))

            # Query with 'полужирным шрифтом'
            q2 = "Можно ли выделять слова полужирным шрифтом?"
            sources2 = await retrieve_chunks(session, q2, user_role="employee", top_k=3)
            self.assertGreater(len(sources2), 0)
            clauses2 = [s.clause for s in sources2]
            # Must match 3.2 or 5.3
            self.assertTrue(any(c in ("3.2", "5.3") for c in clauses2))

            # Query with 'колонтитулы'
            q3 = "Как правильно оформлять колонтитулы и нумерацию страниц?"
            sources3 = await retrieve_chunks(session, q3, user_role="employee", top_k=3)
            clauses3 = [s.clause for s in sources3]
            # Must match pagination/headers clauses (8.16, 3.3, 9.5.3 or 6.2)
            self.assertTrue(any(c in ("8.16", "3.3", "9.5.3", "6.2") for c in clauses3), f"Clauses found: {clauses3}")

    def test_relevance_pct_calibration_prevents_partial_saturation_to_100(self) -> None:
        """Partial matches without exact clause number or full 95%+ coverage must be capped <= 75.0%."""
        # Simulated partial match: ts_rank > 0, coverage = 0.5, no exact clause
        score = calculate_relevance_pct(
            ts_rank_exact=0.4,
            ts_rank_or=0.8,
            clause_sim=0.0,
            content_sim=0.15,
            chunk_clause="9.15",
            clause_candidates=["1.1"],
            detected_terms=[],
            chunk_content="Текст документа содержит некоторые совпадающие слова",
            doc_code="OD-184",
            query="согласование некоторых документов",
            bm25_norm=0.7,
            semantic_sim=0.5,
            rrf_boost=10.0,
        )
        self.assertLessEqual(score, 75.0)
        self.assertGreaterEqual(score, 45.0)

    async def test_default_word_font_calibri_detected_as_issue(self) -> None:
        """A document using Word default styling (Calibri 11pt via docDefaults) must trigger CHK-FONT."""
        doc = docx.Document()
        doc.add_paragraph("Служебная записка о согласовании графика работы отдела.")
        doc.add_paragraph("Прошу согласовать график дежурств сотрудников на предстоящий квартал.")
        buf = io.BytesIO()
        doc.save(buf)

        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, buf.getvalue(), "default_font.docx")
            rule_ids = {iss.rule_id for iss in resp.issues}
            self.assertIn("CHK-FONT", rule_ids)

    async def test_uppercase_fio_signature_accepted(self) -> None:
        """Official documents with uppercase signatory surnames (e.g. И.И. ИВАНОВ) must pass CHK-SIGN."""
        doc = docx.Document()
        doc.add_paragraph("ПРИКАЗ")
        doc.add_paragraph("О вводе в эксплуатацию информационной системы")
        doc.add_paragraph("В целях автоматизации процессов документационного обеспечения,")
        doc.add_paragraph("ПРИКАЗЫВАЮ: ввести в эксплуатацию систему.")
        doc.add_paragraph("Контроль за исполнением приказа оставляю за собой.")
        doc.add_paragraph("Генеральный директор           (подпись)           И.И. ИВАНОВ")
        doc.add_paragraph("ДАТА / РЕГИСТРАЦИОННЫЙ НОМЕР (НЕ УДАЛЯТЬ)")
        doc.add_paragraph("ВИЗУАЛИЗАЦИЯ ЭП (НЕ УДАЛЯТЬ)")

        buf = io.BytesIO()
        doc.save(buf)

        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, buf.getvalue(), "caps_signature.docx")
            rule_ids = {iss.rule_id for iss in resp.issues}
            self.assertNotIn("CHK-SIGN", rule_ids)

    def test_auto_fix_removes_entire_notes_block_and_cleans_title(self) -> None:
        """Auto-fix must strip the entire notes block (heading + note paragraphs) and clean title dots."""
        doc = docx.Document()
        p_title = doc.add_paragraph("О вводе в эксплуатацию информационной системы.")
        for r in p_title.runs:
            r.font.underline = True
        doc.add_paragraph("1. Назначить ответственного за эксплуатацию информационной системы.")
        doc.add_paragraph("Примечания по заполнению шаблона:")
        doc.add_paragraph("Пункт 1 заполняется в соответствии с приказом о назначении.")
        doc.add_paragraph("В пункте 2 указываются реквизиты технического паспорта системы.")

        buf = io.BytesIO()
        doc.save(buf)

        url = remediate_docx(buf.getvalue(), "test_notes.docx")
        self.assertIsNotNone(url)

        fname = url.split("/")[-1]
        fpath = settings.GENERATED_DOCS_DIR / fname
        fixed_doc = docx.Document(str(fpath))

        fixed_texts = [p.text for p in fixed_doc.paragraphs]
        fixed_joined = "\n".join(fixed_texts)

        # Entire notes block must be stripped
        self.assertNotIn("Примечания по заполнению", fixed_joined)
        self.assertNotIn("Пункт 1 заполняется", fixed_joined)
        self.assertNotIn("технического паспорта системы", fixed_joined)

        # Title trailing dot must be stripped and underline removed
        title_p = fixed_doc.paragraphs[0]
        self.assertFalse(title_p.text.endswith("."))
        self.assertTrue(all(not r.font.underline for r in title_p.runs))

        if fpath.exists():
            fpath.unlink()

    async def test_external_non_ord_document_rejected_and_no_route(self) -> None:
        """Third-party document (e.g. computer networks test 'вопросы к тесту.docx') must not be classified as Act or receive an approval route."""
        doc = docx.Document()
        doc.add_paragraph("Вопросы к тесту по дисциплине Сети и телекоммуникации")
        doc.add_paragraph("1. Взаимодействие в компьютерных сетях. Семиуровневая модель OSI.")
        doc.add_paragraph("2. Понятие интерактивной связи компьютеров и сетевых протоколов передачи данных.")
        doc.add_paragraph("3. Практические аспекты маршрутизации пакетов в корпоративных сетях.")

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        file_bytes = buf.getvalue()

        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, file_bytes, "вопросы к тесту.docx")

            # Must NOT be classified as "Акт"
            self.assertNotEqual(resp.detected_doc_kind, "Акт")
            self.assertEqual(resp.detected_doc_kind, "Неопознанный документ / Не является ОРД")

            # Compliance score must not exceed 25% (unsuitable for approval)
            self.assertLessEqual(resp.score_pct, 25.0)
            self.assertFalse(resp.passed)
            self.assertFalse(resp.is_compliant)

            # Must NOT assign an approval route (Rule 5 or any other rule)
            self.assertIsNone(resp.approval_recommendation)

            # Must NOT generate an auto-fixed file for non-ORD files
            self.assertIsNone(resp.fixed_file_url)

            # Must contain critical CHK-ORD issue
            rule_ids = {iss.rule_id for iss in resp.issues}
            self.assertIn("CHK-ORD", rule_ids)
            chk_ord_issue = next(i for i in resp.issues if i.rule_id == "CHK-ORD")
            self.assertEqual(chk_ord_issue.severity, "critical")

    async def test_word_boundary_act_not_triggered_by_interactive_word(self) -> None:
        """The word 'интерактивной' containing substring 'акт' must NOT trigger 'Акт' classification."""
        from src.core.compliance_checker import _detect_doc_kind_and_module
        sample_text = "Тестовые вопросы: понятие интерактивной связи узлов, сетевые контакты и практические работы."
        detected_kind, _ = _detect_doc_kind_and_module(sample_text)
        self.assertNotEqual(detected_kind, "Акт")
        self.assertEqual(detected_kind, "Неопознанный документ / Не является ОРД")

    async def test_project_committee_roles_explicitly_listed_in_answer(self) -> None:
        """Assistant answer to 'Какие роли входят в состав проектного комитета...' must explicitly list all 4 roles."""
        async with async_session_factory() as session:
            q = "Какие роли входят в состав проектного комитета в модульном распоряжении?"
            sources = await retrieve_chunks(session, q, user_role="employee", top_k=3)
            self.assertGreater(len(sources), 0)

            # Ensure MOD-DISP-PROJECT or OD-184 clause 9.5.7 is retrieved
            doc_codes = {s.document_code for s in sources}
            self.assertIn("MOD-DISP-PROJECT", doc_codes)

            answer = build_offline_fallback_answer(q, sources)

            # Must explicitly list all roles
            self.assertIn("Председатель Комитета", answer)
            self.assertIn("Заместитель председателя Комитета", answer)
            self.assertIn("Секретарь Комитета", answer)
            self.assertIn("Члены Комитета", answer)

            # Must not contain raw template artifacts
            self.assertNotIn("______", answer)
            self.assertNotIn("[7]", answer)
            self.assertNotIn("[8]", answer)

            # Must cite MOD-DISP-PROJECT and OD-184
            self.assertIn("MOD-DISP-PROJECT", answer)

    async def test_workgroup_roles_explicitly_listed(self) -> None:
        """Assistant answer for working group roles must list Leader, Deputy, Secretary, Members."""
        async with async_session_factory() as session:
            q = "Какие роли входят в состав рабочей группы в модульном распоряжении?"
            sources = await retrieve_chunks(session, q, user_role="employee", top_k=3)
            answer = build_offline_fallback_answer(q, sources)

            self.assertIn("Руководитель рабочей группы", answer)
            self.assertIn("Заместитель руководителя рабочей группы", answer)
            self.assertIn("Секретарь рабочей группы", answer)
            self.assertIn("Члены рабочей группы", answer)

    async def test_test_question_mentioning_act_or_order_rejected_as_non_ord(self) -> None:
        """Test document where questions mention 'акт' or 'приказ' must not be classified as ORD."""
        doc = docx.Document()
        doc.add_paragraph("Вопросы к зачету по компьютерным сетям")
        doc.add_paragraph("1. Составьте акт технической экспертизы сервера в организации.")
        doc.add_paragraph("2. Назовите приказ Минцифры об утверждении стандартов связи.")

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        file_bytes = buf.getvalue()

        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, file_bytes, "зачет_сети.docx")
            self.assertEqual(resp.detected_doc_kind, "Неопознанный документ / Не является ОРД")
            self.assertLessEqual(resp.score_pct, 25.0)
            self.assertIsNone(resp.approval_recommendation)
            self.assertIsNone(resp.fixed_file_url)
            self.assertEqual(len(resp.issues), 1)
            self.assertEqual(resp.issues[0].rule_id, "CHK-ORD")

    async def test_role_queries_who_enters_returns_clean_roles(self) -> None:
        """Queries like 'Кто входит в проектный комитет?' and 'Кто входит в группу внутреннего аудита?' must return structured roles."""
        async with async_session_factory() as session:
            # 1. Project committee "Кто входит"
            q1 = "Кто входит в проектный комитет?"
            sources1 = await retrieve_chunks(session, q1, user_role="employee", top_k=3)
            ans1 = build_offline_fallback_answer(q1, sources1)
            self.assertIn("Председатель Комитета", ans1)
            self.assertIn("Секретарь Комитета", ans1)
            self.assertIn("Члены Комитета", ans1)
            self.assertFalse(ans1.startswith(","))
            self.assertFalse(ans1.startswith("..."))
            self.assertNotIn("______", ans1)

            # 2. Audit team "Кто входит"
            q2 = "Кто входит в группу внутреннего аудита?"
            sources2 = await retrieve_chunks(session, q2, user_role="employee", top_k=3)
            ans2 = build_offline_fallback_answer(q2, sources2)
            self.assertIn("Руководитель группы аудита", ans2)
            self.assertNotIn("______", ans2)


if __name__ == "__main__":
    unittest.main()
