"""Unit and integration tests for Approval Matrix Decision Engine and FastAPI endpoints.

Verifies:
- All 13 matrix rules and condition branches from 'Матрица_обязательного_визирования...docx'
- Ordered 5-stage workflow from Section 4.2 of 'Методические_рекомендации...docx'
- Edge cases:
    * Order with IT systems (Legal, DOU, InfoSec, IT)
    * Order with handover of affairs with and without InfoSec condition
    * Dispositions with IT condition and without
    * External letters (authorities, international, regional, central)
    * Non-modular documents fallback
- REST API endpoints (POST /v1/approval/calculate, GET /v1/approval/rules)
- Query pipeline integration attaching approval recommendation
"""

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from starlette.testclient import TestClient

from src.core.approval_router import (
    calculate_approval_route,
    get_approval_rules_list,
)
from src.core.pipeline import match_approval_recommendation, process_query
from src.db.database import async_session_factory, engine
from src.main import app
from src.schemas.api_models import (
    ApprovalCalculateRequest,
    ApprovalCalculateResponse,
    QueryRequest,
)


class TestApprovalRouter(unittest.IsolatedAsyncioTestCase):
    """Authoritative test suite for the Approval Router decision engine and API."""

    async def asyncTearDown(self):
        await engine.dispose()

    @classmethod
    async def asyncTearDownClass(cls):
        await engine.dispose()

    async def test_order_with_it_systems_stages_and_departments(self):
        """Verify order with IT systems (Rule 4) includes Legal, DOU, InfoSec, and IT in Stage 2."""
        async with async_session_factory() as session:
            # 1. By template module code
            req = ApprovalCalculateRequest(
                doc_type="MOD-ORDER-IS",
                uses_module=True,
                initiator_department="Департамент информационных технологий",
            )
            resp = await calculate_approval_route(session, req)

            self.assertIsInstance(resp, ApprovalCalculateResponse)
            self.assertEqual(resp.rule_number, 4)
            self.assertTrue(resp.is_modular)
            self.assertIn("Заместитель Председателя", resp.signatory)

            # Verify Stage 1: Initiator executor + Head
            self.assertGreaterEqual(len(resp.stages), 7)
            s1 = resp.stages[0]
            self.assertEqual(s1.order, 1)
            self.assertEqual(s1.role_name, "Ответственный исполнитель")
            self.assertEqual(s1.department, "Департамент информационных технологий")

            s2 = resp.stages[1]
            self.assertEqual(s2.order, 2)
            self.assertEqual(s2.role_name, "Руководитель подразделения-инициатора")
            self.assertEqual(s2.department, "Департамент информационных технологий")

            # Verify Stage 2 departments: Legal, DOU, InfoSec, IT
            stage_depts = [st.department for st in resp.stages]
            self.assertTrue(any("Юридическое" in d for d in stage_depts))
            self.assertTrue(any("делопроизводства" in d or "ДОУ" in d for d in stage_depts))
            self.assertTrue(any("информационной безопасности" in d for d in stage_depts))
            self.assertTrue(any("информационных технологий" in d for d in stage_depts))
            # HR must NOT be required for Rule 4
            self.assertFalse(any("кадр" in d.lower() for d in stage_depts))

            # Verify Stage 3: Proofreader linguistic expertise
            proof_stage = next(st for st in resp.stages if "Корректор" in st.role_name)
            self.assertIn("Лингвистическая экспертиза", proof_stage.reason)

            # Verify Stage 4: DOU specialist verification
            dou_stage = next(st for st in resp.stages if "Визирование Департаментом ДОУ" in st.reason)
            self.assertIn("модуля", dou_stage.reason)

            # Verify Stage 5: Signatory
            sign_stage = resp.stages[-1]
            self.assertEqual(sign_stage.role_name, "Подписант")

            # Sequential order check
            orders = [s.order for s in resp.stages]
            self.assertEqual(orders, list(range(1, len(resp.stages) + 1)))

    async def test_order_handover_affairs_without_infosec(self):
        """Verify affairs handover without InfoSec (Rule 2) includes Legal, DOU, HR, but NOT InfoSec."""
        async with async_session_factory() as session:
            req = ApprovalCalculateRequest(
                doc_type="MOD-ORDER-PROP",
                uses_module=True,
                involves_infosec_access=False,
                initiator_department="Административный департамент",
            )
            resp = await calculate_approval_route(session, req)

            self.assertEqual(resp.rule_number, 2)
            self.assertTrue(resp.is_modular)

            stage_depts = [st.department for st in resp.stages]
            self.assertTrue(any("Юридическое" in d for d in stage_depts))
            self.assertTrue(any("ДОУ" in d for d in stage_depts))
            self.assertTrue(any("Кадровое" in d for d in stage_depts))
            # InfoSec MUST NOT be present
            self.assertFalse(any("информационной безопасности" in d.lower() for d in stage_depts))

    async def test_order_handover_affairs_with_infosec(self):
        """Verify affairs handover WITH InfoSec (Rule 3) activates InfoSec Department."""
        async with async_session_factory() as session:
            req = ApprovalCalculateRequest(
                doc_type="MOD-ORDER-PROP",
                uses_module=True,
                involves_infosec_access=True,
                initiator_department="Департамент безопасности",
            )
            resp = await calculate_approval_route(session, req)

            self.assertEqual(resp.rule_number, 3)
            self.assertTrue(resp.is_modular)

            stage_depts = [st.department for st in resp.stages]
            self.assertTrue(any("Юридическое" in d for d in stage_depts))
            self.assertTrue(any("ДОУ" in d for d in stage_depts))
            self.assertTrue(any("Кадровое" in d for d in stage_depts))
            # InfoSec MUST be present
            self.assertTrue(any("информационной безопасности" in d.lower() for d in stage_depts))

    async def test_dispositions_without_it_condition(self):
        """Verify working group without IT (Rule 7) includes DOU, HR, and excludes Legal and IT."""
        async with async_session_factory() as session:
            req = ApprovalCalculateRequest(
                doc_type="MOD-DISP-WORKGROUP",
                uses_module=True,
                involves_it=False,
            )
            resp = await calculate_approval_route(session, req)

            self.assertEqual(resp.rule_number, 7)
            self.assertTrue(resp.is_modular)

            # In Matrix Rule 7: requires_legal=False
            stage_2_stages = [st for st in resp.stages if st.order not in (1, 2) and st != resp.stages[-1] and "Корректор" not in st.role_name and "проверка применения модуля" not in st.reason.lower()]
            stage_2_depts = [st.department for st in stage_2_stages]

            self.assertTrue(any("Кадровое" in d for d in stage_2_depts))
            self.assertTrue(any("ДОУ" in d for d in stage_2_depts))
            self.assertFalse(any("Юридическое" in d for d in stage_2_depts))
            self.assertFalse(any("информационных технологий" in d.lower() for d in stage_2_depts))

    async def test_dispositions_with_it_condition(self):
        """Verify working group WITH IT (Rule 8) includes IT Department and HR, excludes Legal."""
        async with async_session_factory() as session:
            req = ApprovalCalculateRequest(
                doc_type="MOD-DISP-WORKGROUP",
                uses_module=True,
                involves_it=True,
            )
            resp = await calculate_approval_route(session, req)

            self.assertEqual(resp.rule_number, 8)
            self.assertTrue(resp.is_modular)

            stage_depts = [st.department for st in resp.stages]
            self.assertTrue(any("информационных технологий" in d.lower() for d in stage_depts))
            self.assertTrue(any("Кадровое" in d for d in stage_depts))
            self.assertFalse(any("Юридическое" in d for d in stage_depts))

    async def test_external_letters_all_variants(self):
        """Verify all 4 external letters routes: authorities (10), foreign (11), central (12), regional (13)."""
        async with async_session_factory() as session:
            # 1. State authorities & Accounts Chamber -> Rule 10
            resp_auth = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="LETTER_AUTHORITIES")
            )
            self.assertEqual(resp_auth.rule_number, 10)
            self.assertFalse(resp_auth.is_modular)
            depts_auth = [st.department for st in resp_auth.stages]
            self.assertTrue(any("внутреннего контроля" in d.lower() for d in depts_auth))

            # 2. Foreign organizations -> Rule 11
            resp_intl = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="LETTER_INTERNATIONAL")
            )
            self.assertEqual(resp_intl.rule_number, 11)
            self.assertFalse(resp_intl.is_modular)
            depts_intl = [st.department for st in resp_intl.stages]
            self.assertTrue(any("международного сотрудничества" in d.lower() for d in depts_intl))

            # 3. Russian legal entities with Regional branch involvement -> Rule 13
            resp_reg = await calculate_approval_route(
                session,
                ApprovalCalculateRequest(
                    doc_type="Письмо российским юридическим лицам",
                    involves_regional=True,
                ),
            )
            self.assertEqual(resp_reg.rule_number, 13)
            self.assertFalse(resp_reg.is_modular)
            depts_reg = [st.department for st in resp_reg.stages]
            self.assertTrue(any("регионального отделения" in d.lower() for d in depts_reg))
            self.assertIn("Руководитель РО", resp_reg.signatory)

            # 4. Russian legal entities Central apparatus -> Rule 12
            resp_ca = await calculate_approval_route(
                session,
                ApprovalCalculateRequest(
                    doc_type="Письмо российским юридическим лицам",
                    involves_regional=False,
                ),
            )
            self.assertEqual(resp_ca.rule_number, 12)
            self.assertFalse(resp_ca.is_modular)
            depts_ca = [st.department for st in resp_ca.stages]
            self.assertFalse(any("регионального отделения" in d.lower() for d in depts_ca))

    async def test_non_modular_documents_fallback(self):
        """Verify non-modular fallback: orders fall back to Rule 5, dispositions fall back to Rule 9."""
        async with async_session_factory() as session:
            # Case A: Order with uses_module=False
            resp_order = await calculate_approval_route(
                session,
                ApprovalCalculateRequest(
                    doc_type="MOD-ORDER-IS",
                    uses_module=False,
                ),
            )
            self.assertEqual(resp_order.rule_number, 5)
            self.assertFalse(resp_order.is_modular)
            self.assertTrue(any("немодульн" in n.lower() or "без применения" in n.lower() for n in resp_order.notes))

            # Case B: Disposition with uses_module=False
            resp_disp = await calculate_approval_route(
                session,
                ApprovalCalculateRequest(
                    doc_type="MOD-DISP-WORKGROUP",
                    uses_module=False,
                ),
            )
            self.assertEqual(resp_disp.rule_number, 9)
            self.assertFalse(resp_disp.is_modular)

            # Case C: Material assistance disposition (Rule 6)
            resp_aid = await calculate_approval_route(
                session,
                ApprovalCalculateRequest(
                    doc_type="DISP_MATERIAL_AID",
                    uses_module=False,
                ),
            )
            self.assertEqual(resp_aid.rule_number, 6)
            self.assertFalse(resp_aid.is_modular)

    async def test_initiator_department_custom_propagation(self):
        """Verify initiator department is propagated to Stage 1, with sensible fallback if omitted."""
        async with async_session_factory() as session:
            # Custom department
            req_custom = ApprovalCalculateRequest(
                doc_type="MOD-ORDER-IS",
                initiator_department="Служба финансового мониторинга",
            )
            resp_custom = await calculate_approval_route(session, req_custom)
            self.assertEqual(resp_custom.stages[0].department, "Служба финансового мониторинга")
            self.assertEqual(resp_custom.stages[1].department, "Служба финансового мониторинга")

            # Omitted department -> "Подразделение-инициатор"
            req_default = ApprovalCalculateRequest(doc_type="MOD-ORDER-IS")
            resp_default = await calculate_approval_route(session, req_default)
            self.assertEqual(resp_default.stages[0].department, "Подразделение-инициатор")

    async def test_pipeline_integration_natural_language_queries(self):
        """Verify natural language queries attach correct approval recommendations in pipeline."""
        async with async_session_factory() as session:
            # 1. Exact prompt query: IS order with short acronym "ИС" -> Rule 4
            rec_is = await match_approval_recommendation(
                session, "С кем согласовать приказ о вводе ИС?"
            )
            self.assertIsNotNone(rec_is)
            self.assertEqual(rec_is.rule_number, 4)
            dept_names_is = [s.department for s in rec_is.stages]
            self.assertTrue(any("информационных технологий" in d.lower() for d in dept_names_is))
            self.assertTrue(any("информационной безопасности" in d.lower() for d in dept_names_is))
            self.assertFalse(any("кадр" in d.lower() for d in dept_names_is))

            # 2. Exact prompt query: Working group general -> Rule 7
            rec_wg = await match_approval_recommendation(
                session, "Какой маршрут согласования для распоряжения о рабочей группе?"
            )
            self.assertIsNotNone(rec_wg)
            self.assertEqual(rec_wg.rule_number, 7)
            dept_names_wg = [s.department for s in rec_wg.stages]
            self.assertTrue(any("кадр" in d.lower() for d in dept_names_wg))
            self.assertFalse(any("информационных технологий" in d.lower() for d in dept_names_wg))

            # 3. Working group with IT condition -> Rule 8
            rec_wg_it = await match_approval_recommendation(
                session, "Маршрут согласования распоряжения о создании рабочей группы по вопросам ИТ"
            )
            self.assertIsNotNone(rec_wg_it)
            self.assertEqual(rec_wg_it.rule_number, 8)
            dept_names_wg_it = [s.department for s in rec_wg_it.stages]
            self.assertTrue(any("информационных технологий" in d.lower() for d in dept_names_wg_it))

            # 4. Affairs handover WITH IS access -> Rule 3
            rec_prop_sec = await match_approval_recommendation(
                session, "С кем согласовать приказ о приеме и передаче дел с доступом к ИС?"
            )
            self.assertIsNotNone(rec_prop_sec)
            self.assertEqual(rec_prop_sec.rule_number, 3)
            dept_names_prop_sec = [s.department for s in rec_prop_sec.stages]
            self.assertTrue(any("информационной безопасности" in d.lower() for d in dept_names_prop_sec))

            # 5. Affairs handover WITHOUT IS access -> Rule 2
            rec_prop_no_sec = await match_approval_recommendation(
                session, "С кем согласовать приказ о приеме-передаче дел без доступа к ИС?"
            )
            self.assertIsNotNone(rec_prop_no_sec)
            self.assertEqual(rec_prop_no_sec.rule_number, 2)
            dept_names_prop_no_sec = [s.department for s in rec_prop_no_sec.stages]
            self.assertFalse(any("информационной безопасности" in d.lower() for d in dept_names_prop_no_sec))

            # 6. Letter to State Authority / Ministry (Минцифры) -> Rule 10
            rec_min = await match_approval_recommendation(
                session, "С кем согласовать внешнее письмо в Минцифры?"
            )
            self.assertIsNotNone(rec_min)
            self.assertEqual(rec_min.rule_number, 10)
            dept_names_min = [s.department for s in rec_min.stages]
            self.assertTrue(any("внутреннего контроля" in d.lower() for d in dept_names_min))

            # 7. Letter to Central Bank of Russia (Банк России) -> Rule 10
            rec_cbr = await match_approval_recommendation(
                session, "С кем согласовать внешнее письмо в Банк России?"
            )
            self.assertIsNotNone(rec_cbr)
            self.assertEqual(rec_cbr.rule_number, 10)

            # 8. Letter to Russian commercial bank (Сбербанк) -> Rule 12 (NOT foreign!)
            rec_sber = await match_approval_recommendation(
                session, "С кем согласовать внешнее письмо в Сбербанк?"
            )
            self.assertIsNotNone(rec_sber)
            self.assertEqual(rec_sber.rule_number, 12)
            dept_names_sber = [s.department for s in rec_sber.stages]
            self.assertFalse(any("международного сотрудничества" in d.lower() for d in dept_names_sber))

            # 9. Letter to foreign bank -> Rule 11
            rec_foreign = await match_approval_recommendation(
                session, "С кем согласовать письмо в иностранный банк?"
            )
            self.assertIsNotNone(rec_foreign)
            self.assertEqual(rec_foreign.rule_number, 11)
            dept_names_foreign = [s.department for s in rec_foreign.stages]
            self.assertTrue(any("международного сотрудничества" in d.lower() for d in dept_names_foreign))

            # 10. Regional letter -> Rule 13
            rec_reg = await match_approval_recommendation(
                session, "С кем согласовать внешнее письмо регионального отделения?"
            )
            self.assertIsNotNone(rec_reg)
            self.assertEqual(rec_reg.rule_number, 13)

            # 11. Informational query without approval intent -> None
            rec_info = await match_approval_recommendation(
                session, "Что такое номенклатура дел?"
            )
            self.assertIsNone(rec_info)

    async def test_direct_rule_numbers_and_edge_inputs(self):
        """Verify numeric rule resolution, template aliases, and empty input handling."""
        async with async_session_factory() as session:
            # Numeric rule 4
            resp_r4 = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="правило 4")
            )
            self.assertEqual(resp_r4.rule_number, 4)
            self.assertTrue(resp_r4.is_modular)

            # Numeric rule 2 promoted to 3 with infosec flag
            resp_r2_to_3 = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="2", involves_infosec_access=True)
            )
            self.assertEqual(resp_r2_to_3.rule_number, 3)

            # Numeric rule 7 promoted to 8 with IT flag
            resp_r7_to_8 = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="№ 7", involves_it=True)
            )
            self.assertEqual(resp_r7_to_8.rule_number, 8)

            # Template alias УТВ-01
            resp_utv1 = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="УТВ-01")
            )
            self.assertEqual(resp_utv1.rule_number, 4)
            self.assertTrue(resp_utv1.is_modular)

            # Template alias УТВ-02 (DOU appointment)
            resp_utv2 = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="УТВ-02")
            )
            self.assertEqual(resp_utv2.rule_number, 5)
            self.assertTrue(resp_utv2.is_modular)

            # Template alias УТВ-05 (Internal audit)
            resp_utv5 = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="УТВ-05")
            )
            self.assertEqual(resp_utv5.rule_number, 9)
            self.assertTrue(resp_utv5.is_modular)

            # Empty doc_type string fallback
            resp_empty = await calculate_approval_route(
                session, ApprovalCalculateRequest(doc_type="   ")
            )
            self.assertEqual(resp_empty.rule_number, 5)
            self.assertFalse(resp_empty.is_modular)

    async def test_fastapi_rest_endpoints(self):
        """Verify FastAPI REST API endpoints /v1/approval/rules and /v1/approval/calculate cleanly using AsyncClient."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. GET /v1/approval/rules
            resp_rules = await client.get("/v1/approval/rules")
            self.assertEqual(resp_rules.status_code, 200)
            rules_data = resp_rules.json()
            self.assertEqual(len(rules_data), 13)
            self.assertEqual([r["rule_number"] for r in rules_data], list(range(1, 14)))

            # Rule 4 check
            r4 = next(r for r in rules_data if r["rule_number"] == 4)
            self.assertTrue(r4["is_modular"])
            self.assertEqual(r4["requires_infosec"], "yes")
            self.assertEqual(r4["requires_it"], "yes")

            # 2. POST /v1/approval/calculate (Order with IT systems)
            resp_calc = await client.post(
                "/v1/approval/calculate",
                json={
                    "doc_type": "MOD-ORDER-IS",
                    "uses_module": True,
                    "involves_infosec_access": True,
                    "involves_it": True,
                    "involves_regional": False,
                    "initiator_department": "Департамент ИТ",
                },
            )
            self.assertEqual(resp_calc.status_code, 200)
            calc_data = resp_calc.json()
            self.assertEqual(calc_data["rule_number"], 4)
            self.assertTrue(calc_data["is_modular"])
            self.assertGreaterEqual(len(calc_data["stages"]), 7)

            # 3. POST /v1/approval/calculate (Non-modular fallback)
            resp_fallback = await client.post(
                "/v1/approval/calculate",
                json={
                    "doc_type": "MOD-ORDER-IS",
                    "uses_module": False,
                },
            )
            self.assertEqual(resp_fallback.status_code, 200)
            fb_data = resp_fallback.json()
            self.assertEqual(fb_data["rule_number"], 5)
            self.assertFalse(fb_data["is_modular"])


if __name__ == "__main__":
    unittest.main()

