"""FastAPI router defining REST endpoints for approval calculation, rules, query, and health."""

import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.approval_router import (
    calculate_approval_route,
    get_approval_rules_list,
)
from src.core.doc_generator import (
    generate_document,
    get_all_projects,
    get_available_templates,
    get_template_by_code,
)
from src.core.pipeline import process_query
from src.db.database import get_db
from src.schemas.api_models import (
    ApprovalCalculateRequest,
    ApprovalCalculateResponse,
    ApprovalRuleItem,
    DocumentGenerateRequest,
    DocumentGenerateResponse,
    HealthResponse,
    ProjectCardItem,
    QueryRequest,
    QueryResponse,
    TemplateModuleInfo,
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


# =============================================================================
# Modular Document Generation & Registry Endpoints (Section 2.3 & 3.3)
# =============================================================================


@router.get(
    "/documents/templates",
    response_model=List[TemplateModuleInfo],
    status_code=status.HTTP_200_OK,
    summary="List all available modular document templates",
    description="Returns metadata and dynamic input field schemas for all 7 approved modular templates.",
)
async def list_templates(
    session: AsyncSession = Depends(get_db),
) -> List[TemplateModuleInfo]:
    """Return all 7 approved document module templates with field schemas."""
    return await get_available_templates(session)


@router.get(
    "/documents/templates/{module_code}",
    response_model=TemplateModuleInfo,
    status_code=status.HTTP_200_OK,
    summary="Get specific document template by module code or registration number",
)
async def get_template(
    module_code: str,
    session: AsyncSession = Depends(get_db),
) -> TemplateModuleInfo:
    """Get single template module by its code (e.g. MOD-ORDER-IS) or reg number (e.g. УТВ-01)."""
    template = await get_template_by_code(session, module_code)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template module '{module_code}' not found.",
        )
    return template


@router.post(
    "/documents/generate",
    response_model=DocumentGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate clean DOCX document and register Project Card",
    description=(
        "Substitutes variable fields, performs strict cleaning per Section 3.3, "
        "calculates approval route per Section 4.2 and registers a Project Card in PostgreSQL."
    ),
)
async def generate_doc(
    request: DocumentGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> DocumentGenerateResponse:
    """Generate cleaned .docx, calculate approval route, and create project card in DB."""
    return await generate_document(session, request)


@router.get(
    "/documents/download/{file_name}",
    status_code=status.HTTP_200_OK,
    summary="Download generated DOCX document",
)
async def download_document(
    file_name: str,
) -> FileResponse:
    """Serve generated DOCX file with appropriate content disposition headers."""
    safe_name = Path(file_name).name
    file_path = settings.GENERATED_DOCS_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generated document '{safe_name}' not found.",
        )
    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get(
    "/documents/projects",
    response_model=List[ProjectCardItem],
    status_code=status.HTTP_200_OK,
    summary="List all created project cards",
)
async def list_projects(
    session: AsyncSession = Depends(get_db),
) -> List[ProjectCardItem]:
    """Retrieve list of all created project cards from database."""
    return await get_all_projects(session)

