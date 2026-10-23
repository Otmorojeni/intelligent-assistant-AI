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

    from src.core.approval_router import (
        get_all_rules_from_db,
        match_approval_from_query,
    )

    rules = await get_all_rules_from_db(session)
    return match_approval_from_query(rules, query)


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
