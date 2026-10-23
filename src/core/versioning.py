"""Hot-reload document versioning and lifecycle management.

Handles dynamic upload of new regulatory document editions (PDF, DOCX),
automatic archival of previous editions (is_active = False), immediate live
tsvector indexing in PostgreSQL without server restarts, active version rollback,
and document version listing.
"""

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import uuid

import docx
from fastapi import HTTPException, status
import pymupdf
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.extractor import ExtractedChunk, ExtractedDocument
from src.db.models import AuditLog, DocumentChunk, KnowledgeDocument
from src.schemas.api_models import AuditLogItem, DocumentVersionItem

logger = logging.getLogger(__name__)

UPLOADS_DIR = settings.GENERATED_DOCS_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def compute_file_hash(path: Path) -> str:
    """Calculate SHA-256 checksum of local file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def parse_uploaded_document(
    file_path: Path,
    doc_code: str,
    title: str,
    version: str,
    doc_type: str = "instruction",
    access_level: str = "public",
) -> ExtractedDocument:
    """Parse uploaded PDF or DOCX file on the fly into structured ExtractedDocument and chunks."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size
    sha256 = compute_file_hash(file_path)
    suffix = file_path.suffix.lower()
    chunks: List[ExtractedChunk] = []

    if suffix == ".pdf":
        doc = pymupdf.open(file_path)
        current_chapter = "Титульный лист и общие положения"
        current_clause = "1.1"
        current_page = 1
        current_lines: List[str] = []

        for p_idx in range(len(doc)):
            page_num = p_idx + 1
            page_text = doc[p_idx].get_text().replace("\xa0", " ")
            lines = [l.strip() for l in page_text.split("\n") if l.strip()]

            for line in lines:
                m_chap = re.match(r"^(?:Глава|Раздел)\s+(\d+)\.?\s*(.*)", line, re.I)
                m_cl = re.match(r"^(\d+\.\d+(?:\.\d+)*)\.?\s*(.*)", line)

                if m_chap:
                    if current_lines:
                        chunks.append(
                            ExtractedChunk(
                                chapter=current_chapter,
                                clause=current_clause,
                                page_number=current_page,
                                content="\n".join(current_lines),
                                metadata={"doc_code": doc_code, "version": version, "clause": current_clause},
                            )
                        )
                        current_lines = []
                    current_chapter = line
                    current_clause = f"{m_chap.group(1)}.0"
                    current_page = page_num
                elif m_cl:
                    if current_lines:
                        chunks.append(
                            ExtractedChunk(
                                chapter=current_chapter,
                                clause=current_clause,
                                page_number=current_page,
                                content="\n".join(current_lines),
                                metadata={"doc_code": doc_code, "version": version, "clause": current_clause},
                            )
                        )
                        current_lines = []
                    current_clause = m_cl.group(1)
                    current_page = page_num
                    current_lines.append(line)
                else:
                    current_lines.append(line)

        if current_lines:
            chunks.append(
                ExtractedChunk(
                    chapter=current_chapter,
                    clause=current_clause,
                    page_number=current_page,
                    content="\n".join(current_lines),
                    metadata={"doc_code": doc_code, "version": version, "clause": current_clause},
                )
            )
        doc.close()

    elif suffix in [".docx", ".doc"]:
        doc = docx.Document(file_path)
        current_chapter = "Общие положения"
        current_clause = "1.1"
        current_lines: List[str] = []

        for p in doc.paragraphs:
            text = p.text.replace("\xa0", " ").strip()
            if not text:
                continue

            m_chap = re.match(r"^(?:Глава|Раздел|[1-9]\d*\.)\s+(.*)", text, re.I)
            m_cl = re.match(r"^(\d+\.\d+(?:\.\d+)*)\.?\s*(.*)", text)

            if m_cl:
                if current_lines:
                    chunks.append(
                        ExtractedChunk(
                            chapter=current_chapter,
                            clause=current_clause,
                            page_number=1,
                            content="\n".join(current_lines),
                            metadata={"doc_code": doc_code, "version": version, "clause": current_clause},
                        )
                    )
                    current_lines = []
                current_clause = m_cl.group(1)
                current_lines.append(text)
            elif m_chap and not m_cl:
                if current_lines:
                    chunks.append(
                        ExtractedChunk(
                            chapter=current_chapter,
                            clause=current_clause,
                            page_number=1,
                            content="\n".join(current_lines),
                            metadata={"doc_code": doc_code, "version": version, "clause": current_clause},
                        )
                    )
                    current_lines = []
                current_chapter = text
            else:
                current_lines.append(text)

        if current_lines:
            chunks.append(
                ExtractedChunk(
                    chapter=current_chapter,
                    clause=current_clause,
                    page_number=1,
                    content="\n".join(current_lines),
                    metadata={"doc_code": doc_code, "version": version, "clause": current_clause},
                )
            )

    # Fallback to guaranteed chunk if document body was freeform
    if not chunks:
        chunks.append(
            ExtractedChunk(
                chapter="Общие положения",
                clause="1.1",
                page_number=1,
                content=f"{title}. Версия регламента {version}.",
                metadata={"doc_code": doc_code, "version": version, "clause": "1.1"},
            )
        )

    return ExtractedDocument(
        doc_code=doc_code,
        title=title,
        doc_type=doc_type,
        version=version,
        access_level=access_level,
        file_name=file_path.name,
        file_size=file_size,
        sha256=sha256,
        chunks=chunks,
    )


async def upload_document_version(
    session: AsyncSession,
    file_bytes: bytes,
    file_name: str,
    doc_code: str,
    title: str,
    version: str,
    doc_type: str = "instruction",
    access_level: str = "public",
) -> KnowledgeDocument:
    """Save uploaded document edition, archive previous versions, parse chunks, and commit hot-reload."""
    from src.core.indexer import save_extracted_document

    safe_filename = Path(file_name).name
    target_path = UPLOADS_DIR / f"{doc_code}_v{version}_{safe_filename}"
    with open(target_path, "wb") as f:
        f.write(file_bytes)

    # 1. Fetch existing documents with the same doc_code
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.doc_code == doc_code)
    existing_docs = (await session.execute(stmt)).scalars().all()

    # 2. Archive previous versions or remove duplicate same version
    for prev_doc in existing_docs:
        if prev_doc.version == version:
            # Overwriting the exact same version edition
            await session.delete(prev_doc)
        else:
            prev_doc.is_active = False

    await session.flush()

    # 3. Parse the uploaded file on the fly
    extracted_doc = parse_uploaded_document(
        file_path=target_path,
        doc_code=doc_code,
        title=title,
        version=version,
        doc_type=doc_type,
        access_level=access_level,
    )

    # 4. Save new document and chunks with search_vector computed column
    db_doc = await save_extracted_document(session, extracted_doc)
    await session.commit()
    await session.refresh(db_doc)

    logger.info(
        f"Uploaded and activated new document edition: {doc_code} v{version} "
        f"({len(extracted_doc.chunks)} chunks, access={access_level})"
    )
    return db_doc


async def activate_document_version(
    session: AsyncSession,
    doc_code: str,
    version: str,
) -> KnowledgeDocument:
    """Switch active document edition: sets target to is_active=True, others to is_active=False."""
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.doc_code == doc_code)
    docs = (await session.execute(stmt)).scalars().all()

    if not docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with code '{doc_code}' not found.",
        )

    target_doc: Optional[KnowledgeDocument] = None
    for d in docs:
        if d.version == version:
            target_doc = d
            d.is_active = True
        else:
            d.is_active = False

    if not target_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version '{version}' for document '{doc_code}' not found.",
        )

    await session.commit()
    await session.refresh(target_doc)
    logger.info(f"Activated document edition {doc_code} v{version}")
    return target_doc


async def get_all_document_versions(
    session: AsyncSession,
) -> List[DocumentVersionItem]:
    """Retrieve full catalog of all document versions with chunk counts and active statuses."""
    stmt = (
        select(
            KnowledgeDocument,
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .outerjoin(DocumentChunk, KnowledgeDocument.id == DocumentChunk.document_id)
        .group_by(KnowledgeDocument.id)
        .order_by(KnowledgeDocument.doc_code, KnowledgeDocument.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()

    items: List[DocumentVersionItem] = []
    for doc, count in rows:
        items.append(
            DocumentVersionItem(
                id=str(doc.id),
                doc_code=doc.doc_code,
                title=doc.title,
                doc_type=doc.doc_type,
                version=doc.version,
                access_level=doc.access_level,
                is_active=doc.is_active,
                file_name=doc.file_name,
                file_size=doc.file_size,
                sha256=doc.sha256,
                chunk_count=int(count or 0),
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )
        )
    return items


async def query_audit_logs(
    session: AsyncSession,
    action_type: Optional[str] = None,
    user_role: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[AuditLogItem]:
    """Retrieve filtered audit trail log entries from PostgreSQL audit_logs table."""
    stmt = select(AuditLog)
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    if user_role:
        stmt = stmt.where(AuditLog.user_role == user_role)
    if status_filter:
        stmt = stmt.where(AuditLog.status == status_filter)

    stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)
    res = await session.execute(stmt)
    logs = res.scalars().all()

    return [
        AuditLogItem(
            id=str(log.id),
            timestamp=log.timestamp,
            user_role=log.user_role,
            user_name=log.user_name,
            action_type=log.action_type,
            query_text=log.query_text,
            response_summary=log.response_summary,
            status=log.status,
            latency_ms=log.latency_ms,
            ip_address=log.ip_address,
        )
        for log in logs
    ]
