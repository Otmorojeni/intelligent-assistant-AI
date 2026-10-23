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
from src.db.models import ApprovalRule, AuditLog
from src.schemas.api_models import (
    ApprovalRecommendation,
    ApprovalStage,
    DetectedTermRef,
    QueryRequest,
    QueryResponse,
    SourceRef,
)

logger = logging.getLogger(__name__)

ZERO_HALLUCINATION_REFUSAL = (
    "В действующей редакции нормативных документов ДОУ Организации данный вопрос не "
    "регламентирован. Рекомендуется обратиться в Департамент ДОУ Организации."
)

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

    clean_query = query.strip().lower()

    # Check for approval intent
    has_approval_intent = any(kw in clean_query for kw in APPROVAL_TRIGGER_KEYWORDS)

    # Document kind flags
    is_prikaz = any(w in clean_query for w in ("приказ", "приказа", "приказом", "приказов"))
    is_disp = any(w in clean_query for w in ("распоряжен", "распоряжение", "распоряжения", "распоряжением"))
    is_letter = any(w in clean_query for w in ("письм", "письмо", "письма", "письмом"))

    # Fetch all registered approval rules
    stmt = select(ApprovalRule).order_by(ApprovalRule.rule_number)
    res = await session.execute(stmt)
    rules = res.scalars().all()
    if not rules:
        return None

    best_rule: Optional[ApprovalRule] = None
    best_score = 0.0

    for rule in rules:
        rule_name = rule.doc_type_name.lower()
        score = fuzz.token_set_ratio(clean_query, rule_name)

        # Document kind alignment to prevent cross-type mismatch (e.g. order matching disposition)
        if is_prikaz:
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

        # Domain keyword bonuses with strict operator precedence
        if "информационн" in clean_query and ("информационн" in rule_name or rule.requires_it != "no"):
            score += 25.0
        if "кадр" in clean_query or "личн" in clean_query:
            if rule.rule_number in (2, 3):
                score += 35.0
            elif rule.requires_hr:
                score += 15.0
        if any(w in clean_query for w in ("выходн", "праздничн", "календар")) and rule.rule_number == 1:
            score += 40.0
        if any(w in clean_query for w in ("командиров", "командирован")) and rule.rule_number == 5:
            score += 40.0
        if "основной деятельност" in clean_query and rule.rule_number == 5:
            score += 40.0
        if "отпуск" in clean_query and (rule.rule_number in (1, 5) or rule.requires_hr):
            score += 30.0
        if "имущество" in clean_query and "имущество" in rule_name:
            score += 40.0
        if "аудит" in clean_query and "аудит" in rule_name:
            score += 40.0
        if "рабоч" in clean_query and "групп" in clean_query and "рабочих групп" in rule_name:
            score += 40.0
        if any(org in clean_query for org in ("счетн", "счетная палата", "государственн", "президент", "правительств", "дума", "совет федерации")) and rule.rule_number == 10:
            score += 50.0
        if any(org in clean_query for org in ("иностранн", "международн", "банк")) and rule.rule_number == 11:
            score += 50.0
        if any(org in clean_query for org in ("региональн", "ро организац")) and rule.rule_number == 13:
            score += 40.0

        if score > best_score:
            best_score = score
            best_rule = rule

    # If approval intent explicitly present and best_score >= 35.0, or high similarity >= 65.0
    if (has_approval_intent and best_score >= 35.0 and best_rule) or (best_score >= 65.0 and best_rule):
        stages = build_approval_stages(best_rule)
        return ApprovalRecommendation(
            rule_number=best_rule.rule_number,
            doc_type_name=best_rule.doc_type_name,
            stages=stages,
            signatory=best_rule.signatory,
        )

    return None


async def log_audit_event(
    session: AsyncSession,
    user_role: str,
    query_text: str,
    response_summary: str,
    status: str,
    latency_ms: float,
    ip_address: Optional[str] = None,
) -> None:
    """Save query event into audit_logs table."""
    try:
        audit = AuditLog(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            user_role=user_role,
            user_name="Пользователь",
            action_type="query",
            query_text=query_text,
            response_summary=response_summary[:500] if response_summary else None,
            status=status,
            latency_ms=latency_ms,
            ip_address=ip_address,
        )
        session.add(audit)
        await session.flush()
    except Exception as e:
        logger.warning(f"Failed to record audit log: {e}")


async def process_query(
    session: AsyncSession,
    request: QueryRequest,
    ip_address: Optional[str] = None,
    llm_client: Optional[OllamaClient] = None,
) -> QueryResponse:
    """Execute end-to-end question answering pipeline with Zero-Hallucination Guard and stage profiling."""
    t_total_start = time.perf_counter()
    req_id = request.request_id or str(uuid.uuid4())

    # 1. Matching Stage: Detect corporate terms and approval routing
    t_match_start = time.perf_counter()
    detected_terms = await detect_query_terms(session, request.query)
    approval_rec = await match_approval_recommendation(session, request.query)
    t_match_ms = round((time.perf_counter() - t_match_start) * 1000.0, 2)

    # 2. Retrieval Stage: Hybrid search over PostgreSQL chunks (passing detected_terms to avoid duplicate query)
    t_retriever_start = time.perf_counter()
    sources = await retrieve_chunks(
        session=session,
        query=request.query,
        user_role=request.user_role,
        top_k=request.top_k,
        detected_terms=detected_terms,
    )
    t_retriever_ms = round((time.perf_counter() - t_retriever_start) * 1000.0, 2)

    max_relevance = max((s.relevance_pct for s in sources), default=0.0)

    # 3. Zero-Hallucination Guard
    if max_relevance < settings.MIN_RELEVANCE_THRESHOLD:
        t_llm_ms = 0.0
        total_latency_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
        logger.info(
            f"Zero-Hallucination Guard triggered (relevance {max_relevance}% < {settings.MIN_RELEVANCE_THRESHOLD}%)"
        )

        response = QueryResponse(
            request_id=req_id,
            answer=ZERO_HALLUCINATION_REFUSAL,
            relevance_score=max_relevance,
            detected_terms=detected_terms,
            sources=[],
            approval_recommendation=approval_rec,
            zero_hallucination_triggered=True,
            latency_ms=total_latency_ms,
            t_match_ms=t_match_ms,
            t_retriever_ms=t_retriever_ms,
            t_llm_ms=0.0,
        )

        await log_audit_event(
            session=session,
            user_role=request.user_role,
            query_text=request.query,
            response_summary=ZERO_HALLUCINATION_REFUSAL,
            status="zero_hallucination",
            latency_ms=total_latency_ms,
            ip_address=ip_address,
        )
        return response

    # 4. Grounded LLM Generation Stage
    t_llm_start = time.perf_counter()
    client = llm_client or OllamaClient()
    answer = await client.generate_answer(
        query=request.query,
        sources=sources,
        detected_terms=detected_terms,
    )
    t_llm_ms = round((time.perf_counter() - t_llm_start) * 1000.0, 2)
    total_latency_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)

    response = QueryResponse(
        request_id=req_id,
        answer=answer,
        relevance_score=max_relevance,
        detected_terms=detected_terms,
        sources=sources,
        approval_recommendation=approval_rec,
        zero_hallucination_triggered=False,
        latency_ms=total_latency_ms,
        t_match_ms=t_match_ms,
        t_retriever_ms=t_retriever_ms,
        t_llm_ms=t_llm_ms,
    )

    await log_audit_event(
        session=session,
        user_role=request.user_role,
        query_text=request.query,
        response_summary=answer,
        status="success",
        latency_ms=total_latency_ms,
        ip_address=ip_address,
    )

    return response
