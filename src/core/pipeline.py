"""Orchestration pipeline connecting hybrid retrieval and grounded LLM generation.

Features:
- Zero-Hallucination Guard: blocks LLM invocation and returns standardized regulatory refusal
  if top retrieval relevance is below MIN_RELEVANCE_THRESHOLD.
- Latency profiling across all processing stages (t_match_ms, t_retriever_ms, t_llm_ms, latency_ms).
- Defined corporate terms extraction and glossary linking.
- Regulatory approval routing recommendation based on approval_rules matrix.
- Audit logging of all processed queries for security, governance, and compliance.
"""

from datetime import datetime, timezone
import logging
import re
import time
from typing import Any, Dict, List, Optional
import uuid

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.llm_client import OllamaClient
from src.core.retriever import (
    detect_query_terms,
    get_allowed_access_levels,
    retrieve_chunks,
)
from src.db.models import ApprovalRule, AuditLog, ChatMessage, ChatSession, TemplateModule
from src.schemas.api_models import (
    ApprovalRecommendation,
    ApprovalStage,
    DetectedTermRef,
    DocumentGenerateRequest,
    DocumentGenerateResponse,
    QueryRequest,
    QueryResponse,
    SourceRef,
)

logger = logging.getLogger(__name__)

ZERO_HALLUCINATION_REFUSAL = (
    "В действующей редакции нормативных документов ДОУ Организации данный вопрос не "
    "регламентирован. Рекомендуется обратиться в Департамент ДОУ Организации."
)

TEMPLATE_FILL_TRIGGERS = (
    "заполн",
    "сформируй",
    "сформировать",
    "создай проект",
    "создай черновик",
    "подготовь проект",
    "подготовь приказ",
    "подготовь распоряжение",
    "подготовить приказ",
    "подготовить распоряжение",
    "подготовить проект",
    "оформить приказ",
    "оформить распоряжение",
    "сгенерируй",
)


def detect_dialog_template_module(query: str) -> Optional[str]:
    """Detect if the user is asking the assistant in dialog to fill/generate one of the 7 modular templates."""
    q_low = query.lower()
    if not any(t in q_low for t in TEMPLATE_FILL_TRIGGERS):
        return None
    for code in (
        "MOD-ORDER-IS",
        "MOD-ORDER-DOU",
        "MOD-ORDER-PROP",
        "MOD-ORDER-LNA",
        "MOD-DISP-AUDIT",
        "MOD-DISP-PROJECT",
        "MOD-DISP-WORKGROUP",
    ):
        if code.lower() in q_low:
            return code
    if "вводе в эксплуатацию" in q_low or "информационной системы" in q_low or "утв-01" in q_low:
        return "MOD-ORDER-IS"
    if "ответственных за делопроизводство" in q_low or "ответственных за ведение" in q_low or "утв-02" in q_low:
        return "MOD-ORDER-DOU"
    if "приеме и передаче" in q_low or "приеме-передаче" in q_low or "утв-03" in q_low:
        return "MOD-ORDER-PROP"
    if "утверждении" in q_low and ("лна" in q_low or "локальн" in q_low or "положени" in q_low) or "утв-04" in q_low:
        return "MOD-ORDER-LNA"
    if "внутреннего аудита" in q_low or "внутреннем аудите" in q_low or "утв-05" in q_low:
        return "MOD-DISP-AUDIT"
    if "проектного комитета" in q_low or "проектный комитет" in q_low or "утв-06" in q_low:
        return "MOD-DISP-PROJECT"
    if "рабочей группы" in q_low or "рабочую группу" in q_low or "утв-07" in q_low:
        return "MOD-DISP-WORKGROUP"
    return None


def detect_conditional_ambiguity(
    query: str,
    approval_rec: Optional[ApprovalRecommendation],
) -> tuple[bool, Optional[str], List[str]]:
    """Detect whether an approval query hits a conditional matrix branch without specifying the condition."""
    if not approval_rec:
        return False, None, []

    q_low = query.lower()
    # 1. Rule 2 / 3: Handover of affairs & property (depends on InfoSec access change)
    if approval_rec.rule_number in (2, 3):
        explicit_infosec = any(
            w in q_low
            for w in ("доступ", "информационной безопасности", "без изменения", "с изменением", "правами")
        ) or bool(re.search(r"\b(?:ис|иб)\b", q_low))
        if not explicit_infosec:
            return (
                True,
                "Уточните, пожалуйста: связан ли приказ о приеме-передаче дел с предоставлением, изменением или прекращением доступа к информационным системам (ИС)? От этого зависит обязательность визы Департамента информационной безопасности (Правило № 2 или № 3 Матрицы визирования).",
                [
                    "Да, затрагивает доступ к ИС (нужна виза Департамента ИБ — Правило № 3)",
                    "Нет, без изменения доступа к ИС (стандартный маршрут — Правило № 2)",
                ],
            )

    # 2. Rule 7 / 8: Working group / project committee (depends on whether it's an IT project)
    if approval_rec.rule_number in (7, 8):
        explicit_it = any(
            w in q_low
            for w in ("ит-проект", "информационн", "цифровизац", "программн", "без ит", "общего профиля")
        ) or bool(re.search(r"\b(?:ит|it|ис|is)\b", q_low))
        if not explicit_it:
            return (
                True,
                "Уточните, пожалуйста: создается ли рабочая группа (проектный комитет) для реализации ИТ-проекта или решения вопросов информационных систем? При участии ИТ в маршрут обязательно включается Департамент информационных технологий (Правило № 7 или № 8 Матрицы визирования).",
                [
                    "Да, создается для ИТ-проекта / вопросов ИС (Правило № 8 — с визой ДИТ)",
                    "Нет, рабочая группа общего профиля без ИТ (Правило № 7)",
                ],
            )

    # 3. Rule 12 / 13: External letters to Russian legal entities (CA vs Regional branch RO)
    if approval_rec.rule_number in (12, 13):
        explicit_reg = any(
            w in q_low
            for w in ("региональн", "ро организац", "центральн", "филиал", "территориальн")
        ) or bool(re.search(r"\b(?:ро|ца)\b", q_low))
        if not explicit_reg:
            return (
                True,
                "Уточните, пожалуйста: подготавливается ли письмо российскому юридическому лицу в Центральном аппарате (ЦА) или с участием Регионального отделения (РО Организации)? (Правило № 12 или № 13 Матрицы визирования).",
                [
                    "В Центральном аппарате (Правило № 12)",
                    "С участием Регионального отделения РО (Правило № 13 — с визой ДОУ РО)",
                ],
            )

    return False, None, []

APPROVAL_TRIGGER_KEYWORDS = [
    "согласован",
    "согласовать",
    "согласует",
    "согласование",
    "визиров",
    "визирование",
    "визирует",
    "завизировать",
    "подписан",
    "подписание",
    "подписывает",
    "подписант",
    "маршрут",
    "матриц",
    "с кем согласовывать",
    "кто подписывает",
    "кто визирует",
    "порядок визирования",
    "порядок согласования",
    "правила визирования",
    "этапы визирования",
]


def build_approval_stages(
    rule: ApprovalRule,
    initiator_department: Optional[str] = None,
) -> List[ApprovalStage]:
    """Convert an ApprovalRule database model into structured 5-stage ApprovalStage list per Section 4.2."""
    from src.core.approval_router import construct_approval_stages
    from src.schemas.api_models import ApprovalCalculateRequest

    req = ApprovalCalculateRequest(
        doc_type=rule.doc_type_name,
        uses_module=rule.is_modular,
        involves_infosec_access=(rule.requires_infosec == "yes"),
        involves_it=(rule.requires_it == "yes"),
        involves_regional=(rule.requires_regional == "yes"),
        initiator_department=initiator_department or "Подразделение-инициатор",
    )
    return construct_approval_stages(rule, req)


async def match_approval_recommendation(
    session: AsyncSession, query: str
) -> Optional[ApprovalRecommendation]:
    """Identify if query relates to document approval and return matching rule recommendation."""
    if not query or not query.strip():
        return None

    from src.core.approval_router import (
        get_all_rules_from_db,
        match_approval_from_query,
    )

    rules = await get_all_rules_from_db(session)
    return match_approval_from_query(rules, query)


from src.core.security import log_audit_event


_MEMORY_SESSION_STATE: Dict[str, Dict[str, Any]] = {}


async def process_query(
    session: AsyncSession,
    request: QueryRequest,
    ip_address: Optional[str] = None,
    user_name: str = "Пользователь",
    llm_client: Optional[OllamaClient] = None,
) -> QueryResponse:
    """Execute end-to-end question answering pipeline with Zero-Hallucination Guard and multi-turn dialog."""
    t_total_start = time.perf_counter()
    req_id = request.request_id or str(uuid.uuid4())
    session_id_str = request.session_id or request.conversation_id or str(uuid.uuid4())

    # Resolve multi-turn conversation context if session_id or history is present
    effective_query = request.query
    chat_session: Optional[ChatSession] = None
    try:
        sess_uuid = uuid.UUID(session_id_str)
    except ValueError:
        sess_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, session_id_str)
    session_id_str = str(sess_uuid)

    prev_state = _MEMORY_SESSION_STATE.get(session_id_str, {})
    try:
        async with session.begin_nested():
            chat_session = (
                await session.execute(select(ChatSession).where(ChatSession.id == sess_uuid))
            ).scalar_one_or_none()
            if not chat_session:
                chat_session = ChatSession(
                    id=sess_uuid,
                    user_name=user_name,
                    user_role=request.user_role,
                    title=request.query[:120],
                    state_json=prev_state,
                )
                session.add(chat_session)
                await session.flush()
            elif chat_session.state_json:
                prev_state = dict(chat_session.state_json)
    except Exception:
        chat_session = None

    prev_topic = prev_state.get("last_query")
    if prev_topic and len(request.query.strip()) < 120 and (
        prev_state.get("needs_clarification")
        or any(
            w in request.query.lower()
            for w in (
                "да,",
                "нет,",
                "правило",
                "с участием",
                "в центральном",
                "без ит",
                "с доступом",
                "затрагивает доступ",
                "без изменения доступа",
                "ит-проект",
            )
        )
    ):
        effective_query = f"{prev_topic}. Уточнение пользователя: {request.query}"
    elif request.history:
        last_user_msgs = [
            m.get("content", "")
            for m in request.history
            if m.get("role") == "user" and m.get("content")
        ]
        if last_user_msgs and len(request.query.strip()) < 120:
            effective_query = f"{last_user_msgs[-1]}. {request.query}"

    # 1. Matching Stage: Detect corporate terms and approval routing
    t_match_start = time.perf_counter()
    detected_terms = await detect_query_terms(session, effective_query)
    approval_rec = await match_approval_recommendation(session, effective_query)
    t_match_ms = round((time.perf_counter() - t_match_start) * 1000.0, 2)

    # 2. Retrieval Stage: Hybrid search over PostgreSQL chunks
    prev_slot_state = prev_state.get("slot_filling_state") or {}
    retrieval_query = (
        prev_topic
        if (prev_slot_state.get("active") and prev_topic)
        else effective_query
    )
    t_retriever_start = time.perf_counter()
    sources = await retrieve_chunks(
        session=session,
        query=retrieval_query,
        user_role=request.user_role,
        top_k=request.top_k,
        detected_terms=detected_terms,
    )
    t_retriever_ms = round((time.perf_counter() - t_retriever_start) * 1000.0, 2)

    max_relevance = max((s.relevance_pct for s in sources), default=0.0)

    # 3. Zero-Hallucination Guard — never attach approval_recommendation on out-of-domain refusal (RAG-04)
    if max_relevance < settings.MIN_RELEVANCE_THRESHOLD and not prev_slot_state.get("active"):
        total_latency_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
        logger.info(
            f"Zero-Hallucination Guard triggered (relevance {max_relevance}% < {settings.MIN_RELEVANCE_THRESHOLD}%)"
        )

        response = QueryResponse(
            request_id=req_id,
            session_id=str(chat_session.id) if chat_session else session_id_str,
            answer=ZERO_HALLUCINATION_REFUSAL,
            relevance_score=max_relevance,
            detected_terms=detected_terms,
            sources=[],
            approval_recommendation=None,
            zero_hallucination_triggered=True,
            latency_ms=total_latency_ms,
            t_match_ms=t_match_ms,
            t_retriever_ms=t_retriever_ms,
            t_llm_ms=0.0,
        )

        await log_audit_event(
            session=session,
            user_role=request.user_role,
            user_name=user_name,
            query_text=request.query,
            response_summary=ZERO_HALLUCINATION_REFUSAL,
            status="zero_hallucination",
            latency_ms=total_latency_ms,
            ip_address=ip_address,
        )
        return response

    # Check if query hits a conditional matrix branch and benefits from clarifying options
    needs_clarif, clarif_q, quick_replies = detect_conditional_ambiguity(effective_query, approval_rec)

    # Check if session is in active template slot-filling state (Turn 2) or starting template filling (Turn 1)
    slot_filling_state: Optional[Dict[str, Any]] = None
    generated_document: Optional[DocumentGenerateResponse] = None
    prev_slot_state = prev_state.get("slot_filling_state") or {}

    if prev_slot_state.get("active") and prev_slot_state.get("module_code"):
        target_mod_code = prev_slot_state["module_code"]
        tm_row = (
            await session.execute(select(TemplateModule).where(TemplateModule.module_code == target_mod_code))
        ).scalar_one_or_none()
        if tm_row:
            from src.core.doc_generator import generate_document

            filled_fields: Dict[str, str] = {}
            for f_def in tm_row.fields_schema or []:
                fname = f_def.get("name", "")
                fdefault = f_def.get("default", "") or "По согласованию"
                filled_fields[fname] = fdefault
                flabel = f_def.get("label", "")
                # Parse "field_name: value" or "label: value" from user reply if provided
                for key_cand in (fname, flabel):
                    if key_cand:
                        m_kv = re.search(rf"{re.escape(key_cand)}\s*[:=-]\s*([^\n;,]+)", request.query, re.I)
                        if m_kv:
                            filled_fields[fname] = m_kv.group(1).strip()

            gen_req = DocumentGenerateRequest(
                module_code=target_mod_code,
                executor_name=user_name or "Иванов И.И.",
                executor_department="Департамент ДОУ",
                signatory_name=filled_fields.get("signatory_name", "Петров П.П."),
                fields=filled_fields,
            )
            generated_document = await generate_document(session, gen_req)
            slot_filling_state = {
                "active": False,
                "completed": True,
                "module_code": target_mod_code,
                "reg_number": tm_row.reg_number,
                "fields": filled_fields,
                "file_name": generated_document.file_name,
            }
            needs_clarif = False
            clarif_q = None
            quick_replies = []
    else:
        detected_mod_code = detect_dialog_template_module(request.query)
        if detected_mod_code:
            tm_row = (
                await session.execute(select(TemplateModule).where(TemplateModule.module_code == detected_mod_code))
            ).scalar_one_or_none()
            if tm_row:
                field_labels = [f.get("label", f.get("name", "")) for f in (tm_row.fields_schema or [])]
                slot_filling_state = {
                    "active": True,
                    "module_code": tm_row.module_code,
                    "reg_number": tm_row.reg_number,
                    "title": tm_row.title,
                    "required_fields": field_labels,
                }
                needs_clarif = True
                clarif_q = (
                    f"Я подобрал модульный шаблон «{tm_row.title}» (№ {tm_row.reg_number}, код {tm_row.module_code}). "
                    f"Для автоматического заполнения укажите реквизиты ({', '.join(field_labels[:4])}) "
                    f"или подтвердите выпуск черновика со стандартными значениями:"
                )
                quick_replies = [
                    "Заполнить стандартными реквизитами и выпустить проект .DOCX",
                    f"Открыть конструктор шаблона {tm_row.module_code}",
                ]

    approval_summary = None
    if approval_rec:
        stage_str = "; ".join(f"{st.order}. {st.department} ({st.role_name})" for st in approval_rec.stages)
        approval_summary = (
            f"Правило № {approval_rec.rule_number} ({approval_rec.doc_type_name}).\n"
            f"Обязательные этапы согласования: {stage_str}.\n"
            f"Подписант: {approval_rec.signatory}."
        )

    # 4. Grounded LLM Generation Stage
    t_llm_start = time.perf_counter()
    client = llm_client or OllamaClient()
    try:
        answer = await client.generate_answer(
            query=effective_query,
            sources=sources,
            detected_terms=detected_terms,
            approval_summary=approval_summary,
        )
    except TypeError:
        answer = await client.generate_answer(
            query=effective_query,
            sources=sources,
            detected_terms=detected_terms,
        )

    if generated_document:
        answer = (
            f"{answer}\n\n"
            f"✅ **Проект документа ({slot_filling_state.get('module_code', '')} / {slot_filling_state.get('reg_number', '')}) автоматически сформирован в диалоге!**\n"
            f"- **Файл:** `{generated_document.file_name}` (`{generated_document.download_url}`)\n"
            f"- **Обязательная отметка п. 2.3:** {generated_document.note_text}"
        )
    elif needs_clarif and clarif_q and clarif_q not in answer:
        answer = f"{answer}\n\n💡 **{clarif_q}**"

    t_llm_ms = round((time.perf_counter() - t_llm_start) * 1000.0, 2)
    total_latency_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)

    new_state = {
        "last_query": effective_query,
        "needs_clarification": needs_clarif,
        "last_rule_number": approval_rec.rule_number if approval_rec else None,
        "slot_filling_state": slot_filling_state,
    }
    _MEMORY_SESSION_STATE[session_id_str] = new_state
    if chat_session:
        try:
            async with session.begin_nested():
                chat_session.state_json = new_state
                session.add(
                    ChatMessage(
                        session_id=chat_session.id,
                        role="user",
                        content=request.query,
                        metadata_json={"request_id": req_id},
                    )
                )
                session.add(
                    ChatMessage(
                        session_id=chat_session.id,
                        role="assistant",
                        content=answer,
                        metadata_json={
                            "request_id": req_id,
                            "relevance_score": max_relevance,
                            "needs_clarification": needs_clarif,
                            "quick_replies": quick_replies,
                        },
                    )
                )
                await session.flush()
        except Exception:
            pass

    response = QueryResponse(
        request_id=req_id,
        session_id=str(chat_session.id) if chat_session else session_id_str,
        answer=answer,
        relevance_score=max_relevance,
        detected_terms=detected_terms,
        sources=sources,
        approval_recommendation=approval_rec,
        zero_hallucination_triggered=False,
        needs_clarification=needs_clarif,
        clarification_question=clarif_q,
        quick_replies=quick_replies,
        slot_filling_state=slot_filling_state,
        generated_document=generated_document.model_dump(mode="json") if generated_document else None,
        latency_ms=total_latency_ms,
        t_match_ms=t_match_ms,
        t_retriever_ms=t_retriever_ms,
        t_llm_ms=t_llm_ms,
    )

    await log_audit_event(
        session=session,
        user_role=request.user_role,
        user_name=user_name,
        query_text=request.query,
        response_summary=answer,
        status="success",
        latency_ms=total_latency_ms,
        ip_address=ip_address,
    )

    return response
