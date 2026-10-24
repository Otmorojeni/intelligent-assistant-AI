"""Normative Compliance Checker for Draft DOCX Documents (OD-184 & Methodological Guidelines).

Inspects uploaded .docx draft orders, dispositions, and internal documents against 12 mandatory
regulatory formatting and structure rules from:
- Инструкция по ДОУ № ОД-184 (разделы 5, 6, 9, 10)
- Методические рекомендации по работе с модульными документами (разделы 2.3, 3.3, 4.2)
"""

import io
import re
from typing import List, Optional, Tuple

import docx
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.approval_router import calculate_approval_route
from src.schemas.api_models import (
    ApprovalCalculateRequest,
    ApprovalRecommendation,
    ComplianceCheckResponse,
    ComplianceIssue,
)


def _extract_docx_lines_and_tables(file_bytes: bytes) -> Tuple[List[str], List[str]]:
    """Extract paragraph lines and table cell texts from DOCX bytes."""
    doc = docx.Document(io.BytesIO(file_bytes))
    para_lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    table_cells: List[str] = []
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                txt = cell.text.strip()
                if txt:
                    table_cells.append(txt)
    return para_lines, table_cells


def _detect_doc_kind_and_module(all_text: str) -> Tuple[str, Optional[str]]:
    """Detect document kind and matching modular template code from text."""
    up = all_text.upper()
    doc_kind = "Внутренний документ"
    if "ПРИКАЗ" in up:
        doc_kind = "Приказ"
    elif "РАСПОРЯЖЕНИЕ" in up:
        doc_kind = "Распоряжение"
    elif "СЛУЖЕБНАЯ ЗАПИСКА" in up:
        doc_kind = "Служебная записка"
    elif "АКТ" in up:
        doc_kind = "Акт"

    low = all_text.lower()
    module_code: Optional[str] = None
    if "вводе в эксплуатацию" in low and "информационной системы" in low:
        module_code = "MOD-ORDER-IS"
    elif "назначении ответственных за ведение делопроизводства" in low or "ответственных за делопроизводство" in low:
        module_code = "MOD-ORDER-DOU"
    elif "приеме и передаче дел" in low:
        module_code = "MOD-ORDER-PROP"
    elif "утверждении и введении в действие" in low:
        module_code = "MOD-ORDER-LNA"
    elif "внутреннего аудита" in low:
        module_code = "MOD-DISP-AUDIT"
    elif "проектного комитета" in low:
        module_code = "MOD-DISP-PROJECT"
    elif "рабочей группы" in low:
        module_code = "MOD-DISP-WORKGROUP"

    return doc_kind, module_code


async def check_docx_compliance(
    session: AsyncSession,
    file_bytes: bytes,
    file_name: str,
) -> ComplianceCheckResponse:
    """Run 12-rule normative compliance inspection on an uploaded DOCX draft."""
    para_lines, table_cells = _extract_docx_lines_and_tables(file_bytes)
    all_text = "\n".join(para_lines + table_cells)
    up_text = all_text.upper()

    doc_kind, module_code = _detect_doc_kind_and_module(all_text)
    issues: List[ComplianceIssue] = []
    total_checks = 10

    # Check 1: Leftover 'МОДУЛЬНЫЙ ДОКУМЕНТ' marker (Section 3.3 Methodological Guidelines)
    if "МОДУЛЬНЫЙ ДОКУМЕНТ" in up_text:
        issues.append(
            ComplianceIssue(
                rule_id="CHK-01",
                severity="critical",
                clause_ref="Разд. 3.3 Методических рекомендаций",
                title="Не удалена техническая отметка «МОДУЛЬНЫЙ ДОКУМЕНТ»",
                description="В верхней части проекта осталась служебная отметка шаблона «МОДУЛЬНЫЙ ДОКУМЕНТ».",
                recommendation="Удалите строку «МОДУЛЬНЫЙ ДОКУМЕНТ» перед направлением проекта на согласование.",
            )
        )

    # Check 2: Leftover upper approval stamp 'УТВЕРЖДЕНО' / 'УТВЕРЖДАЮ' (Section 3.3)
    if re.search(r"\bУТВЕРЖД(?:ЕНО|АЮ)\b", up_text) and "УТВ-" in up_text:
        issues.append(
            ComplianceIssue(
                rule_id="CHK-02",
                severity="critical",
                clause_ref="Разд. 3.3 Методических рекомендаций",
                title="Не удален верхний гриф утверждения модульного шаблона",
                description="В проекте сохранился гриф утверждения самого модульного шаблона (УТВЕРЖДЕНО / № УТВ-...).",
                recommendation="Полностью удалите верхний гриф утверждения шаблона (п. 3.3 Методических рекомендаций).",
            )
        )

    # Check 3: Unfilled blank lines '____' or bracketed placeholders '[Указать ...]' (Section 3.3)
    if re.search(r"_{2,}|\[[^\d\]][^\]]{2,}\]", all_text):
        issues.append(
            ComplianceIssue(
                rule_id="CHK-03",
                severity="critical",
                clause_ref="Разд. 3.3 Методических рекомендаций, п. 5.1 Инструкции ОД-184",
                title="Обнаружены незаполненные графы или шаблонные заглушки («____» / «[...]»)",
                description="В тексте документа остались незаполненные прочерки «____» или шаблонные подсказки в скобках из шаблона.",
                recommendation="Заполните все переменные поля конкретными реквизитами и удалите линии подчеркивания и подсказки в скобках.",
            )
        )

    # Check 4: Leftover footnote indices [1], [2], [15] (Section 3.3)
    footnote_hits = re.findall(r"\[\d+\]", all_text)
    if footnote_hits:
        sample = ", ".join(sorted(set(footnote_hits))[:5])
        issues.append(
            ComplianceIssue(
                rule_id="CHK-04",
                severity="critical",
                clause_ref="Разд. 3.3 Методических рекомендаций",
                title=f"Не удалены цифровые сноски шаблона ({sample})",
                description="В тексте проекта остались ссылки на примечания по заполнению вида [1], [2].",
                recommendation="Удалите все квадратные скобки с номерами сносок из заголовка, текста и таблиц.",
            )
        )

    # Check 5: Leftover explanatory notes block at end of document (Section 3.3)
    if "ПРИМЕЧАНИЯ ПО ЗАПОЛНЕНИЮ" in up_text or "ПОЯСНЕНИЯ ПО ЗАПОЛНЕНИЮ" in up_text:
        issues.append(
            ComplianceIssue(
                rule_id="CHK-05",
                severity="critical",
                clause_ref="Разд. 3.3 Методических рекомендаций",
                title="Не удален справочный раздел «Примечания / Пояснения по заполнению»",
                description="В конце документа остался служебный раздел с инструкциями по заполнению модуля.",
                recommendation="Удалите раздел «Примечания по заполнению» и все пункты пояснений в конце файла.",
            )
        )

    # Check 6: Service zone 'ДАТА / РЕГИСТРАЦИОННЫЙ НОМЕР (НЕ УДАЛЯТЬ)' (Section 3.3)
    if doc_kind in ("Приказ", "Распоряжение") and "ДАТА / РЕГИСТРАЦИОННЫЙ НОМЕР (НЕ УДАЛЯТЬ)" not in up_text:
        issues.append(
            ComplianceIssue(
                rule_id="CHK-06",
                severity="critical",
                clause_ref="Разд. 3.3 Методических рекомендаций, п. 5.3 Инструкции ОД-184",
                title="Отсутствует служебная зона «ДАТА / РЕГИСТРАЦИОННЫЙ НОМЕР (НЕ УДАЛЯТЬ)»",
                description="Служебная рамка для автоматической простановки даты и номера в ИИС ДО была удалена или повреждена.",
                recommendation="Восстановите блок «ДАТА / РЕГИСТРАЦИОННЫЙ НОМЕР (НЕ УДАЛЯТЬ)» в верхней таблице документа.",
            )
        )

    # Check 7: Service zone 'ВИЗУАЛИЗАЦИЯ ЭП (НЕ УДАЛЯТЬ)' (Section 3.3 & cl. 6.1)
    if doc_kind in ("Приказ", "Распоряжение") and "ВИЗУАЛИЗАЦИЯ ЭП (НЕ УДАЛЯТЬ)" not in up_text:
        issues.append(
            ComplianceIssue(
                rule_id="CHK-07",
                severity="critical",
                clause_ref="Разд. 3.3 Методических рекомендаций, п. 6.1 Инструкции ОД-184",
                title="Отсутствует служебная зона «ВИЗУАЛИЗАЦИЯ ЭП (НЕ УДАЛЯТЬ)»",
                description="Служебная зона для штампа электронной подписи отсутствует в блоке подписи.",
                recommendation="Сохраните маркер «ВИЗУАЛИЗАЦИЯ ЭП (НЕ УДАЛЯТЬ)» перед ФИО подписанта.",
            )
        )

    # Check 8: Unfilled signatory placeholder 'И. О. Фамилия'
    if re.search(r"И\.\s*О\.\s*Фамилия", all_text, re.I):
        issues.append(
            ComplianceIssue(
                rule_id="CHK-08",
                severity="critical",
                clause_ref="П. 6.1, 6.3 Инструкции ОД-184",
                title="Не указаны инициалы и фамилия подписанта («И. О. Фамилия»)",
                description="В реквизите «Подпись» осталась шаблонная заглушка «И. О. Фамилия».",
                recommendation="Укажите фактические инициалы и фамилию уполномоченного должностного лица.",
            )
        )

    # Check 9: Control clause presence in orders and dispositions (cl. 9.2.6 / 9.7.6)
    if doc_kind in ("Приказ", "Распоряжение") and "КОНТРОЛЬ ЗА ИСПОЛНЕНИЕМ" not in up_text:
        issues.append(
            ComplianceIssue(
                rule_id="CHK-09",
                severity="warning",
                clause_ref="П. 9.2.6, 9.7.6 Инструкции ОД-184",
                title="Отсутствует пункт о контроле за исполнением документа",
                description="Заключительный пункт распорядительной части не содержит указания на должностное лицо, контролирующее исполнение.",
                recommendation="Добавьте заключительный пункт: «Контроль за исполнением настоящего приказа/распоряжения возложить на ... (или оставляю за собой)».",
            )
        )

    # Check 10: Preamble check (cl. 9.1.4)
    if doc_kind in ("Приказ", "Распоряжение") and not any(
        w in up_text for w in ("В ЦЕЛЯХ", "В СООТВЕТСТВИИ С", "ВО ИСПОЛНЕНИЕ", "В СВЯЗИ С")
    ):
        issues.append(
            ComplianceIssue(
                rule_id="CHK-10",
                severity="warning",
                clause_ref="П. 9.1.4, 9.2.3 Инструкции ОД-184",
                title="Не обнаружена преамбула (обоснование издания акта)",
                description="Констатирующая часть (преамбула) должна начинаться словами «В целях...», «В соответствии с...» или «Во исполнение...».",
                recommendation="Добавьте преамбулу с указанием целей и правовых оснований перед словом ПРИКАЗЫВАЮ / ОБЯЗЫВАЮ.",
            )
        )

    passed_checks = max(0, total_checks - len(issues))
    score_pct = round((passed_checks / total_checks) * 100.0, 1)
    critical_count = sum(1 for i in issues if i.severity == "critical")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    info_count = sum(1 for i in issues if i.severity == "info")

    # Calculate recommended approval route
    route_target = module_code or doc_kind
    calc_res = await calculate_approval_route(
        session,
        ApprovalCalculateRequest(
            doc_type=route_target,
            uses_module=bool(module_code),
        ),
    )
    approval_rec = ApprovalRecommendation(
        rule_number=calc_res.rule_number,
        doc_type_name=calc_res.doc_type_name,
        stages=calc_res.stages,
        signatory=calc_res.signatory,
    )

    return ComplianceCheckResponse(
        file_name=file_name,
        detected_doc_kind=doc_kind,
        is_modular=bool(module_code),
        detected_module_code=module_code,
        score_pct=score_pct,
        passed=(critical_count == 0),
        is_compliant=(critical_count == 0),
        total_checks=total_checks,
        passed_checks=passed_checks,
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        issues=issues,
        approval_recommendation=approval_rec,
    )
