"""FastAPI router defining REST endpoints for approval calculation, rules, query, and health."""

import json
import logging
from pathlib import Path
import time
from typing import AsyncGenerator, List, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.approval_router import (
    calculate_approval_route,
    get_approval_rules_list,
)
from src.core.compliance_checker import check_docx_compliance
from src.core.doc_generator import (
    generate_document,
    get_all_projects,
    get_available_templates,
    get_template_by_code,
)
from src.core.llm_client import OllamaClient
from src.core.pipeline import (
    ZERO_HALLUCINATION_REFUSAL,
    detect_conditional_ambiguity,
    match_approval_recommendation,
    process_query,
)
from src.core.retriever import detect_query_terms, retrieve_chunks
from src.core.security import (
    UserContext,
    UserRole,
    check_document_access,
    create_access_token,
    detect_prompt_injection,
    get_current_user,
    log_audit_event,
    normalize_role,
    require_role,
)
from src.core.versioning import (
    activate_document_version,
    get_all_document_versions,
    query_audit_logs,
    upload_document_version,
)
from src.db.database import get_db
from src.db.models import DocumentChunk, ProjectCard
from src.schemas.api_models import (
    ApprovalCalculateRequest,
    ApprovalCalculateResponse,
    ApprovalRuleItem,
    AuditLogItem,
    ComplianceCheckResponse,
    DocumentGenerateRequest,
    DocumentGenerateResponse,
    DocumentVersionItem,
    HealthResponse,
    ProjectCardItem,
    QueryRequest,
    QueryResponse,
    TemplateModuleInfo,
    TokenRequest,
    TokenResponse,
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
    "/assistant/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask questions to the regulatory knowledge base (assistant)",
    description="Orchestration pipeline with hybrid retrieval, RBAC access-level filtering, and audit logging.",
)
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
    current_user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> QueryResponse:
    """Handle natural language question answering with approval recommendation, RBAC, and prompt injection guard."""
    client_ip = raw_request.client.host if raw_request.client else None

    # Determine effective role strictly from authenticated UserContext (never escalate from JSON body!)
    effective_role = current_user.role
    request.user_role = effective_role

    # Guard against Prompt Injection / Malicious inputs
    is_malicious, reason = detect_prompt_injection(request.query)
    if is_malicious:
        refusal_msg = (
            "Запрос содержит потенциально небезопасные инструкции (Prompt Injection). "
            "В обработке отказано в соответствии с политикой информационной безопасности."
        )
        logger.warning(f"Prompt injection blocked from {client_ip} (role={effective_role}): {reason}")
        await log_audit_event(
            session=session,
            user_role=effective_role,
            user_name=current_user.username,
            action_type="security_alert",
            query_text=request.query,
            response_summary=f"Prompt injection blocked: {reason}",
            status="prompt_injection_blocked",
            latency_ms=0.0,
            ip_address=client_ip,
        )
        await session.commit()

        return QueryResponse(
            request_id=request.request_id or str(uuid.uuid4()),
            session_id=request.session_id or request.conversation_id,
            answer=refusal_msg,
            relevance_score=0.0,
            detected_terms=[],
            sources=[],
            approval_recommendation=None,
            zero_hallucination_triggered=True,
            latency_ms=0.0,
        )

    return await process_query(
        session=session,
        request=request,
        ip_address=client_ip,
        user_name=current_user.username,
    )


@router.post(
    "/assistant/query/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream grounded answer tokens via Server-Sent Events (SSE)",
    description="Returns retrieval metadata immediately (<50ms) and streams LLM tokens as they are generated.",
)
async def handle_query_stream(
    request: QueryRequest,
    raw_request: Request,
    current_user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """SSE streaming endpoint for responsive Web UI on 2-core CPU VM."""
    client_ip = raw_request.client.host if raw_request.client else None
    effective_role = current_user.role
    request.user_role = effective_role
    req_id = request.request_id or str(uuid.uuid4())
    t0 = time.perf_counter()

    is_malicious, reason = detect_prompt_injection(request.query)
    if is_malicious:
        refusal_msg = (
            "Запрос содержит потенциально небезопасные инструкции (Prompt Injection). "
            "В обработке отказано в соответствии с политикой информационной безопасности."
        )
        await log_audit_event(
            session=session,
            user_role=effective_role,
            user_name=current_user.username,
            action_type="security_alert",
            query_text=request.query,
            response_summary=f"Prompt injection blocked: {reason}",
            status="prompt_injection_blocked",
            latency_ms=0.0,
            ip_address=client_ip,
        )
        await session.commit()

        async def _err_gen() -> AsyncGenerator[str, None]:
            meta = {
                "type": "metadata",
                "request_id": req_id,
                "relevance_score": 0.0,
                "zero_hallucination_triggered": True,
                "detected_terms": [],
                "sources": [],
                "approval_recommendation": None,
                "needs_clarification": False,
                "quick_replies": [],
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'content': refusal_msg}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'latency_ms': 1.0}, ensure_ascii=False)}\n\n"

        return StreamingResponse(_err_gen(), media_type="text/event-stream")

    detected_terms = await detect_query_terms(session, request.query)
    approval_rec = await match_approval_recommendation(session, request.query)
    sources = await retrieve_chunks(
        session=session,
        query=request.query,
        user_role=effective_role,
        top_k=request.top_k,
        detected_terms=detected_terms,
    )
    max_relevance = max((s.relevance_pct for s in sources), default=0.0)
    needs_clarif, clarif_q, quick_replies = detect_conditional_ambiguity(request.query, approval_rec)

    async def _stream_generator() -> AsyncGenerator[str, None]:
        if max_relevance < settings.MIN_RELEVANCE_THRESHOLD:
            meta = {
                "type": "metadata",
                "request_id": req_id,
                "relevance_score": max_relevance,
                "zero_hallucination_triggered": True,
                "detected_terms": [t.model_dump() for t in detected_terms],
                "sources": [],
                "approval_recommendation": None,
                "needs_clarification": False,
                "quick_replies": [],
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'content': ZERO_HALLUCINATION_REFUSAL}, ensure_ascii=False)}\n\n"
            total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            yield f"data: {json.dumps({'type': 'done', 'latency_ms': total_ms}, ensure_ascii=False)}\n\n"
            return

        meta = {
            "type": "metadata",
            "request_id": req_id,
            "relevance_score": max_relevance,
            "zero_hallucination_triggered": False,
            "detected_terms": [t.model_dump() for t in detected_terms],
            "sources": [s.model_dump() for s in sources],
            "approval_recommendation": approval_rec.model_dump() if approval_rec else None,
            "needs_clarification": needs_clarif,
            "clarification_question": clarif_q,
            "quick_replies": quick_replies,
        }
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

        approval_summary = None
        if approval_rec:
            stage_str = "; ".join(f"{st.order}. {st.department} ({st.role_name})" for st in approval_rec.stages)
            approval_summary = (
                f"Правило № {approval_rec.rule_number} ({approval_rec.doc_type_name}).\n"
                f"Обязательные этапы согласования: {stage_str}.\n"
                f"Подписант: {approval_rec.signatory}."
            )

        client = OllamaClient()
        async for token_chunk in client.generate_answer_stream(
            query=request.query,
            sources=sources,
            detected_terms=detected_terms,
            approval_summary=approval_summary,
        ):
            yield f"data: {json.dumps({'type': 'token', 'content': token_chunk}, ensure_ascii=False)}\n\n"

        if needs_clarif and clarif_q:
            yield f"data: {json.dumps({'type': 'token', 'content': f'\n\n💡 **{clarif_q}**'}, ensure_ascii=False)}\n\n"

        total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        yield f"data: {json.dumps({'type': 'done', 'latency_ms': total_ms}, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream_generator(), media_type="text/event-stream")


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
            resp = await client.get(f"{settings.OLLAMA_BASE_URL.removesuffix('/v1')}/api/tags")
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
    current_user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve generated DOCX file with RBAC classification enforcement."""
    if "/" in file_name or "\\" in file_name or ".." in file_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file name.",
        )
    safe_name = Path(file_name).name
    file_path = settings.GENERATED_DOCS_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generated document '{safe_name}' not found.",
        )

    # Check RBAC classification against ProjectCard record if registered
    card = (
        await session.execute(
            select(ProjectCard).where(ProjectCard.generated_file_name == safe_name)
        )
    ).scalars().first()
    if card and not check_document_access(current_user.role, card.access_level):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: role '{current_user.role}' cannot download '{card.access_level}' document.",
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
    summary="List created project cards accessible by caller's role",
)
async def list_projects(
    current_user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[ProjectCardItem]:
    """Retrieve list of created project cards filtered by caller's RBAC clearance."""
    all_projects = await get_all_projects(session)
    return [
        p for p in all_projects if check_document_access(current_user.role, p.access_level)
    ]


@router.post(
    "/documents/check-compliance",
    response_model=ComplianceCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect uploaded draft DOCX document for normative DOU compliance",
    description="Checks uploaded .docx draft against 10+ normative rules of OD-184 and Section 3.3 of Guidelines.",
)
async def check_document_compliance_endpoint(
    file: UploadFile = File(..., description="Draft DOCX document to inspect"),
    current_user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ComplianceCheckResponse:
    """Validate uploaded draft DOCX against OD-184 and Methodological Guidelines."""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    safe_name = file.filename or "draft.docx"
    if not safe_name.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file extension. Only .docx draft documents are supported for compliance check.",
        )
    try:
        return await check_docx_compliance(session=session, file_bytes=file_bytes, file_name=safe_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to inspect DOCX document: {e}",
        )


# =============================================================================
# Document Hot-Reload Versioning & Lifecycle Endpoints (Section 6)
# =============================================================================


@router.post(
    "/documents/upload-version",
    response_model=DocumentVersionItem,
    status_code=status.HTTP_201_CREATED,
    summary="Upload new regulatory document edition (PDF or DOCX)",
    description=(
        "Requires dou_specialist or admin role. Archives previous versions, parses chunks on the fly, "
        "and indexes them in PostgreSQL without requiring server restart."
    ),
)
async def upload_version(
    raw_request: Request,
    file: UploadFile = File(..., description="PDF or DOCX regulatory document file"),
    doc_code: str = Form(..., description="Document identifier code, e.g. OD-184"),
    title: str = Form(..., description="Full regulatory document title"),
    version: str = Form(..., description="Version identifier, e.g. 2.0"),
    doc_type: str = Form("instruction", description="Document type: instruction, guideline, matrix, template"),
    access_level: str = Form("public", description="Access level: public, dsp, confidential, secret"),
    current_user: UserContext = Depends(require_role(["dou_specialist", "admin"])),
    session: AsyncSession = Depends(get_db),
) -> DocumentVersionItem:
    """Upload and hot-reload a new version of a regulatory document."""
    client_ip = raw_request.client.host if raw_request.client else None
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    safe_name = file.filename or f"{doc_code}.pdf"
    suffix = Path(safe_name).suffix.lower()
    if suffix not in [".pdf", ".docx"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{suffix}'. Only .pdf and .docx documents are supported.",
        )

    clean_access = access_level.strip().lower()
    if clean_access not in ["public", "dsp", "confidential", "secret"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid access_level '{access_level}'. Allowed: public, dsp, confidential, secret.",
        )

    try:
        db_doc = await upload_document_version(
            session=session,
            file_bytes=file_bytes,
            file_name=safe_name,
            doc_code=doc_code.strip(),
            title=title.strip(),
            version=version.strip(),
            doc_type=doc_type.strip(),
            access_level=clean_access,
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    await log_audit_event(
        session=session,
        user_role=current_user.role,
        user_name=current_user.username,
        action_type="upload_version",
        query_text=f"Uploaded {doc_code} v{version} ({file.filename})",
        response_summary=f"Successfully indexed version {version} with access={clean_access}",
        status="success",
        latency_ms=0.0,
        ip_address=client_ip,
    )
    await session.commit()

    chunk_count_stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == db_doc.id)
    chunk_count = (await session.execute(chunk_count_stmt)).scalar() or 0

    return DocumentVersionItem(
        id=str(db_doc.id),
        doc_code=db_doc.doc_code,
        title=db_doc.title,
        doc_type=db_doc.doc_type,
        version=db_doc.version,
        access_level=db_doc.access_level,
        is_active=db_doc.is_active,
        file_name=db_doc.file_name,
        file_size=db_doc.file_size,
        sha256=db_doc.sha256,
        chunk_count=int(chunk_count),
        created_at=db_doc.created_at,
        updated_at=db_doc.updated_at,
    )


@router.get(
    "/documents/versions",
    response_model=List[DocumentVersionItem],
    status_code=status.HTTP_200_OK,
    summary="List all registered documents and their versions",
    description="Returns all registered documents and their editions with chunk counts, active status, and access levels.",
)
async def list_document_versions(
    session: AsyncSession = Depends(get_db),
) -> List[DocumentVersionItem]:
    """Return all document versions with chunk counts and active statuses."""
    return await get_all_document_versions(session)


@router.post(
    "/documents/{doc_code}/activate-version/{version}",
    response_model=DocumentVersionItem,
    status_code=status.HTTP_200_OK,
    summary="Activate document version (hot-reload switch or rollback)",
    description="Sets selected version to is_active=True and all other versions to is_active=False. Requires dou_specialist or admin.",
)
async def switch_document_version(
    doc_code: str,
    version: str,
    raw_request: Request,
    current_user: UserContext = Depends(require_role(["dou_specialist", "admin"])),
    session: AsyncSession = Depends(get_db),
) -> DocumentVersionItem:
    """Activate specified version for a regulatory document, archiving all other versions."""
    client_ip = raw_request.client.host if raw_request.client else None
    target_doc = await activate_document_version(session, doc_code.strip(), version.strip())

    await log_audit_event(
        session=session,
        user_role=current_user.role,
        user_name=current_user.username,
        action_type="activate_version",
        query_text=f"Activated {doc_code} v{version}",
        response_summary=f"Switched active edition of {doc_code} to v{version}",
        status="success",
        latency_ms=0.0,
        ip_address=client_ip,
    )
    await session.commit()

    chunk_count_stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == target_doc.id)
    chunk_count = (await session.execute(chunk_count_stmt)).scalar() or 0

    return DocumentVersionItem(
        id=str(target_doc.id),
        doc_code=target_doc.doc_code,
        title=target_doc.title,
        doc_type=target_doc.doc_type,
        version=target_doc.version,
        access_level=target_doc.access_level,
        is_active=target_doc.is_active,
        file_name=target_doc.file_name,
        file_size=target_doc.file_size,
        sha256=target_doc.sha256,
        chunk_count=int(chunk_count),
        created_at=target_doc.created_at,
        updated_at=target_doc.updated_at,
    )


# =============================================================================
# Security Audit Trail & Authentication Endpoints (Section 6)
# =============================================================================


@router.get(
    "/audit/logs",
    response_model=List[AuditLogItem],
    status_code=status.HTTP_200_OK,
    summary="Retrieve security and operational audit trail records",
    description="Requires security_auditor or admin role. Filter by action_type, user_role, status.",
)
async def get_audit_trail(
    action_type: Optional[str] = None,
    user_role: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: UserContext = Depends(require_role(["security_auditor", "admin"])),
    session: AsyncSession = Depends(get_db),
) -> List[AuditLogItem]:
    """Retrieve filtered audit records from PostgreSQL audit_logs table."""
    return await query_audit_logs(
        session=session,
        action_type=action_type,
        user_role=user_role,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/auth/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue JWT access token for user identity and role",
)
async def generate_token(
    request: TokenRequest,
) -> TokenResponse:
    """Generate signed JWT token containing subject and RBAC role (requires password for admin)."""
    norm_role = normalize_role(request.role)
    if norm_role == UserRole.ADMIN.value:
        if not request.password or request.password != settings.ADMIN_DEMO_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin token issuance requires valid administrator password.",
            )
    token = create_access_token({"sub": request.username, "role": norm_role})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=norm_role,
        username=request.username,
    )

