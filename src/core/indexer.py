"""Database indexing and persistence module for regulatory knowledge base.

Handles database seeding, document chunking, full-text tsvector index population,
defined terms glossary, approval matrix rules, and modular templates registry.
"""

from dataclasses import asdict
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.extractor import (
    ApprovalRuleDTO,
    DefinedTermDTO,
    ExtractedDocument,
    TemplateModuleDTO,
    extract_approval_matrix_data,
    extract_defined_terms,
    extract_guidelines_document,
    extract_pdf_instruction,
    extract_template_modules,
)
from src.db.models import (
    ApprovalRule,
    AuditLog,
    DefinedTerm,
    DocumentChunk,
    KnowledgeDocument,
    ProjectCard,
    TemplateModule,
)

logger = logging.getLogger(__name__)


async def clear_database(session: AsyncSession) -> None:
    """Clear all regulatory tables in correct dependency order."""
    logger.info("Cleaning existing regulatory records from database...")
    # Clean dependent tables first
    await session.execute(delete(ProjectCard))
    await session.execute(delete(DocumentChunk))
    await session.execute(delete(TemplateModule))
    await session.execute(delete(ApprovalRule))
    await session.execute(delete(DefinedTerm))
    await session.execute(delete(KnowledgeDocument))
    await session.commit()
    logger.info("Database cleaned successfully.")


async def save_extracted_document(
    session: AsyncSession, doc: ExtractedDocument
) -> KnowledgeDocument:
    """Persist an ExtractedDocument and all its DocumentChunk instances."""
    db_doc = KnowledgeDocument(
        id=uuid.uuid4(),
        doc_code=doc.doc_code,
        title=doc.title,
        doc_type=doc.doc_type,
        version=doc.version,
        access_level=doc.access_level,
        is_active=True,
        file_name=doc.file_name,
        file_size=doc.file_size,
        sha256=doc.sha256,
    )
    session.add(db_doc)
    await session.flush()

    for chunk in doc.chunks:
        db_chunk = DocumentChunk(
            id=uuid.uuid4(),
            document_id=db_doc.id,
            chapter=chunk.chapter,
            clause=chunk.clause,
            page_number=chunk.page_number,
            content=chunk.content,
            metadata_json=chunk.metadata,
        )
        session.add(db_chunk)

    await session.flush()
    return db_doc


async def save_defined_terms(
    session: AsyncSession, terms: List[DefinedTermDTO]
) -> int:
    """Persist canonical terms and abbreviations into defined_terms table."""
    count = 0
    for t in terms:
        db_term = DefinedTerm(
            id=uuid.uuid4(),
            canonical=t.canonical,
            expansion=t.expansion,
            definition=t.definition,
            source_doc_code=t.source_doc_code,
            clause=t.clause,
            page_number=t.page_number,
        )
        session.add(db_term)
        count += 1
    await session.flush()
    return count


async def save_approval_rules(
    session: AsyncSession, rules: List[ApprovalRuleDTO]
) -> Dict[int, uuid.UUID]:
    """Persist approval rules and return mapping of rule_number -> UUID."""
    rule_map: Dict[int, uuid.UUID] = {}
    for r in rules:
        rule_id = uuid.uuid4()
        db_rule = ApprovalRule(
            id=rule_id,
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
            extra_info=r.extra_info,
        )
        session.add(db_rule)
        rule_map[r.rule_number] = rule_id

    await session.flush()
    return rule_map


async def save_template_modules(
    session: AsyncSession,
    templates: List[TemplateModuleDTO],
    rule_map: Dict[int, uuid.UUID],
) -> int:
    """Register modular templates in template_modules and knowledge_documents."""
    count = 0
    for tm in templates:
        rule_id = rule_map.get(tm.default_rule_number)
        db_tm = TemplateModule(
            id=uuid.uuid4(),
            module_code=tm.module_code,
            doc_kind=tm.doc_kind,
            title=tm.title,
            reg_number=tm.reg_number,
            version=tm.version,
            file_name=tm.file_name,
            fields_schema=tm.fields_schema,
            default_rule_id=rule_id,
        )
        session.add(db_tm)

        # Also store template info as searchable knowledge document
        template_doc = ExtractedDocument(
            doc_code=tm.module_code,
            title=f"{tm.doc_kind}: {tm.title} (Модуль {tm.reg_number})",
            doc_type="template",
            version=tm.version,
            access_level="public",
            file_name=tm.file_name,
            file_size=tm.file_size,
            sha256=tm.sha256,
            chunks=tm.chunks,
        )
        await save_extracted_document(session, template_doc)
        count += 1

    await session.flush()
    return count


async def index_all_materials(
    session: AsyncSession,
    materials_dir: Optional[Path] = None,
    reset: bool = True,
) -> Dict[str, Any]:
    """Execute complete extraction and database indexing workflow."""
    target_dir = materials_dir or settings.MATERIALS_DIR
    logger.info(f"Starting complete indexing of materials from: {target_dir}")

    if reset:
        await clear_database(session)

    # 1. Process PDF Instruction (51 pages)
    pdf_files = list(target_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"Instruction PDF file not found in {target_dir}")
    pdf_doc = extract_pdf_instruction(pdf_files[0])
    db_pdf = await save_extracted_document(session, pdf_doc)

    # 2. Extract and save Defined Terms & Abbreviations
    terms = extract_defined_terms(pdf_doc)
    saved_terms_count = await save_defined_terms(session, terms)

    # 3. Process Methodological Guidelines DOCX
    guide_files = [f for f in target_dir.iterdir() if "методические" in f.name.lower() and f.suffix == ".docx"]
    if not guide_files:
        raise FileNotFoundError(f"Methodological guidelines file not found in {target_dir}")
    guide_doc = extract_guidelines_document(guide_files[0])
    db_guide = await save_extracted_document(session, guide_doc)

    # 4. Process Approval Matrix DOCX and Rules
    matrix_files = [f for f in target_dir.iterdir() if "матрица" in f.name.lower() and f.suffix == ".docx"]
    if not matrix_files:
        raise FileNotFoundError(f"Approval matrix file not found in {target_dir}")
    matrix_doc, rules = extract_approval_matrix_data(matrix_files[0])
    db_matrix = await save_extracted_document(session, matrix_doc)
    rule_map = await save_approval_rules(session, rules)

    # 5. Process and Register 7 Modular Templates
    templates = extract_template_modules(target_dir)
    saved_templates_count = await save_template_modules(session, templates, rule_map)

    # Commit the transaction
    await session.commit()

    # Query final counts for validation
    res_docs = await session.execute(select(func.count(KnowledgeDocument.id)))
    docs_count = res_docs.scalar() or 0

    res_chunks = await session.execute(select(func.count(DocumentChunk.id)))
    chunks_count = res_chunks.scalar() or 0

    res_terms = await session.execute(select(func.count(DefinedTerm.id)))
    terms_count = res_terms.scalar() or 0

    res_rules = await session.execute(select(func.count(ApprovalRule.id)))
    rules_count = res_rules.scalar() or 0

    res_tm = await session.execute(select(func.count(TemplateModule.id)))
    tm_count = res_tm.scalar() or 0

    summary = {
        "documents_count": docs_count,
        "chunks_count": chunks_count,
        "terms_count": terms_count,
        "approval_rules_count": rules_count,
        "template_modules_count": tm_count,
    }

    logger.info(f"Indexing completed successfully! Summary: {summary}")
    return summary


import re


async def search_chunks_fulltext(
    session: AsyncSession,
    query_text: str,
    top_k: int = 5,
    min_rank: float = 0.01,
) -> List[Dict[str, Any]]:
    """Execute PostgreSQL full-text search against Russian TSVECTOR with clause and metadata ranking."""
    if not query_text or not query_text.strip():
        return []

    clean_query = query_text.strip()
    # Check for clause pattern (e.g. "4.2.3", "п. 4.2.3", "пункт 10.6")
    clause_match = re.search(r"\b(\d+(?:\.\d+)+)\b", clean_query)
    clause_candidate = clause_match.group(1) if clause_match else clean_query

    sql = text("""
        SELECT 
            c.id,
            c.chapter,
            c.clause,
            c.page_number,
            c.content,
            c.metadata_json,
            d.doc_code,
            d.title as doc_title,
            d.version,
            d.access_level,
            ts_rank_cd(c.search_vector, plainto_tsquery('russian', :query)) as rank,
            CASE 
                WHEN LOWER(c.clause) = LOWER(:clean_query) THEN 100.0
                WHEN c.clause = :clause_candidate THEN 90.0
                WHEN LOWER(d.doc_code) = LOWER(:clean_query) THEN 80.0
                WHEN c.clause ILIKE :like_query THEN 70.0
                WHEN d.title ILIKE :like_query THEN 60.0
                WHEN c.search_vector @@ plainto_tsquery('russian', :query) THEN 50.0
                ELSE 10.0
            END as match_priority
        FROM document_chunks c
        JOIN knowledge_documents d ON c.document_id = d.id
        WHERE c.search_vector @@ plainto_tsquery('russian', :query)
           OR c.content ILIKE :like_query
           OR c.clause = :clause_candidate
           OR c.clause ILIKE :like_query
           OR c.chapter ILIKE :like_query
           OR d.doc_code ILIKE :like_query
           OR d.title ILIKE :like_query
        ORDER BY match_priority DESC, rank DESC, c.page_number ASC
        LIMIT :top_k;
    """)

    res = await session.execute(
        sql,
        {
            "query": clean_query,
            "clean_query": clean_query,
            "clause_candidate": clause_candidate,
            "like_query": f"%{clean_query}%",
            "top_k": top_k,
        },
    )

    rows = res.fetchall()
    results = []
    for row in rows:
        score = float(row.rank) if row.rank else (float(row.match_priority) / 100.0)
        results.append({
            "id": str(row.id),
            "chapter": row.chapter,
            "clause": row.clause,
            "page_number": row.page_number,
            "content": row.content,
            "metadata": row.metadata_json,
            "doc_code": row.doc_code,
            "doc_title": row.doc_title,
            "version": row.version,
            "access_level": row.access_level,
            "relevance_score": score,
        })
    return results


async def lookup_defined_term(
    session: AsyncSession, term: str
) -> Optional[Dict[str, Any]]:
    """Lookup term or abbreviation definition in glossary with case-insensitivity and expansion support."""
    if not term or not term.strip():
        return None

    clean_term = term.strip()
    upper_term = clean_term.upper()

    # 1. Exact canonical match
    stmt = select(DefinedTerm).where(
        func.upper(DefinedTerm.canonical) == upper_term
    )
    res = await session.execute(stmt)
    dt = res.scalar_one_or_none()
    if dt:
        return {
            "id": str(dt.id),
            "canonical": dt.canonical,
            "expansion": dt.expansion,
            "definition": dt.definition,
            "source_doc_code": dt.source_doc_code,
            "clause": dt.clause,
            "page_number": dt.page_number,
        }

    # 2. Exact or prefix expansion match
    stmt_exp = select(DefinedTerm).where(
        (func.upper(DefinedTerm.expansion) == upper_term)
        | (DefinedTerm.expansion.ilike(f"{clean_term}%"))
    )
    res_exp = await session.execute(stmt_exp)
    dt_exp = res_exp.scalars().first()
    if dt_exp:
        return {
            "id": str(dt_exp.id),
            "canonical": dt_exp.canonical,
            "expansion": dt_exp.expansion,
            "definition": dt_exp.definition,
            "source_doc_code": dt_exp.source_doc_code,
            "clause": dt_exp.clause,
            "page_number": dt_exp.page_number,
        }

    # 3. Substring match fallback
    stmt_sub = select(DefinedTerm).where(
        DefinedTerm.canonical.ilike(f"%{clean_term}%")
        | DefinedTerm.expansion.ilike(f"%{clean_term}%")
    )
    res_sub = await session.execute(stmt_sub)
    dt_sub = res_sub.scalars().first()
    if dt_sub:
        return {
            "id": str(dt_sub.id),
            "canonical": dt_sub.canonical,
            "expansion": dt_sub.expansion,
            "definition": dt_sub.definition,
            "source_doc_code": dt_sub.source_doc_code,
            "clause": dt_sub.clause,
            "page_number": dt_sub.page_number,
        }

    return None
