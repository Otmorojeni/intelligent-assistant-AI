"""Comprehensive Generalization & Novel Documents Verification Suite.

Validates that the AI Assistant service is completely generalized, non-hardcoded,
and operates reliably on novel corporate regulations, instructions, policies,
agreements, protocols, and multi-version lifecycles beyond original hackathon materials.

Test Categories:
1. Hot-Reload & Multi-Version Lifecycle of Novel Regulations:
   - Upload novel DOCX & PDF regulations (PIB-501, DBO-12, RKA-03) with DSP & internal classification.
   - Hot-reload without server restart; immediate PostgreSQL tsvector indexing.
   - Dynamic version switching / rollback (/switch-version and /activate-version).
   - Multi-version document catalog listing (/v1/documents/versions).

2. RAG Hybrid Retrieval & Strict RBAC Enforcement:
   - Deep clause search and precise citation of novel document rules (PIB-501, DBO-12).
   - Role-Based Access Control: 'employee' blocked from 'dsp' / 'internal' chunks.
   - 'dou_specialist' and 'security_auditor' successfully retrieve classified chunks.
   - Grounded generation without hallucinating OD-184.
   - Normative table extraction of committee and working body roles from novel documents.

3. Normative Compliance & Auto-Fix on Diverse Document Types:
   - Exemplar novel Orders, Dispositions, Protocols, and Memos score 90-100% (Passed).
   - Defective novel documents detected with exact rule violations (margins, fonts, spacing, title, signature).
   - Auto-Fix remediation produces clean compliant DOCX resolving detected defects.
   - Non-ORD documents (Contracts, Technical Specifications, Resumes, Reports) correctly rejected:
     * Never falsely classified as 'Приказ' or 'Акт'.
     * Never assigned fictitious approval routes (approval_recommendation is None).

4. Query Robustness & Safety Guards:
   - Conversational phrasing, slang, colloquial queries properly grounded in novel regulations.
   - Typo-tolerant retrieval via PostgreSQL trigrams and BM25Okapi Russian stem matching.
   - Multi-aspect two-part questions avoid coverage dilution.
   - Zero-Hallucination Guard blocks out-of-domain queries with official refusal.
"""

import asyncio
import io
from pathlib import Path
import sys
import unittest
import uuid

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Mm, Pt
import httpx
from httpx import ASGITransport
import pymupdf
from sqlalchemy import delete, func, select, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.core.compliance_checker import check_docx_compliance, remediate_docx
from src.core.llm_client import build_offline_fallback_answer
from src.core.pipeline import ZERO_HALLUCINATION_REFUSAL, process_query
from src.core.retriever import retrieve_chunks
from src.core.security import check_document_access, create_access_token
from src.core.versioning import (
    activate_document_version,
    get_all_document_versions,
    upload_document_version,
)
from src.db.database import async_session_factory, engine
from src.db.models import AuditLog, DocumentChunk, KnowledgeDocument
from src.main import app
from src.schemas.api_models import QueryRequest, QueryResponse


from src.core.llm_client import OllamaClient, build_offline_fallback_answer


class MockFastOllamaClient(OllamaClient):
    """Fast deterministic LLM client for tests to avoid external Ollama latency."""

    async def generate_answer(
        self, query, sources, detected_terms=None, approval_summary=None
    ):
        return build_offline_fallback_answer(
            query=query,
            sources=sources,
            detected_terms=detected_terms,
        )


def get_pdf_font_file() -> Optional[str]:
    """Find a system TrueType font supporting Cyrillic."""
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/times.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def create_novel_pib_docx(version: str = "1.0") -> bytes:
    """Create in-memory DOCX for 'Политика информационной безопасности № ПИБ-501'."""
    doc = docx.Document()
    doc.add_heading(f"Политика информационной безопасности Организации № ПИБ-501 (Редакция {version})", level=0)
    
    doc.add_heading("Глава 1. Общие положения политики ИБ", level=1)
    doc.add_paragraph(
        "1.1. Настоящая Политика информационной безопасности определяет базовые требования к обеспечению "
        "информационной безопасности, конфиденциальности, целостности и доступности информационных активов Банка."
    )
    doc.add_paragraph(
        "1.2. Требования политики обязательны для исполнения всеми работниками, подрядчиками и внешними аудиторами."
    )

    doc.add_heading("Глава 2. Требования к аутентификации и парольной защите", level=1)
    doc.add_paragraph(
        "2.1. Пароли учетных записей пользователей информационных систем подлежат регулярной плановой смене "
        "не реже одного раза в 90 календарных дней. Периодичность смены паролей пользователей установлена нормативно. "
        "Минимальная длина пароля составляет 12 символов, включая заглавные буквы, строчные буквы, цифры и специальные символы. "
        "Запрещается повторное использование последних 6 паролей."
    )
    doc.add_paragraph(
        "2.2. При пятикратном неверном вводе пароля учетная запись пользователя автоматически блокируется "
        "на срок не менее 30 минут либо до ручной разблокировки администратором безопасности."
    )

    doc.add_heading("Глава 3. Порядок реагирования на инциденты безопасности", level=1)
    doc.add_paragraph(
        "3.1. Обо всех выявленных подозрениях на компрометацию учетных данных или вредоносную активность работник "
        "обязан незамедлительно, не позднее 15 минут с момента обнаружения, уведомить Дежурную службу SOC по телефону 1122."
    )

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_novel_dbo_pdf() -> bytes:
    """Create in-memory PDF for 'Регламент дистанционного банковского обслуживания № ДБО-12'."""
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=842)
    font_file = get_pdf_font_file()
    fontname = "f0" if font_file else "helv"
    if font_file:
        page.insert_font(fontname=fontname, fontfile=font_file)

    page.insert_text((50, 50), "Регламент дистанционного банковского обслуживания № ДБО-12", fontname=fontname, fontsize=14)
    page.insert_text((50, 90), "Раздел 1. Общие условия подключения к системе ДБО", fontname=fontname, fontsize=12)
    page.insert_text(
        (50, 115),
        "1.1. Настоящий Регламент регулирует порядок предоставления сервисов ДБО корпоративным и розничным клиентам.",
        fontname=fontname,
        fontsize=10,
    )
    page.insert_text(
        (50, 135),
        "1.2. Подключение к личному кабинету ДБО осуществляется на основании заявления клиента и договора банковского счета.",
        fontname=fontname,
        fontsize=10,
    )

    page.insert_text((50, 170), "Раздел 2. Сроки и лимиты совершения дистанционных операций", fontname=fontname, fontsize=12)
    page.insert_text(
        (50, 195),
        "2.1. Максимальный срок обработки электронного платежного поручения через шлюз ДБО составляет не более 15 минут в операционное время.",
        fontname=fontname,
        fontsize=10,
    )
    page.insert_text(
        (50, 215),
        "2.2. Суточный лимит безакцептного перевода средств без дополнительного подтверждения кодом OTP установлен в размере 300 000 рублей.",
        fontname=fontname,
        fontsize=10,
    )

    page.insert_text((50, 250), "Раздел 3. Блокировка и приостановление доступа", fontname=fontname, fontsize=12)
    page.insert_text(
        (50, 275),
        "3.1. Банк вправе приостановить доступ к ДБО в случае выявления признаков осуществления перевода без добровольного согласия клиента.",
        fontname=fontname,
        fontsize=10,
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_novel_rka_docx_with_roles() -> bytes:
    """Create in-memory DOCX for 'Регламент кадрового администрирования № РКА-03' with structured role table."""
    doc = docx.Document()
    doc.add_heading("Регламент кадрового администрирования и аттестации персонала № РКА-03", level=0)

    doc.add_heading("Глава 1. Общие положения аттестации", level=1)
    doc.add_paragraph(
        "1.1. Регламент определяет периодичность, критерии и порядок проведения аттестации работников Организации."
    )

    doc.add_heading("Глава 2. Состав Аттестационной комиссии", level=1)
    doc.add_paragraph(
        "2.1. Для проведения плановой и внеочередной аттестации формируется постоянно действующая Аттестационная комиссия Организации."
    )
    doc.add_paragraph("Установленный состав и роли: Председатель комиссии, Заместитель председателя комиссии, Секретарь комиссии, Члены аттестационной комиссии.")

    # Insert table of roles
    tbl = doc.add_table(rows=1, cols=3)
    hdr_cells = tbl.rows[0].cells
    hdr_cells[0].text = "Роль в комиссии"
    hdr_cells[1].text = "Должностное лицо"
    hdr_cells[2].text = "Полномочия"

    role_data = [
        ("Председатель аттестационной комиссии", "Заместитель Председателя Правления", "Общее руководство заседанием и утверждение протокола"),
        ("Заместитель председателя комиссии", "Руководитель Департамента кадрового администрирования", "Исполнение обязанностей в отсутствие председателя"),
        ("Секретарь аттестационной комиссии", "Ведущий эксперт отдела кадров", "Ведение протокола и сбор аттестационных листов"),
        ("Члены аттестационной комиссии", "Руководители профильных департаментов", "Оценка компетенций и голосование по результатам аттестации"),
    ]
    for role, pos, powers in role_data:
        row_cells = tbl.add_row().cells
        row_cells[0].text = role
        row_cells[1].text = pos
        row_cells[2].text = powers

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_novel_document_bytes(
    kind: str = "Приказ",
    with_defects: bool = False,
    non_ord_type: str = "",
) -> bytes:
    """Synthesize realistic new documents (.docx) with or without formatting defects."""
    doc = docx.Document()

    if non_ord_type == "contract":
        doc.add_paragraph("ДОГОВОР КУПЛИ-ПРОДАЖИ ОБОРУДОВАНИЯ № 44-КП")
        doc.add_paragraph("г. Москва                                                              24 октября 2026 г.")
        doc.add_paragraph("ООО «ТехноСнаб», именуемое в дальнейшем «Продавец», и ПАО «Банк», именуемое «Покупатель», заключили договор.")
        doc.add_paragraph("1. Предмет договора: Продавец обязуется передать в собственность серверное оборудование.")
        doc.add_paragraph("2. Передача товара оформляется актом сдачи-приемки товара, который составили стороны настоящего договора.")
        doc.add_paragraph("Подписи сторон: Продавец: Сидоров С.С.  Покупатель: Петров П.П.")
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    if non_ord_type == "tz":
        doc.add_paragraph("ТЕХНИЧЕСКОЕ ЗАДАНИЕ НА РАЗРАБОТКУ ШЛЮЗА ДБО")
        doc.add_paragraph("1. Назначение системы: интеграция банковских сервисов ДБО с шиной данных.")
        doc.add_paragraph("2. Требования к производительности: пропускная способность не менее 500 RPS.")
        doc.add_paragraph("Составитель: Главный архитектор Кузнецов К.К.")
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    if non_ord_type == "resume":
        doc.add_paragraph("РЕЗЮМЕ КАНДИДАТА НА ДОЛЖНОСТЬ ВЕДУЩЕГО ЭКСПЕРТА ДОУ")
        doc.add_paragraph("ФИО: Сергеева Анна Михайловна")
        doc.add_paragraph("Опыт работы: 8 лет в сфере корпоративного делопроизводства и СЭД.")
        doc.add_paragraph("Навыки: знание ГОСТ Р 7.0.97-2016, организация архивного хранения.")
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    if non_ord_type == "report":
        doc.add_paragraph("ОТЧЕТ О РЕЗУЛЬТАТАХ НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ СИСТЕМЫ ДБО")
        doc.add_paragraph("Дата проведения: 22.10.2026. Место: Тестовый контур ЦОД.")
        doc.add_paragraph("Выводы: система выдерживает целевую нагрузку без деградации времени отклика.")
        doc.add_paragraph("Руководитель тестирования: Смирнов В.В.")
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    # Administrative ORD Documents (Приказ, Распоряжение, Протокол, Служебная записка)
    for s in doc.sections:
        if with_defects:
            s.left_margin = Mm(10)
            s.right_margin = Mm(10)
            s.top_margin = Mm(10)
            s.bottom_margin = Mm(10)
        else:
            s.left_margin = Mm(30)
            s.right_margin = Mm(15)
            s.top_margin = Mm(20)
            s.bottom_margin = Mm(20)

    font_name = "Comic Sans MS" if with_defects else "Times New Roman"
    font_size = Pt(9) if with_defects else Pt(13)
    line_sp = 2.5 if with_defects else 1.15
    indent_val = Cm(0) if with_defects else Cm(1.25)

    p_org = doc.add_paragraph("НАИМЕНОВАНИЕ ОРГАНИЗАЦИИ")
    p_org.paragraph_format.line_spacing = line_sp
    for r in p_org.runs:
        r.font.name = font_name
        r.font.size = font_size

    p_kind = doc.add_paragraph(kind.upper())
    p_kind.paragraph_format.line_spacing = line_sp
    for r in p_kind.runs:
        r.font.name = font_name
        r.font.size = Pt(14)
        r.bold = True

    p_meta = doc.add_paragraph("24.10.2026 № 210-П")
    p_meta.paragraph_format.line_spacing = line_sp
    for r in p_meta.runs:
        r.font.name = font_name
        r.font.size = font_size

    # Title paragraph
    raw_title = "О внедрении новой политики безопасности в информационных системах." if with_defects else "О внедрении новой политики безопасности в информационных системах"
    p_title = doc.add_paragraph(raw_title)
    p_title.paragraph_format.line_spacing = line_sp
    p_title.paragraph_format.first_line_indent = Cm(0)
    for r in p_title.runs:
        r.font.name = font_name
        r.font.size = font_size

    # Body paragraphs
    if kind == "Приказ":
        p_body = doc.add_paragraph(
            "В целях реализации мер защиты информации и выполнения требований регулятора приказываю "
            "ввести в действие регламент парольной защиты во всех структурных подразделениях Организации."
        )
    elif kind == "Распоряжение":
        p_body = doc.add_paragraph(
            "В соответствии с решением Правления обязываю Департамент информационных технологий "
            "обеспечить развертывание обновленных политик доступа в срок до 1 декабря 2026 года."
        )
    elif kind == "Протокол":
        p_body = doc.add_paragraph(
            "СЛУШАЛИ: Доклад о готовности контура безопасности. ВЫСТУПИЛИ: Эксперты комиссии. "
            "ПОСТАНОВИЛИ: Принять представленные регламенты и направить на согласование."
        )
    else:  # Служебная записка
        p_body = doc.add_paragraph(
            "В связи с производственной необходимостью прошу согласовать предоставление расширенных "
            "прав доступа к тестовому контуру ДБО для участников проектной группы."
        )

    p_body.paragraph_format.line_spacing = line_sp
    p_body.paragraph_format.first_line_indent = indent_val
    for r in p_body.runs:
        r.font.name = font_name
        r.font.size = font_size

    if kind in ("Приказ", "Распоряжение"):
        p_ctrl = doc.add_paragraph("2. Контроль за исполнением настоящего распорядительного документа оставляю за собой.")
        p_ctrl.paragraph_format.line_spacing = line_sp
        p_ctrl.paragraph_format.first_line_indent = indent_val
        for r in p_ctrl.runs:
            r.font.name = font_name
            r.font.size = font_size

    # Signature paragraph (omitted if with_defects)
    if not with_defects:
        if kind == "Протокол":
            p_sign1 = doc.add_paragraph("Председатель комиссии                     (подпись)                     А.А. Андреев")
            p_sign1.paragraph_format.line_spacing = line_sp
            for r in p_sign1.runs:
                r.font.name = font_name
                r.font.size = font_size
            p_sign2 = doc.add_paragraph("Секретарь комиссии                        (подпись)                     Е.В. Васильева")
            p_sign2.paragraph_format.line_spacing = line_sp
            for r in p_sign2.runs:
                r.font.name = font_name
                r.font.size = font_size
        else:
            p_sign = doc.add_paragraph("Генеральный директор                     (подпись)                     А.А. Андреев")
            p_sign.paragraph_format.line_spacing = line_sp
            for r in p_sign.runs:
                r.font.name = font_name
                r.font.size = font_size

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestNovelDocumentsGeneralization(unittest.IsolatedAsyncioTestCase):
    """Independent generalization test suite testing complete handling of novel documents."""

    @classmethod
    def tearDownClass(cls):
        """Cleanup test artifacts from PostgreSQL and restore baseline state."""
        asyncio.run(cls._cleanup_test_artifacts())

    @classmethod
    async def _cleanup_test_artifacts(cls):
        """Clean all synthetic documents and audit entries created during tests."""
        async with async_session_factory() as session:
            test_codes = ["PIB-501", "DBO-12", "RKA-03", "IT-42", "SED-15", "SEC-101", "PROC-01", "NOVEL-TEST-DOC"]
            stmt = select(KnowledgeDocument).where(KnowledgeDocument.doc_code.in_(test_codes))
            docs = (await session.execute(stmt)).scalars().all()
            for d in docs:
                await session.delete(d)

            # Cleanup audit records for test queries
            await session.execute(
                delete(AuditLog).where(
                    (AuditLog.query_text.ilike("%PIB-501%"))
                    | (AuditLog.query_text.ilike("%DBO-12%"))
                    | (AuditLog.query_text.ilike("%RKA-03%"))
                    | (AuditLog.query_text.ilike("%IT-42%"))
                    | (AuditLog.query_text.ilike("%SED-15%"))
                    | (AuditLog.query_text.ilike("%SEC-101%"))
                    | (AuditLog.query_text.ilike("%парол%"))
                    | (AuditLog.query_text.ilike("%аквариумн%"))
                )
            )
            await session.commit()
        await engine.dispose()

    # =========================================================================
    # Group 1: Hot-Reload and Versioning of Novel Regulations
    # =========================================================================

    async def test_01_upload_pib_501_docx_hot_reload(self):
        """Upload novel DOCX 'ПИБ-501' v1.0 with 'internal' access level and verify immediate indexing."""
        docx_bytes = create_novel_pib_docx("1.0")
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            files = {
                "file": (
                    "PIB-501_v1.0.docx",
                    docx_bytes,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            }
            data = {
                "doc_code": "PIB-501",
                "title": "Политика информационной безопасности № ПИБ-501",
                "version": "1.0",
                "doc_type": "instruction",
                "access_level": "internal",
            }

            resp = await client.post(
                "/v1/documents/upload-version",
                files=files,
                data=data,
                headers={"X-User-Role": "dou_specialist"},
            )
            self.assertEqual(resp.status_code, 201)
            info = resp.json()
            self.assertEqual(info["doc_code"], "PIB-501")
            self.assertEqual(info["version"], "1.0")
            self.assertEqual(info["access_level"], "dsp")  # internal normalized to dsp
            self.assertTrue(info["is_active"])
            self.assertGreaterEqual(info["chunk_count"], 3)

        # Confirm chunks and tsvector in PostgreSQL
        async with async_session_factory() as session:
            doc_stmt = select(KnowledgeDocument).where(KnowledgeDocument.doc_code == "PIB-501", KnowledgeDocument.version == "1.0")
            doc = (await session.execute(doc_stmt)).scalar_one_or_none()
            self.assertIsNotNone(doc)
            self.assertTrue(doc.is_active)

            chunks_stmt = select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            chunks = (await session.execute(chunks_stmt)).scalars().all()
            self.assertGreaterEqual(len(chunks), 3)
            clauses = {c.clause for c in chunks}
            self.assertIn("2.1", clauses)

    async def test_02_upload_dbo_12_pdf_hot_reload(self):
        """Upload novel PDF 'ДБО-12' v1.0 with 'public' access and verify parsing of chapters/clauses."""
        pdf_bytes = create_novel_dbo_pdf()
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            files = {
                "file": (
                    "DBO-12_v1.0.pdf",
                    pdf_bytes,
                    "application/pdf",
                )
            }
            data = {
                "doc_code": "DBO-12",
                "title": "Регламент дистанционного банковского обслуживания № ДБО-12",
                "version": "1.0",
                "doc_type": "instruction",
                "access_level": "public",
            }

            resp = await client.post(
                "/v1/documents/upload-version",
                files=files,
                data=data,
                headers={"X-User-Role": "dou_specialist"},
            )
            self.assertEqual(resp.status_code, 201)
            info = resp.json()
            self.assertEqual(info["doc_code"], "DBO-12")
            self.assertEqual(info["access_level"], "public")
            self.assertTrue(info["is_active"])
            self.assertGreaterEqual(info["chunk_count"], 3)

    async def test_03_upload_rka_03_with_tables(self):
        """Upload novel DOCX 'РКА-03' containing tables and verify table data is indexed."""
        rka_bytes = create_novel_rka_docx_with_roles()
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            files = {
                "file": (
                    "RKA-03_v1.0.docx",
                    rka_bytes,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            }
            data = {
                "doc_code": "RKA-03",
                "title": "Регламент кадрового администрирования № РКА-03",
                "version": "1.0",
                "doc_type": "instruction",
                "access_level": "public",
            }

            resp = await client.post(
                "/v1/documents/upload-version",
                files=files,
                data=data,
                headers={"X-User-Role": "dou_specialist"},
            )
            self.assertEqual(resp.status_code, 201)
            info = resp.json()
            self.assertEqual(info["doc_code"], "RKA-03")
            self.assertGreaterEqual(info["chunk_count"], 2)

    async def test_04_upload_switch_version_rollback(self):
        """Upload PIB-501 v2.0, verify v1.0 archived, then test rollback via switch-version."""
        v2_bytes = create_novel_pib_docx("2.0")
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Upload v2.0
            resp_v2 = await client.post(
                "/v1/documents/upload-version",
                files={"file": ("PIB-501_v2.0.docx", v2_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"doc_code": "PIB-501", "title": "Политика информационной безопасности № ПИБ-501", "version": "2.0", "access_level": "dsp"},
                headers={"X-User-Role": "dou_specialist"},
            )
            self.assertEqual(resp_v2.status_code, 201)

            # 2. Check in DB: v2.0 is active, v1.0 is inactive
            async with async_session_factory() as session:
                doc_v1 = (await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.doc_code == "PIB-501", KnowledgeDocument.version == "1.0"))).scalar_one()
                doc_v2 = (await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.doc_code == "PIB-501", KnowledgeDocument.version == "2.0"))).scalar_one()
                self.assertFalse(doc_v1.is_active)
                self.assertTrue(doc_v2.is_active)

            # 3. Rollback to v1.0 via /documents/{doc_code}/switch-version/{version}
            resp_switch = await client.post(
                "/v1/documents/PIB-501/switch-version/1.0",
                headers={"X-User-Role": "dou_specialist"},
            )
            self.assertEqual(resp_switch.status_code, 200)
            switch_info = resp_switch.json()
            self.assertEqual(switch_info["version"], "1.0")
            self.assertTrue(switch_info["is_active"])

            # 4. Verify in DB that v1.0 is active and v2.0 is inactive
            async with async_session_factory() as session:
                doc_v1 = (await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.doc_code == "PIB-501", KnowledgeDocument.version == "1.0"))).scalar_one()
                doc_v2 = (await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.doc_code == "PIB-501", KnowledgeDocument.version == "2.0"))).scalar_one()
                self.assertTrue(doc_v1.is_active)
                self.assertFalse(doc_v2.is_active)

    async def test_05_switch_version_json_body_endpoint(self):
        """Verify version switching endpoint with JSON request body (/v1/documents/switch-version)."""
        token = create_access_token({"sub": "admin", "role": "admin"})
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/documents/switch-version",
                json={"doc_code": "PIB-501", "version": "2.0"},
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["doc_code"], "PIB-501")
            self.assertEqual(data["version"], "2.0")
            self.assertTrue(data["is_active"])

    async def test_06_multiversion_listing_catalog(self):
        """Verify GET /v1/documents/versions lists all uploaded editions with chunk counts."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/documents/versions")
            self.assertEqual(resp.status_code, 200)
            items = resp.json()
            pib_versions = [it for it in items if it["doc_code"] == "PIB-501"]
            dbo_versions = [it for it in items if it["doc_code"] == "DBO-12"]
            self.assertGreaterEqual(len(pib_versions), 2)  # v1.0 and v2.0
            self.assertGreaterEqual(len(dbo_versions), 1)

    # =========================================================================
    # Group 2: RAG, Semantic Search & RBAC Enforcement on Novel Documents
    # =========================================================================

    async def test_07_rag_retrieval_novel_document_clause_citation(self):
        """Ask specific question on novel regulation DBO-12 and verify exact clause citation."""
        async with async_session_factory() as session:
            sources = await retrieve_chunks(
                session=session,
                query="Какой максимальный срок обработки платежного поручения через шлюз ДБО по пункту 2.1?",
                user_role="employee",
                top_k=3,
            )
            self.assertGreater(len(sources), 0)
            top = sources[0]
            self.assertEqual(top.document_code, "DBO-12")
            self.assertIn("2.1", top.clause)
            self.assertIn("15 минут", top.quote or top.full_content)
            self.assertGreaterEqual(top.relevance_pct, 40.0)

    async def test_08_rag_rbac_employee_denied_dsp_novel_document(self):
        """Verify that user with 'employee' role cannot retrieve chunks from 'dsp' novel document PIB-501."""
        async with async_session_factory() as session:
            sources = await retrieve_chunks(
                session=session,
                query="Каковы правила смены паролей пользователей по пункту 2.1 Политики информационной безопасности ПИБ-501?",
                user_role="employee",
                top_k=5,
            )
            # Employee role must NOT receive any chunks from PIB-501 (which has dsp access level)
            pib_sources = [s for s in sources if s.document_code == "PIB-501"]
            self.assertEqual(len(pib_sources), 0)

    async def test_09_rag_rbac_dou_specialist_and_auditor_allowed(self):
        """Verify that 'dou_specialist' and 'security_auditor' roles can access DSP document PIB-501."""
        async with async_session_factory() as session:
            for role in ("dou_specialist", "security_auditor", "admin"):
                sources = await retrieve_chunks(
                    session=session,
                    query="Каковы правила смены паролей пользователей по пункту 2.1 Политики информационной безопасности ПИБ-501?",
                    user_role=role,
                    top_k=3,
                )
                pib_sources = [s for s in sources if s.document_code == "PIB-501"]
                self.assertGreater(len(pib_sources), 0, f"Role {role} should have retrieved PIB-501 chunks")
                self.assertIn("2.1", pib_sources[0].clause)
                self.assertIn("90 календарных дней", pib_sources[0].quote or pib_sources[0].full_content)

    async def test_10_rag_grounded_answer_offline_fallback(self):
        """Verify offline answer synthesis generates grounded citation to novel document without hallucinating OD-184."""
        async with async_session_factory() as session:
            q = "Каков суточный лимит перевода средств без дополнительного OTP по регламенту ДБО-12?"
            sources = await retrieve_chunks(session=session, query=q, user_role="employee", top_k=2)
            self.assertGreater(len(sources), 0)
            self.assertEqual(sources[0].document_code, "DBO-12")

            answer = build_offline_fallback_answer(q, sources)
            self.assertIn("DBO-12", answer)
            self.assertIn("300 000", answer)
            self.assertIn("Основание:", answer)

    async def test_11_rag_roles_table_extraction_novel_document(self):
        """Verify role and committee composition extraction from table in novel document RKA-03."""
        async with async_session_factory() as session:
            q = "Кто входит в состав аттестационной комиссии по регламенту РКА-03?"
            sources = await retrieve_chunks(session=session, query=q, user_role="employee", top_k=3)
            self.assertGreater(len(sources), 0)
            rka_sources = [s for s in sources if s.document_code == "RKA-03"]
            self.assertGreater(len(rka_sources), 0)

            ans = build_offline_fallback_answer(q, sources)
            self.assertIn("Председатель", ans)
            self.assertIn("Секретарь", ans)
            self.assertIn("RKA-03", ans)

    # =========================================================================
    # Group 3: Compliance Normocontrol on Diverse Novel Documents (.docx)
    # =========================================================================

    async def test_12_compliance_exemplar_novel_order(self):
        """Flawless novel Order must receive high compliance score (90-100%) and passed=True."""
        doc_bytes = create_novel_document_bytes(kind="Приказ", with_defects=False)
        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, doc_bytes, "exemplar_order.docx")
            self.assertEqual(resp.detected_doc_kind, "Приказ")
            self.assertTrue(resp.passed)
            self.assertGreaterEqual(resp.score_pct, 90.0)
            self.assertEqual(resp.critical_count, 0)
            self.assertIsNotNone(resp.approval_recommendation)

    async def test_13_compliance_exemplar_novel_protocol(self):
        """Flawless novel Protocol must receive high score (90-100%) and passed=True."""
        doc_bytes = create_novel_document_bytes(kind="Протокол", with_defects=False)
        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, doc_bytes, "exemplar_protocol.docx")
            self.assertEqual(resp.detected_doc_kind, "Протокол")
            self.assertTrue(resp.passed)
            self.assertGreaterEqual(resp.score_pct, 90.0)
            self.assertEqual(resp.critical_count, 0)

    async def test_14_compliance_exemplar_novel_memo(self):
        """Flawless novel Internal Memo must receive high score (90-100%) and passed=True."""
        doc_bytes = create_novel_document_bytes(kind="Служебная записка", with_defects=False)
        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, doc_bytes, "exemplar_memo.docx")
            self.assertEqual(resp.detected_doc_kind, "Служебная записка")
            self.assertTrue(resp.passed)
            self.assertGreaterEqual(resp.score_pct, 90.0)
            self.assertEqual(resp.critical_count, 0)

    async def test_15_compliance_novel_order_with_defects(self):
        """Defective novel Order must be flagged with multiple specific rule violations."""
        doc_bytes = create_novel_document_bytes(kind="Приказ", with_defects=True)
        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, doc_bytes, "defective_order.docx")
            self.assertEqual(resp.detected_doc_kind, "Приказ")
            self.assertFalse(resp.passed)
            rule_ids = {iss.rule_id for iss in resp.issues}
            # Margins defect
            self.assertIn("CHK-MARG", rule_ids)
            # Font defect
            self.assertIn("CHK-FONT", rule_ids)
            # Line spacing defect
            self.assertIn("CHK-LINE", rule_ids)
            # Title trailing dot defect
            self.assertIn("CHK-TITLE", rule_ids)
            # Missing signature defect
            self.assertIn("CHK-SIGN", rule_ids)

    async def test_16_compliance_novel_autofix_remediation(self):
        """Auto-Fix routine must remediate formatting defects and generate compliant .docx."""
        doc_bytes = create_novel_document_bytes(kind="Приказ", with_defects=True)
        async with async_session_factory() as session:
            initial_resp = await check_docx_compliance(session, doc_bytes, "bad_draft.docx")
            self.assertFalse(initial_resp.passed)
            self.assertIsNotNone(initial_resp.fixed_file_url)

            # Retrieve generated fixed file from disk
            fixed_filename = Path(initial_resp.fixed_file_url).name
            fixed_filepath = settings.GENERATED_DOCS_DIR / fixed_filename
            self.assertTrue(fixed_filepath.exists())

            with open(fixed_filepath, "rb") as f:
                fixed_bytes = f.read()

            # Verify remediated document
            fixed_doc = docx.Document(io.BytesIO(fixed_bytes))
            section = fixed_doc.sections[0]
            self.assertAlmostEqual(section.left_margin.mm, 30.0, delta=1.0)
            self.assertAlmostEqual(section.right_margin.mm, 15.0, delta=1.0)
            self.assertAlmostEqual(section.top_margin.mm, 20.0, delta=1.0)

            # Re-check compliance of fixed document: margin, font, and spacing violations must be resolved
            rechecked_resp = await check_docx_compliance(session, fixed_bytes, fixed_filename)
            rechecked_rules = {iss.rule_id for iss in rechecked_resp.issues}
            self.assertNotIn("CHK-MARG", rechecked_rules)
            self.assertNotIn("CHK-FONT", rechecked_rules)
            self.assertNotIn("CHK-LINE", rechecked_rules)
            self.assertNotIn("CHK-TITLE", rechecked_rules)

    async def test_17_non_ord_contract_rejected_no_fake_route(self):
        """Sales Contract must NOT be falsely identified as 'Приказ' or 'Акт' and must have NO approval route."""
        doc_bytes = create_novel_document_bytes(non_ord_type="contract")
        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, doc_bytes, "договор_поставки.docx")
            self.assertNotIn(resp.detected_doc_kind, ["Приказ", "Распоряжение", "Акт"])
            self.assertEqual(resp.detected_doc_kind, "Неопознанный документ / Не является ОРД")
            self.assertIsNone(resp.approval_recommendation)
            self.assertIsNone(resp.fixed_file_url)
            self.assertFalse(resp.passed)
            self.assertLessEqual(resp.score_pct, 25.0)

    async def test_18_non_ord_technical_specification_rejected(self):
        """Technical Specification (ТЗ) must NOT receive ORD classification or approval route."""
        doc_bytes = create_novel_document_bytes(non_ord_type="tz")
        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, doc_bytes, "тех_задание.docx")
            self.assertNotIn(resp.detected_doc_kind, ["Приказ", "Распоряжение", "Акт"])
            self.assertEqual(resp.detected_doc_kind, "Неопознанный документ / Не является ОРД")
            self.assertIsNone(resp.approval_recommendation)
            self.assertFalse(resp.passed)

    async def test_19_non_ord_resume_and_report_rejected(self):
        """Candidate Resumes and Analytical Reports must be rejected as non-ORD."""
        resume_bytes = create_novel_document_bytes(non_ord_type="resume")
        report_bytes = create_novel_document_bytes(non_ord_type="report")
        async with async_session_factory() as session:
            for b, name in [(resume_bytes, "резюме.docx"), (report_bytes, "отчет.docx")]:
                resp = await check_docx_compliance(session, b, name)
                self.assertNotIn(resp.detected_doc_kind, ["Приказ", "Распоряжение", "Акт"])
                self.assertEqual(resp.detected_doc_kind, "Неопознанный документ / Не является ОРД")
                self.assertIsNone(resp.approval_recommendation)
                self.assertFalse(resp.passed)

    # =========================================================================
    # Group 4: Conversational Variability, Slang, Typos & Zero-Hallucination Guard
    # =========================================================================

    async def test_20_query_conversational_and_slang(self):
        """Colloquial query with conversational filler and slang properly retrieves novel regulation."""
        async with async_session_factory() as session:
            req = QueryRequest(
                query="Подскажи, пожалуйста, за скока дней юзеру нужно сменить пароль по инфобезопасности?",
                user_role="dou_specialist",
            )
            resp = await process_query(session, req, llm_client=MockFastOllamaClient())
            self.assertFalse(resp.zero_hallucination_triggered)
            self.assertGreater(len(resp.sources), 0)
            top_src = resp.sources[0]
            self.assertEqual(top_src.document_code, "PIB-501")
            self.assertIn("90 календарных дней", resp.answer)

    async def test_21_query_with_typos(self):
        """Query with typos ('перриодичность', 'смеены', 'пааролей') successfully matched via trigram/FTS."""
        async with async_session_factory() as session:
            req = QueryRequest(
                query="Какая перриодичность смеены пааролей установлена по ПИБ-501?",
                user_role="dou_specialist",
            )
            resp = await process_query(session, req, llm_client=MockFastOllamaClient())
            self.assertFalse(resp.zero_hallucination_triggered)
            self.assertGreater(len(resp.sources), 0)
            self.assertEqual(resp.sources[0].document_code, "PIB-501")

    async def test_22_query_two_part_question(self):
        """Compound two-part question avoids coverage dilution and retrieves both aspects."""
        async with async_session_factory() as session:
            req = QueryRequest(
                query="Каков максимальный срок обработки платежного поручения через ДБО и какой суточный лимит?",
                user_role="employee",
            )
            resp = await process_query(session, req, llm_client=MockFastOllamaClient())
            self.assertFalse(resp.zero_hallucination_triggered)
            self.assertGreater(len(resp.sources), 0)
            codes = {s.document_code for s in resp.sources}
            self.assertIn("DBO-12", codes)

    async def test_23_zero_hallucination_guard_unrelated_queries(self):
        """Completely out-of-domain queries must reliably trigger Zero-Hallucination Guard refusal."""
        async with async_session_factory() as session:
            unrelated = [
                "Как правильно ухаживать за аквариумными рыбками скаляриями?",
                "Какая средняя температура поверхности планеты Венера?",
                "Как приготовить венский шоколадный торт Захер?",
            ]
            for uq in unrelated:
                req = QueryRequest(query=uq, user_role="employee")
                resp = await process_query(session, req, llm_client=MockFastOllamaClient())
                self.assertTrue(resp.zero_hallucination_triggered, f"Query '{uq}' should have triggered guard")
                self.assertEqual(resp.answer, ZERO_HALLUCINATION_REFUSAL)
                self.assertEqual(len(resp.sources), 0)
                self.assertIsNone(resp.approval_recommendation)

    async def test_24_generic_code_transliteration_unseen_regulations(self):
        """Verify generic transliteration handles unseen codes (IT-42, SED-15, SEC-101) without hardcoded prefixes."""
        from src.core.retriever import generate_code_variants

        it_vars = generate_code_variants("ИТ-42")
        self.assertIn("it-42", it_vars)
        self.assertIn("it42", it_vars)
        self.assertIn("ит-42", it_vars)

        sed_vars = generate_code_variants("SED-15")
        self.assertTrue(any("сед" in v or "сэд" in v for v in sed_vars))
        self.assertIn("sed-15", sed_vars)

        sec_vars = generate_code_variants("SEC-101")
        self.assertTrue(any("сек" in v for v in sec_vars))
        self.assertIn("sec-101", sec_vars)

    async def test_25_mixed_homoglyphs_code_query_tolerance(self):
        """Query with mixed keyboard layout homoglyphs (Cyrillic 'Р' in 'РIB-501') resolves to regulation."""
        # 'Р' is Cyrillic \u0420, 'IB' is Latin
        mixed_code = "\u0420IB-501"
        async with async_session_factory() as session:
            req = QueryRequest(
                query=f"Каковы правила по регламенту {mixed_code}?",
                user_role="dou_specialist",
            )
            resp = await process_query(session, req, llm_client=MockFastOllamaClient())
            self.assertFalse(resp.zero_hallucination_triggered)
            self.assertGreater(len(resp.sources), 0)
            self.assertEqual(resp.sources[0].document_code, "PIB-501")

    async def test_26_upload_empty_docx_and_pdf_rejected_with_400(self):
        """Uploading empty DOCX (0 text) or blank PDF rejected with 400 without deactivating existing active versions."""
        # Create empty DOCX with zero text
        empty_doc = docx.Document()
        empty_buf = io.BytesIO()
        empty_doc.save(empty_buf)
        empty_docx_bytes = empty_buf.getvalue()

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/documents/upload-version",
                files={"file": ("blank.docx", empty_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"doc_code": "PIB-501", "title": "Пустая версия", "version": "99.0", "access_level": "dsp"},
                headers={"X-User-Role": "dou_specialist"},
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("contains no extractable text", resp.json()["detail"])

        # Confirm previously active PIB-501 remains active
        async with async_session_factory() as session:
            stmt = select(KnowledgeDocument).where(KnowledgeDocument.doc_code == "PIB-501", KnowledgeDocument.is_active.is_(True))
            active_doc = (await session.execute(stmt)).scalar_one_or_none()
            self.assertIsNotNone(active_doc)
            self.assertNotEqual(active_doc.version, "99.0")

    async def test_27_upload_corrupt_binary_disguised_as_docx_rejected(self):
        """Random binary garbage disguised as .docx is rejected with 400 Bad Request."""
        garbage_bytes = b"NOT_A_REAL_DOCX_FILE_RANDOM_BYTES_0123456789"
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/documents/upload-version",
                files={"file": ("fake.docx", garbage_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"doc_code": "NOVEL-TEST-DOC", "title": "Фейк", "version": "1.0", "access_level": "public"},
                headers={"X-User-Role": "dou_specialist"},
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("Failed to open DOCX", resp.json()["detail"])

    async def test_28_non_ord_agreements_and_proposals_rejected(self):
        """Corporate Agreements (Соглашение) and Commercial Proposals rejected as non-ORD with no route."""
        doc_agr = docx.Document()
        doc_agr.add_paragraph("СОГЛАШЕНИЕ О КОНФИДЕНЦИАЛЬНОСТИ И НЕРАЗГЛАШЕНИИ ИНФОРМАЦИИ (NDA)")
        doc_agr.add_paragraph("г. Москва                                                    24 октября 2026 г.")
        doc_agr.add_paragraph("1. Стороны обязуются соблюдать конфиденциальность сведений.")
        doc_agr.add_paragraph("Подписи сторон: Генеральный директор А.А. Андреев")
        agr_buf = io.BytesIO()
        doc_agr.save(agr_buf)

        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, agr_buf.getvalue(), "nda_agreement.docx")
            self.assertEqual(resp.detected_doc_kind, "Неопознанный документ / Не является ОРД")
            self.assertIsNone(resp.approval_recommendation)
            self.assertFalse(resp.passed)

    async def test_29_order_nonstandard_numbering_compliant(self):
        """Novel Order starting with 'ПРИКАЗ N 42-П (ПРОЕКТ)' properly recognized as ORD Order."""
        doc = docx.Document()
        for s in doc.sections:
            s.left_margin = Mm(30)
            s.right_margin = Mm(15)
            s.top_margin = Mm(20)
            s.bottom_margin = Mm(20)

        p_org = doc.add_paragraph("НАИМЕНОВАНИЕ ОРГАНИЗАЦИИ")
        p_kind = doc.add_paragraph("ПРИКАЗ N 42-П (ПРОЕКТ)")
        p_title = doc.add_paragraph("О модернизации серверной инфраструктуры")
        p_body = doc.add_paragraph(
            "В целях повышения отказоустойчивости корпоративных сервисов приказываю "
            "Департаменту информационных технологий провести плановую замену сетевых коммутаторов."
        )
        p_body.paragraph_format.first_line_indent = Cm(1.25)
        p_sign = doc.add_paragraph("Генеральный директор                     (подпись)                     А.А. Андреев")

        for p in [p_org, p_kind, p_title, p_body, p_sign]:
            p.paragraph_format.line_spacing = 1.15
            for r in p.runs:
                r.font.name = "Times New Roman"
                r.font.size = Pt(13)

        buf = io.BytesIO()
        doc.save(buf)

        async with async_session_factory() as session:
            resp = await check_docx_compliance(session, buf.getvalue(), "order_n42.docx")
            self.assertEqual(resp.detected_doc_kind, "Приказ")
            self.assertTrue(resp.passed)
            self.assertIsNotNone(resp.approval_recommendation)

    async def test_30_table_role_extraction_without_synthetic_text(self):
        """Table role extraction works directly from structured table rows without requiring synthetic marker lines."""
        from src.core.llm_client import extract_roles_from_sources
        from src.schemas.api_models import SourceRef

        table_content = (
            "Положение о конкурсной комиссии по закупкам.\n"
            "Роль в комиссии | Должностное лицо | Полномочия\n"
            "Председатель конкурсной комиссии | Заместитель директора | Руководство заседанием\n"
            "Секретарь конкурсной комиссии | Ведущий специалист | Ведение протокола\n"
            "Член конкурсной комиссии | Эксперт по безопасности | Оценка предложений\n"
        )
        sources = [
            SourceRef(
                document_code="PROC-01",
                document_title="Положение о закупках",
                chapter="Раздел 3",
                clause="3.1",
                page_number=1,
                quote=table_content,
                full_content=table_content,
                relevance_pct=85.0,
                version="1.0",
                access_level="public",
            )
        ]
        roles = extract_roles_from_sources(sources, query="Кто входит в состав комиссии по закупкам?")
        self.assertIn("Председатель конкурсной комиссии", roles)
        self.assertIn("Секретарь конкурсной комиссии", roles)
        self.assertIn("Член конкурсной комиссии", roles)

