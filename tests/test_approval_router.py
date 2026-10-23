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
            # 1. IS order natural language query
            rec_is = await match_approval_recommendation(
                session, "С кем согласовать приказ о вводе в эксплуатацию информационной системы?"
            )
            self.assertIsNotNone(rec_is)
            self.assertEqual(rec_is.rule_number, 4)
            self.assertGreaterEqual(len(rec_is.stages), 7)
            dept_names = [s.department for s in rec_is.stages]
            self.assertTrue(any("информационных технологий" in d.lower() for d in dept_names))
            self.assertTrue(any("информационной безопасности" in d.lower() for d in dept_names))

            # 2. Working group query
            rec_wg = await match_approval_recommendation(
                session, "Какой маршрут согласования для распоряжения о рабочей группе?"
            )
            self.assertIsNotNone(rec_wg)
            self.assertEqual(rec_wg.rule_number, 7)
            self.assertTrue(any("Кадровое" in s.department for s in rec_wg.stages))

    def test_fastapi_rest_endpoints(self):
        """Verify FastAPI REST API endpoints /v1/approval/rules and /v1/approval/calculate."""
        client = TestClient(app)

        # 1. GET /v1/approval/rules
        resp_rules = client.get("/v1/approval/rules")
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
        resp_calc = client.post(
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
        resp_fallback = client.post(
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
