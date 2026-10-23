"""Approval Router: Rule-based & DB-backed Approval Matrix Decision Engine.

Implements all approval rules from 'Матрица_обязательного_визирования_внутренних_и_внешних_документов.docx'
and the mandatory sequential workflow from Section 4.2 of 'Методические_рекомендации...docx'.

Stages of Approval Workflow:
- Stage 1: Responsible Executor + Initiator Department Head (initiator_department)
- Stage 2: Mandatory Agreeing Departments per Matrix with justification (reason):
    * Legal Department (requires_legal=True)
    * Department of DOU (all internal & external documents)
    * HR Department (weekend orders, affairs transfer, material aid, working groups)
    * InfoSec Department (IS orders, or affairs transfer when involves_infosec_access=True)
    * IT Department (IS orders, or working groups when involves_it=True)
    * Regional DOU Service (external letters to Russian entities when involves_regional=True)
    * Internal Control Department / International Cooperation Department (authorities / foreign entities)
- Stage 3: Linguistic Expertise (Proofreader of DOU Department) per Section 4.2
- Stage 4: DOU Department Visa (format, template module & route verification) per Section 4.2
- Stage 5: Signatory (Chairperson, Deputy Chairperson, Department Head) and Registration in IIS DO
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ApprovalRule
from src.schemas.api_models import (
    ApprovalCalculateRequest,
    ApprovalCalculateResponse,
    ApprovalRecommendation,
    ApprovalRuleItem,
    ApprovalStage,
)

logger = logging.getLogger(__name__)

# Canonical fallback rules if DB is temporarily empty during offline testing
CANONICAL_FALLBACK_RULES: List[Dict[str, Any]] = [
    {
        "rule_number": 1,
        "category": "internal",
        "doc_type_name": "Приказы о работе в выходные и нерабочие праздничные дни, а также по иным вопросам рабочего календаря, подготовленные с использованием модульных документов",
        "is_modular": True,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": True,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Кадровое подразделение.",
        "signatory": "Руководство Организации / Заместитель Председателя",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ", "Кадровое подразделение"]},
    },
    {
        "rule_number": 2,
        "category": "internal",
        "doc_type_name": "Приказы о приеме и передаче дел и имущества при назначении, освобождении от должности, реорганизации и иных кадровых изменениях (без изменения доступа к ИС), подготовленные с использованием модульных документов",
        "is_modular": True,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": True,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Стандартный маршрут: Юридическое подразделение, Департамент ДОУ, Кадровое подразделение (без затрагивания прав доступа к ИС).",
        "signatory": "Руководство Организации / Руководитель подразделения",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ", "Кадровое подразделение"], "involves_infosec_access": False},
    },
    {
        "rule_number": 3,
        "category": "internal",
        "doc_type_name": "Приказы о приеме и передаче дел и имущества при назначении, освобождении от должности, реорганизации и иных кадровых изменениях (с изменением доступа к ИС), подготовленные с использованием модульных документов",
        "is_modular": True,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": True,
        "requires_infosec": "yes",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Департамент информационной безопасности визирует проект, если прием и передача дел связаны с предоставлением, изменением или прекращением доступа к информационным системам.",
        "signatory": "Руководство Организации / Руководитель подразделения",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ", "Кадровое подразделение", "Департамент информационной безопасности"], "involves_infosec_access": True},
    },
    {
        "rule_number": 4,
        "category": "internal",
        "doc_type_name": "Приказы по вопросам информационных систем, включая ввод в эксплуатацию, вывод из эксплуатации, опытную эксплуатацию, изменение компонентов и иные связанные вопросы, подготовленные с использованием модульных документов",
        "is_modular": True,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": False,
        "requires_infosec": "yes",
        "requires_it": "yes",
        "requires_regional": "no",
        "condition_description": "Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент информационной безопасности, Департамент информационных технологий.",
        "signatory": "Руководство Организации / Заместитель Председателя",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ", "Департамент информационной безопасности", "Департамент информационных технологий"], "involves_it": True, "involves_infosec_access": True},
    },
    {
        "rule_number": 5,
        "category": "internal",
        "doc_type_name": "Прочие приказы, в т.ч., подготовленные без использования модульных документов или с использованием модульных документов кроме указанных в пп.1-3 (включая назначение ответственных за ДОУ и утверждение ЛНА)",
        "is_modular": False,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": False,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Обязательное визирование: Юридическое подразделение, Департамент ДОУ. Подразделение, компетенция которого затрагивается, включается в маршрут независимо от отдельной отметки.",
        "signatory": "Руководство Организации",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ"]},
    },
    {
        "rule_number": 6,
        "category": "internal",
        "doc_type_name": "Распоряжения о предоставлении материальной помощи и осуществлении иных выплат работникам",
        "is_modular": False,
        "requires_legal": False,
        "requires_dou": True,
        "requires_hr": True,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Визируется Департаментом ДОУ и Кадровым подразделением. Юридическое подразделение не требуется.",
        "signatory": "Руководство Организации / Заместитель Председателя",
        "extra_info": {"departments": ["Департамент ДОУ", "Кадровое подразделение"]},
    },
    {
        "rule_number": 7,
        "category": "internal",
        "doc_type_name": "Распоряжения о создании рабочих групп, проектных комитетов, комиссий и иных временных объединений (общего профиля)",
        "is_modular": True,
        "requires_legal": False,
        "requires_dou": True,
        "requires_hr": True,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Визируется Департаментом ДОУ и Кадровым подразделением (если объединение не связано с ИТ-проектами).",
        "signatory": "Руководство Организации / Курирующий Заместитель Председателя",
        "extra_info": {"departments": ["Департамент ДОУ", "Кадровое подразделение"], "involves_it": False},
    },
    {
        "rule_number": 8,
        "category": "internal",
        "doc_type_name": "Распоряжения о создании рабочих групп, проектных комитетов, комиссий и иных временных объединений для реализации ИТ-проектов или вопросов ИС",
        "is_modular": True,
        "requires_legal": False,
        "requires_dou": True,
        "requires_hr": True,
        "requires_infosec": "no",
        "requires_it": "yes",
        "requires_regional": "no",
        "condition_description": "Департамент информационных технологий визирует проект, если временное объединение создается для реализации ИТ-проекта или решения вопросов информационных систем.",
        "signatory": "Руководство Организации / Курирующий Заместитель Председателя",
        "extra_info": {"departments": ["Департамент ДОУ", "Кадровое подразделение", "Департамент информационных технологий"], "involves_it": True},
    },
    {
        "rule_number": 9,
        "category": "internal",
        "doc_type_name": "Прочие распоряжения, подготовленные без использования модульных документов или с использованием модульных документов кроме указанных в пп.5-6 (включая проведение внутреннего аудита процессов)",
        "is_modular": False,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": False,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Обязательное визирование: Юридическое подразделение, Департамент ДОУ.",
        "signatory": "Руководство Организации / Руководитель подразделения",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ"]},
    },
    {
        "rule_number": 10,
        "category": "external",
        "doc_type_name": "Письма за подписью Руководства Организации, адресуемые органам государственной власти, Администрации Президента РФ, членам Совета Федерации, депутатам Государственной Думы, Аппарату Правительства РФ, Счетной палате РФ",
        "is_modular": False,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": False,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент внутреннего контроля.",
        "signatory": "Председатель Организации / Заместитель Председателя",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ", "Департамент внутреннего контроля"]},
    },
    {
        "rule_number": 11,
        "category": "external",
        "doc_type_name": "Письма за подписью Руководства Организации, адресуемые руководству иностранных организаций, центральных (национальных) банков иностранных государств, а также международных банков и иных международных организаций",
        "is_modular": False,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": False,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент международного сотрудничества.",
        "signatory": "Председатель Организации / Заместитель Председателя",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ", "Департамент международного сотрудничества"]},
    },
    {
        "rule_number": 12,
        "category": "external",
        "doc_type_name": "Письма российским юридическим лицам за подписью Руководства Организации или руководителей СП ЦА",
        "is_modular": False,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": False,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "no",
        "condition_description": "Обязательное визирование: Юридическое подразделение, Департамент ДОУ.",
        "signatory": "Руководство Организации / Руководитель СП",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ"], "involves_regional": False},
    },
    {
        "rule_number": 13,
        "category": "external",
        "doc_type_name": "Письма российским юридическим лицам за подписью руководства РО Организации (с участием региональных отделений)",
        "is_modular": False,
        "requires_legal": True,
        "requires_dou": True,
        "requires_hr": False,
        "requires_infosec": "no",
        "requires_it": "no",
        "requires_regional": "yes",
        "condition_description": "Визируется Юридическим подразделением, Департаментом ДОУ и службой документационного обеспечения РО Организации.",
        "signatory": "Руководитель РО Организации",
        "extra_info": {"departments": ["Юридическое подразделение", "Департамент ДОУ", "Подразделение ДОУ РО Организации"], "involves_regional": True},
    },
]


def _create_fallback_rule(data: Dict[str, Any]) -> ApprovalRule:
    """Instantiate ApprovalRule from canonical fallback dictionary."""
    rule = ApprovalRule()
    for k, v in data.items():
        setattr(rule, k, v)
    return rule


async def get_all_rules_from_db(session: AsyncSession) -> List[ApprovalRule]:
    """Retrieve all 13 approval rules from PostgreSQL database, with fallback to canonical records."""
    stmt = select(ApprovalRule).order_by(ApprovalRule.rule_number)
    res = await session.execute(stmt)
    rules = list(res.scalars().all())
    if not rules:
        logger.warning("No approval rules found in database; using canonical in-memory fallback.")
        rules = [_create_fallback_rule(d) for d in CANONICAL_FALLBACK_RULES]
    return rules


def resolve_matching_rule(
    rules: List[ApprovalRule],
    request: ApprovalCalculateRequest,
) -> Tuple[ApprovalRule, List[str], bool]:
    """Resolve the authoritative ApprovalRule based on request parameters and business logic.

    Returns:
        Tuple of (matched_rule, list_of_notes, is_modular_result)
    """
    rules_by_number: Dict[int, ApprovalRule] = {r.rule_number: r for r in rules}
    notes: List[str] = []

    raw_doc = (request.doc_type or "").strip()
    if not raw_doc:
        notes.append(
            "Тип документа не указан. Применен стандартный маршрут визирования для общих приказов (Правило 5)."
        )
        fallback = rules_by_number.get(5) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[4])
        return fallback, notes, False

    clean_doc = raw_doc.lower()

    is_order = any(w in clean_doc for w in ("приказ", "order", "mod-order", "утв-01", "утв-02", "утв-03", "утв-04"))
    is_disp = any(w in clean_doc for w in ("распоряжен", "disp", "mod-disp", "утв-05", "утв-06", "утв-07"))
    is_letter = any(w in clean_doc for w in ("письм", "letter"))

    # Handover of affairs, personnel, and property keywords
    has_prop_keywords = any(code in clean_doc for code in ("mod-order-prop", "утв-03", "order_prop")) or any(
        w in clean_doc
        for w in (
            "прием и передача",
            "приеме и передаче",
            "прием-передача",
            "приеме-передаче",
            "передаче дел",
            "передача дел",
            "дел и имущества",
            "приеме дел",
            "прием дел",
            "личному составу",
            "личный состав",
            "по личному составу",
            "кадровым изменениям",
            "кадровые изменения",
            "кадровых изменениях",
            "назначении на должность",
            "освобождении от должности",
            "по кадрам",
            "кадровый",
            "кадровым",
            "кадровых",
        )
    )

    # =========================================================================
    # CASE 1: Non-modular fallback if user explicitly specifies uses_module=False
    # =========================================================================
    if not request.uses_module:
        notes.append(
            "Документ оформлен без применения утвержденного модульного шаблона (uses_module=False). "
            "Применен маршрут обязательного визирования для немодульных документов."
        )

        # 1. External letters
        if is_letter or clean_doc in ("10", "11", "12", "13", "letter_authorities", "letter_international", "letter_regional", "letter_legal_entities"):
            if any(w in clean_doc for w in ("орган", "государствен", "президент", "правительств", "дума", "совет федерации", "сенатор", "депутат", "счетн", "минцифры", "минфин", "министерств", "ведомств", "федеральн", "служба", "агентство", "банк россии", "цб рф", "центробанк", "регулятор", "10", "letter_authorities")):
                rule = rules_by_number.get(10) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[9])
                notes.append("Обращение в орган государственной власти РФ: обязательно согласование с Департаментом внутреннего контроля (Правило 10).")
                return rule, notes, False
            # Foreign organizations & foreign banks (not Russian commercial banks)
            is_foreign = any(w in clean_doc for w in ("иностранн", "зарубежн", "международн", "foreign", "11", "letter_international", "мвф", "ебрр", "нацбанк")) or (
                "банк" in clean_doc and any(w in clean_doc for w in ("иностран", "зарубеж", "международ", "foreign"))
            )
            if is_foreign:
                rule = rules_by_number.get(11) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[10])
                notes.append("Международная корреспонденция: обязательно согласование с Департаментом международного сотрудничества (Правило 11).")
                return rule, notes, False
            if request.involves_regional or any(w in clean_doc for w in ("ро организац", "региональн", "филиал", "территориальн", "13", "letter_regional")):
                rule = rules_by_number.get(13) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[12])
                notes.append("Внешнее письмо подготовлено с участием РО: включено визирование подразделением ДОУ Регионального отделения (Правило 13).")
                return rule, notes, False
            rule = rules_by_number.get(12) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[11])
            return rule, notes, False

        # 2. Dispositions
        if is_disp or clean_doc in ("6", "7", "8", "9", "disp_material_aid", "disp_project", "disp_workgroup", "disp_audit"):
            if any(w in clean_doc for w in ("материальн", "матпомощ", "выплат", "пособи", "6", "disp_material_aid")):
                rule = rules_by_number.get(6) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[5])
                return rule, notes, False
            # Other non-modular dispositions -> Rule 9
            rule = rules_by_number.get(9) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[8])
            return rule, notes, False

        # 3. Orders and other internal documents -> Rule 5
        rule = rules_by_number.get(5) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[4])
        return rule, notes, False

    # =========================================================================
    # CASE 2: Document with uses_module=True
    # =========================================================================

    # 2.0 Check template module codes directly (УТВ-01 .. УТВ-07, MOD-ORDER-*, MOD-DISP-*)
    if any(code in clean_doc for code in ("mod-order-is", "утв-01")):
        rule = rules_by_number.get(4) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[3])
        notes.append("Проект приказа по информационной системе: обязательно согласование с ДИТ и ДИБ (Правило 4).")
        return rule, notes, True

    if any(code in clean_doc for code in ("mod-order-dou", "утв-02")):
        rule = rules_by_number.get(5) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[4])
        return rule, notes, True

    if any(code in clean_doc for code in ("mod-order-prop", "утв-03")):
        if request.involves_infosec_access:
            rule = rules_by_number.get(3) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[2])
            notes.append("Прием-передача дел затрагивает права доступа к ИС: включено согласование с Департаментом информационной безопасности (Правило 3).")
        else:
            rule = rules_by_number.get(2) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[1])
        return rule, notes, True

    if any(code in clean_doc for code in ("mod-order-lna", "утв-04")):
        rule = rules_by_number.get(5) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[4])
        return rule, notes, True

    if any(code in clean_doc for code in ("mod-disp-audit", "утв-05")):
        rule = rules_by_number.get(9) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[8])
        return rule, notes, True

    if any(
        code in clean_doc
        for code in (
            "mod-disp-project",
            "утв-06",
            "mod-disp-workgroup",
            "утв-07",
            "создании проектного комитета",
            "создании рабочей группы",
        )
    ):
        if request.involves_it:
            rule = rules_by_number.get(8) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[7])
            notes.append("Временное объединение создается для реализации ИТ-проекта или решения вопросов ИС: включено согласование с Департаментом информационных технологий (Правило 8).")
        else:
            rule = rules_by_number.get(7) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[6])
        return rule, notes, True

    # 2.1 Check for direct numeric rule number pattern (e.g. "4", "правило 4", "rule 4", "№ 4", "п. 4")
    if not any(prefix in clean_doc for prefix in ("утв", "mod-", "order-", "disp-", "letter-")):
        match_num = re.fullmatch(r"\s*(?:rule|правил[оа]|пункт|п\.|№|номер)?\s*(\d{1,2})\s*", clean_doc)
        if match_num:
            num = int(match_num.group(1))
            if 1 <= num <= 13:
                # Conditional promotion based on request flags
                if num == 2 and request.involves_infosec_access:
                    num = 3
                    notes.append("Прием-передача дел затрагивает права доступа к ИС: включено согласование с Департаментом информационной безопасности (Правило 3).")
                elif num == 7 and request.involves_it:
                    num = 8
                    notes.append("Временное объединение создается для реализации ИТ-проекта или решения вопросов ИС: включено согласование с Департаментом информационных технологий (Правило 8).")
                elif num == 12 and request.involves_regional:
                    num = 13
                    notes.append("Внешнее письмо подготовлено с участием РО: включено визирование подразделением ДОУ Регионального отделения (Правило 13).")

                target_rule = rules_by_number.get(num) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[num - 1])
                return target_rule, notes, target_rule.is_modular

    # 2.2 Handover of affairs and property -> Rule 3 (if infosec) or Rule 2 (without infosec)
    # Evaluated before general IS orders to prevent collision when handover involves IS access
    if has_prop_keywords:
        has_infosec = (
            request.involves_infosec_access
            or (
                (
                    "с доступом" in clean_doc
                    or "доступ" in clean_doc
                    or "правами" in clean_doc
                    or "учетн" in clean_doc
                    or "информационной безопасности" in clean_doc
                    or bool(re.search(r"\bис\b", clean_doc))
                    or "информационн" in clean_doc
                )
                and ("без доступа" not in clean_doc and "без изменения" not in clean_doc)
            )
        )
        if has_infosec:
            rule = rules_by_number.get(3) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[2])
            notes.append("Прием-передача дел затрагивает права доступа к ИС: включено согласование с Департаментом информационной безопасности (Правило 3).")
            return rule, notes, True
        else:
            rule = rules_by_number.get(2) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[1])
            return rule, notes, True

    # 2.2 Information systems order -> Rule 4
    has_is_keywords = (
        any(code in clean_doc for code in ("mod-order-is", "утв-01", "order_is", "order_it"))
        or (
            is_order
            and (
                "информационн" in clean_doc
                or bool(re.search(r"\b(ис|ит|it|is)\b", clean_doc))
                or any(
                    w in clean_doc
                    for w in (
                        "ввод в эксплуатацию",
                        "вывод из эксплуатации",
                        "опытная эксплуатация",
                        "опытную эксплуатацию",
                        "ввод ис",
                        "вводе ис",
                        "вывод ис",
                        "выводе ис",
                        "эксплуатаци",
                    )
                )
            )
        )
        or ("ввод" in clean_doc and (bool(re.search(r"\bис\b", clean_doc)) or "информационн" in clean_doc))
    )
    if has_is_keywords:
        rule = rules_by_number.get(4) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[3])
        notes.append("Проект приказа по информационной системе: обязательно согласование с ДИТ и ДИБ (Правило 4).")
        return rule, notes, True

    # 2.3 Weekend / working calendar order -> Rule 1
    if any(code in clean_doc for code in ("order_weekend", "weekend", "выходн", "праздничн", "календар", "нерабочие дни")):
        rule = rules_by_number.get(1) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[0])
        return rule, notes, True

    # 2.4 Working groups & project committees -> Rule 8 (if IT) or Rule 7 (general)
    has_wg_keywords = any(code in clean_doc for code in ("mod-disp-workgroup", "mod-disp-project", "утв-06", "утв-07", "disp_workgroup", "disp_project")) or any(
        w in clean_doc for w in ("рабоч", "комитет", "комисси", "временных объединений")
    )
    if has_wg_keywords:
        has_it = (
            request.involves_it
            or (
                (
                    bool(re.search(r"\b(ит|it|ис|is)\b", clean_doc))
                    or "информационн" in clean_doc
                    or "цифровизац" in clean_doc
                    or "программн" in clean_doc
                )
                and ("без ит" not in clean_doc and "без участия ит" not in clean_doc and "не связан" not in clean_doc)
            )
        )
        if has_it:
            rule = rules_by_number.get(8) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[7])
            notes.append("Временное объединение создается для реализации ИТ-проекта или решения вопросов ИС: включено согласование с Департаментом информационных технологий (Правило 8).")
            return rule, notes, True
        else:
            rule = rules_by_number.get(7) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[6])
            return rule, notes, True

    # 2.5 Material assistance disposition -> Rule 6
    if any(code in clean_doc for code in ("disp_material_aid", "material_aid", "материальн", "матпомощ", "выплат", "пособи")):
        rule = rules_by_number.get(6) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[5])
        return rule, notes, False

    # 2.6 Internal audit disposition -> Rule 9 (template УТВ-05)
    if any(code in clean_doc for code in ("mod-disp-audit", "утв-05", "disp_audit", "аудит", "проверк")):
        rule = rules_by_number.get(9) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[8])
        return rule, notes, True

    # 2.7 DOU appointment / LNA approved templates -> Rule 5 (modular templates УТВ-02, УТВ-04)
    if any(code in clean_doc for code in ("mod-order-dou", "утв-02", "order_dou", "делопроизводств", "назначении ответственных")) or (
        is_order and bool(re.search(r"\bдоу\b", clean_doc))
    ):
        rule = rules_by_number.get(5) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[4])
    if any(code in clean_doc for code in ("mod-order-lna", "утв-04", "order_lna", "локальн", "лна", "регламент", "положени", "инструкци")) or (
        is_order and bool(re.search(r"\bлна\b", clean_doc))
    ):
        rule = rules_by_number.get(5) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[4])
        return rule, notes, True
    # 2.7.1 Business trip and other general orders -> Rule 5
    if is_order and any(w in clean_doc for w in ("командиров", "командировании", "поездк", "прочие приказы", "прочий приказ")):
        rule = rules_by_number.get(5) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[4])
        return rule, notes, False

    # 2.8 External letters
    if is_letter or any(code in clean_doc for code in ("letter_authorities", "letter_international", "letter_regional", "letter_legal_entities")):
        if any(
            w in clean_doc
            for w in (
                "орган",
                "государствен",
                "президент",
                "правительств",
                "дума",
                "совет федерации",
                "сенатор",
                "депутат",
                "счетн",
                "минцифры",
                "минфин",
                "министерств",
                "ведомств",
                "федеральн",
                "служба",
                "агентство",
                "банк россии",
                "цб рф",
                "центробанк",
                "регулятор",
                "letter_authorities",
            )
        ):
            rule = rules_by_number.get(10) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[9])
            notes.append("Обращение в орган государственной власти РФ: обязательно согласование с Департаментом внутреннего контроля (Правило 10).")
            return rule, notes, False
        is_foreign = any(w in clean_doc for w in ("иностранн", "зарубежн", "международн", "foreign", "letter_international", "мвф", "ебрр", "нацбанк")) or (
            "банк" in clean_doc and any(w in clean_doc for w in ("иностран", "зарубеж", "международ", "foreign"))
        )
        if is_foreign:
            rule = rules_by_number.get(11) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[10])
            notes.append("Международная корреспонденция: обязательно согласование с Департаментом международного сотрудничества (Правило 11).")
            return rule, notes, False
        if request.involves_regional or any(w in clean_doc for w in ("ро организац", "региональн", "филиал", "территориальн", "letter_regional")):
            rule = rules_by_number.get(13) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[12])
            notes.append("Внешнее письмо подготовлено с участием РО: включено визирование подразделением ДОУ Регионального отделения (Правило 13).")
            return rule, notes, False
        rule = rules_by_number.get(12) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[11])
        return rule, notes, False

    # 2.9 General fuzzy matching against all rules with domain boosts
    best_rule: Optional[ApprovalRule] = None
    best_score = 0.0

    for rule in rules:
        rule_name = rule.doc_type_name.lower()
        score = float(fuzz.token_set_ratio(clean_doc, rule_name))

        if is_order:
            if rule_name.startswith("приказ") or "прочие приказы" in rule_name:
                score += 20.0
            else:
                score -= 30.0
        elif is_disp:
            if rule_name.startswith("распоряжен") or "прочие распоряжения" in rule_name:
                score += 20.0
            else:
                score -= 30.0
        elif is_letter:
            if rule_name.startswith("письм"):
                score += 20.0
            else:
                score -= 30.0

        if ("информационн" in clean_doc or bool(re.search(r"\b(ис|ит)\b", clean_doc))) and ("информационн" in rule_name or rule.requires_it != "no"):
            score += 25.0

        if any(w in clean_doc for w in ("личн", "кадр", "персонал", "должност")) and rule.rule_number in (2, 3):
            score += 35.0

        if rule.rule_number == 1 and not any(w in clean_doc for w in ("выходн", "праздничн", "календар", "нерабоч", "weekend")):
            score -= 35.0

        if rule.rule_number == 6 and not any(w in clean_doc for w in ("материальн", "матпомощ", "выплат", "пособи")):
            score -= 35.0

        if rule.rule_number in (7, 8) and not any(w in clean_doc for w in ("групп", "комитет", "комисси", "объединен", "workgroup", "project")):
            score -= 35.0

        if rule.rule_number == 10 and not any(w in clean_doc for w in ("орган", "государствен", "президент", "правительств", "дума", "совет федерации", "сенатор", "депутат", "счетн", "минцифры", "минфин", "министерств", "ведомств", "федеральн", "служба", "агентство", "банк россии", "цб", "центробанк", "регулятор")):
            score -= 35.0

        if rule.rule_number == 11 and not any(w in clean_doc for w in ("иностран", "зарубеж", "международ", "foreign", "мвф", "ебрр")):
            score -= 35.0

        if score > best_score:
            best_score = score
            best_rule = rule

    if best_rule:
        rule_num = best_rule.rule_number
        if rule_num == 2 and request.involves_infosec_access:
            rule_num = 3
        elif rule_num == 7 and request.involves_it:
            rule_num = 8
        elif rule_num == 12 and request.involves_regional:
            rule_num = 13
        matched = rules_by_number.get(rule_num, best_rule)
        return matched, notes, matched.is_modular

    # Default fallback
    if is_disp:
        rule = rules_by_number.get(9) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[8])
        return rule, notes, False
    rule = rules_by_number.get(5) or _create_fallback_rule(CANONICAL_FALLBACK_RULES[4])
    return rule, notes, False


def construct_approval_stages(
    rule: ApprovalRule,
    request: ApprovalCalculateRequest,
) -> List[ApprovalStage]:
    """Construct full sequential 5-stage approval route adhering to Section 4.2 of Guidelines.

    Stages:
    - Stage 1: Responsible Executor + Initiator Department Head (initiator_department)
    - Stage 2: Mandatory Agreeing Departments per Matrix with justification
    - Stage 3: Linguistic Expertise (Proofreader of DOU Department)
    - Stage 4: DOU Department Visa (checking template module, formatting and route)
    - Stage 5: Signatory (Chairperson, Deputy, Head) and IIS DO Registration
    """
    stages: List[ApprovalStage] = []
    order = 1
    initiator_dept = request.initiator_department or "Подразделение-инициатор"

    # =========================================================================
    # STAGE 1: Ответственный исполнитель + Руководитель подразделения-инициатора
    # =========================================================================
    stages.append(
        ApprovalStage(
            order=order,
            role_name="Ответственный исполнитель",
            department=initiator_dept,
            reason="Подготовка проекта документа и первичная проверка комплектности (п. 4.2 Методических рекомендаций)",
            is_mandatory=True,
        )
    )
    order += 1

    stages.append(
        ApprovalStage(
            order=order,
            role_name="Руководитель подразделения-инициатора",
            department=initiator_dept,
            reason="Непосредственный ведомственный контроль и согласование проекта руководителем подразделения-инициатора (п. 4.2 Методических рекомендаций)",
            is_mandatory=True,
        )
    )
    order += 1

    # =========================================================================
    # STAGE 2: Обязательные согласующие подразделения по Матрице
    # =========================================================================

    # 1. Юридическое подразделение (для всех документов, где requires_legal=True)
    if rule.requires_legal:
        stages.append(
            ApprovalStage(
                order=order,
                role_name="Юрист-эксперт",
                department="Юридическое подразделение",
                reason="Правовая экспертиза проекта документа и проверка соответствия законодательству РФ и нормативным актам",
                is_mandatory=True,
            )
        )
        order += 1

    # 2. Департамент ДОУ (обязательно для всех внутренних и внешних документов)
    if rule.requires_dou:
        stages.append(
            ApprovalStage(
                order=order,
                role_name="Специалист ДОУ",
                department="Департамент делопроизводства (ДОУ)",
                reason="Обязательное визирование документационного обеспечения управления по Матрице визирования",
                is_mandatory=True,
            )
        )
        order += 1

    # 3. Кадровое подразделение (для приказов по выходным дням, приему-передаче дел, распоряжений о матпомощи и рабочих группах)
    if rule.requires_hr:
        stages.append(
            ApprovalStage(
                order=order,
                role_name="Специалист по кадрам",
                department="Кадровое подразделение",
                reason="Согласование кадровых вопросов, режима рабочего времени, выплат или персонального состава объединения",
                is_mandatory=True,
            )
        )
        order += 1

    # 4. Департамент информационной безопасности
    # (для приказов по ИС, а также для приказов о приеме-передаче дел ПРИ УСЛОВИИ involves_infosec_access=True)
    requires_infosec = (
        rule.requires_infosec == "yes"
        or (rule.rule_number == 3 and request.involves_infosec_access)
        or (rule.rule_number == 4)
    )
    if requires_infosec:
        stages.append(
            ApprovalStage(
                order=order,
                role_name="Офицер безопасности",
                department="Департамент информационной безопасности",
                reason="Обязательное согласование требований информационной безопасности и прав доступа к информационным системам",
                is_mandatory=True,
            )
        )
        order += 1

    # 5. Департамент информационных технологий
    # (для приказов по ИС, а также для распоряжений о создании рабочих групп/комитетов ПРИ УСЛОВИИ involves_it=True)
    requires_it = (
        rule.requires_it == "yes"
        or (rule.rule_number == 8 and request.involves_it)
        or (rule.rule_number == 4)
    )
    if requires_it:
        stages.append(
            ApprovalStage(
                order=order,
                role_name="ИТ-архитектор / Эксперт",
                department="Департамент информационных технологий",
                reason="Обязательное согласование технических решений, архитектуры и использования ИТ-инфраструктуры",
                is_mandatory=True,
            )
        )
        order += 1

    # 6. Подразделение ДОУ Регионального отделения (РО Организации)
    # (для внешних писем российским юрлицам ПРИ УСЛОВИИ involves_regional=True)
    requires_regional = (
        rule.requires_regional == "yes"
        or (rule.rule_number == 13 and request.involves_regional)
    )
    if requires_regional:
        stages.append(
            ApprovalStage(
                order=order,
                role_name="Руководитель службы ДОУ РО",
                department="Подразделение ДОУ Регионального отделения (РО Организации)",
                reason="Согласование документационного обеспечения территориального контура Регионального отделения",
                is_mandatory=True,
            )
        )
        order += 1

    # 7. Департамент внутреннего контроля (для писем в органы власти)
    extra_depts = rule.extra_info.get("departments", []) if isinstance(rule.extra_info, dict) else []
    if rule.rule_number == 10 or "Департамент внутреннего контроля" in extra_depts:
        stages.append(
            ApprovalStage(
                order=order,
                role_name="Контролер-ревизор",
                department="Департамент внутреннего контроля",
                reason="Обязательное визирование обращений в органы государственной власти РФ, Администрацию Президента и Счетную палату",
                is_mandatory=True,
            )
        )
        order += 1

    # 8. Департамент международного сотрудничества (для писем иностранным организациям)
    if rule.rule_number == 11 or "Департамент международного сотрудничества" in extra_depts:
        stages.append(
            ApprovalStage(
                order=order,
                role_name="Эксперт по международным связям",
                department="Департамент международного сотрудничества",
                reason="Обязательное визирование международной корреспонденции и взаимодействия с зарубежными партнерами",
                is_mandatory=True,
            )
        )
        order += 1

    # =========================================================================
    # STAGE 3: Лингвистическая экспертиза (корректор Департамента ДОУ)
    # =========================================================================
    stages.append(
        ApprovalStage(
            order=order,
            role_name="Корректор Департамента ДОУ",
            department="Департамент делопроизводства (ДОУ)",
            reason="Лингвистическая экспертиза текста проекта документа (п. 4.2 Методических рекомендаций)",
            is_mandatory=True,
        )
    )
    order += 1

    # =========================================================================
    # STAGE 4: Визирование Департаментом ДОУ (проверка оформления, модуля и маршрута)
    # =========================================================================
    stages.append(
        ApprovalStage(
            order=order,
            role_name="Специалист Департамента ДОУ",
            department="Департамент делопроизводства (ДОУ)",
            reason="Визирование Департаментом ДОУ: проверка применения модуля, оформления и маршрута (п. 4.2 Методических рекомендаций)",
            is_mandatory=True,
        )
    )
    order += 1

    # =========================================================================
    # STAGE 5: Подписание и регистрация в ИИС ДО
    # =========================================================================
    stages.append(
        ApprovalStage(
            order=order,
            role_name="Подписант",
            department=rule.signatory,
            reason=f"Подписание документа ({rule.signatory}) и последующая регистрация в ИИС ДО",
            is_mandatory=True,
        )
    )

    return stages


async def calculate_approval_route(
    session: AsyncSession,
    request: ApprovalCalculateRequest,
) -> ApprovalCalculateResponse:
    """Calculate complete approval route based on PostgreSQL approval_rules and Section 4.2 workflow."""
    rules = await get_all_rules_from_db(session)
    matched_rule, notes, is_modular_res = resolve_matching_rule(rules, request)
    stages = construct_approval_stages(matched_rule, request)

    # Standard regulatory compliance note
    notes.append(
        "Маршрут сформирован в строгом соответствии с Матрицей обязательного визирования "
        "и разделом 4.2 Методических рекомендаций."
    )

    return ApprovalCalculateResponse(
        rule_number=matched_rule.rule_number,
        doc_type_name=matched_rule.doc_type_name,
        is_modular=is_modular_res,
        stages=stages,
        signatory=matched_rule.signatory,
        notes=notes,
    )


async def get_approval_rules_list(session: AsyncSession) -> List[ApprovalRuleItem]:
    """Retrieve all 13 rules formatted as ApprovalRuleItem for UI dropdowns."""
    rules = await get_all_rules_from_db(session)
    items: List[ApprovalRuleItem] = []
    for r in sorted(rules, key=lambda x: x.rule_number):
        items.append(
            ApprovalRuleItem(
                id=str(r.id) if getattr(r, "id", None) else None,
                rule_number=r.rule_number,
                category=r.category,
                doc_type_name=r.doc_type_name,
                is_modular=r.is_modular,
                requires_legal=r.requires_legal,
                requires_dou=r.requires_dou,
                requires_hr=r.requires_hr,
                requires_infosec=r.requires_infosec,
                requires_it=r.requires_it,
                requires_regional=r.requires_regional,
                condition_description=r.condition_description,
                signatory=r.signatory,
                extra_info=r.extra_info if isinstance(r.extra_info, dict) else {},
            )
        )
    return items


def build_pipeline_approval_recommendation(
    rule: ApprovalRule,
    initiator_department: Optional[str] = None,
) -> ApprovalRecommendation:
    """Helper to convert ApprovalRule into full 5-stage ApprovalRecommendation for query pipeline."""
    req = ApprovalCalculateRequest(
        doc_type=rule.doc_type_name,
        uses_module=rule.is_modular,
        involves_infosec_access=(rule.requires_infosec == "yes"),
        involves_it=(rule.requires_it == "yes"),
        involves_regional=(rule.requires_regional == "yes"),
        initiator_department=initiator_department or "Подразделение-инициатор",
    )
    stages = construct_approval_stages(rule, req)
    return ApprovalRecommendation(
        rule_number=rule.rule_number,
        doc_type_name=rule.doc_type_name,
        stages=stages,
        signatory=rule.signatory,
    )


APPROVAL_QUERY_TRIGGERS = (
    "согласов",
    "визир",
    "виз",
    "маршрут",
    "матриц",
    "подпис",
    "кто подписывает",
    "кем подписывается",
    "с кем",
    "кто визирует",
    "кто согласует",
    "кто согласовывает",
    "порядок визирования",
    "порядок согласования",
    "правила визирования",
    "этапы визирования",
    "регламент визирования",
    "регламент согласования",
)


def match_approval_from_query(
    rules: List[ApprovalRule],
    query: str,
) -> Optional[ApprovalRecommendation]:
    """Identify if a natural language query relates to document approval and return matching recommendation."""
    if not query or not query.strip():
        return None

    clean_q = query.strip().lower()

    has_approval_intent = any(trigger in clean_q for trigger in APPROVAL_QUERY_TRIGGERS)

    # Check if query matches a rule number or template module code directly
    has_direct_code = (
        any(
            c in clean_q
            for c in (
                "утв-01",
                "утв-02",
                "утв-03",
                "утв-04",
                "утв-05",
                "утв-06",
                "утв-07",
                "mod-order",
                "mod-disp",
            )
        )
        or bool(re.search(r"\b(правило|rule)\s*\d{1,2}\b", clean_q))
    )

    if not has_approval_intent and not has_direct_code:
        return None

    # Condition flags detection from query text
    infosec_access = (
        (
            "с доступом" in clean_q
            or "доступ" in clean_q
            or "правами" in clean_q
            or "учетн" in clean_q
            or "информационной безопасности" in clean_q
            or bool(re.search(r"\bис\b", clean_q))
            or "информационн" in clean_q
        )
        and ("без доступа" not in clean_q and "без изменения" not in clean_q)
    )

    involves_it = (
        (
            bool(re.search(r"\b(ит|it|ис|is)\b", clean_q))
            or "информационн" in clean_q
            or "цифровизац" in clean_q
            or "программн" in clean_q
        )
        and (
            "без ит" not in clean_q
            and "без участия ит" not in clean_q
            and "не связан" not in clean_q
        )
    )

    involves_regional = any(
        w in clean_q
        for w in (
            "региональн",
            "ро организац",
            "руководство ро",
            "филиал",
            "территориальн",
        )
    )

    uses_module = not any(
        w in clean_q
        for w in ("без модуля", "без применения модуля", "немодульн")
    )

    req = ApprovalCalculateRequest(
        doc_type=clean_q,
        uses_module=uses_module,
        involves_infosec_access=infosec_access,
        involves_it=involves_it,
        involves_regional=involves_regional,
        initiator_department="Подразделение-инициатор",
    )

    matched_rule, notes, is_mod = resolve_matching_rule(rules, req)
    stages = construct_approval_stages(matched_rule, req)

    return ApprovalRecommendation(
        rule_number=matched_rule.rule_number,
        doc_type_name=matched_rule.doc_type_name,
        stages=stages,
        signatory=matched_rule.signatory,
    )

