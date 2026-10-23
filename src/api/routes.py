"""FastAPI router defining REST endpoints for approval calculation, rules, query, and health."""

import logging
from typing import List

from fastapi import APIRouter, Depends, Request, status
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.approval_router import (
    calculate_approval_route,
    get_approval_rules_list,
)
from src.core.pipeline import process_query
from src.db.database import get_db
from src.schemas.api_models import (
    ApprovalCalculateRequest,
    ApprovalCalculateResponse,
    ApprovalRuleItem,
    HealthResponse,
    QueryRequest,
    QueryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Approval & Assistant"])


@router.post(
    "/approval/calculate",
    response_model=ApprovalCalculateResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate approval route per Matrix and Section 4.2",
    description="Calculates ordered 5-stage approval route based on doc_type, modules, and condition flags.",
)
async def calculate_approval(
    request: ApprovalCalculateRequest,
    session: AsyncSession = Depends(get_db),
) -> ApprovalCalculateResponse:
    """Calculate approval route based on PostgreSQL approval_rules and Section 4.2 workflow."""
    return await calculate_approval_route(session, request)


@router.get(
    "/approval/rules",
    response_model=List[ApprovalRuleItem],
    status_code=status.HTTP_200_OK,
    summary="Get list of all 13 approval matrix rules",
    description="Returns list of all 13 rules from approval_rules table for UI dropdowns.",
)
async def get_approval_rules(
    session: AsyncSession = Depends(get_db),
) -> List[ApprovalRuleItem]:
    """Retrieve all 13 rules from approval_rules table for UI dropdowns."""
    return await get_approval_rules_list(session)


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask questions to the regulatory knowledge base",
    description="Orchestration pipeline with hybrid retrieval, Zero-Hallucination Guard, and approval recommendation.",
)
async def handle_query(
    request: QueryRequest,
    raw_request: Request,
    session: AsyncSession = Depends(get_db),
) -> QueryResponse:
    """Handle natural language question answering with approval recommendation."""
    client_ip = raw_request.client.host if raw_request.client else None
    return await process_query(session=session, request=request, ip_address=client_ip)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check service health and dependencies",
)
async def health_check(
    session: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """Check connectivity to PostgreSQL database and local Ollama instance."""
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")

    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/v1')}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        ollama_ok = False

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        db_connected=db_ok,
        ollama_connected=ollama_ok,
        active_version="1.0.0",
    )
