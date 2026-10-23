"""Hybrid retrieval core for regulatory knowledge base.

Implements PostgreSQL full-text search (ts_rank_cd on Russian search_vector),
pg_trgm trigram similarity, clause number boosting, defined terms boosting,
RBAC access level filtering, and 0.0% - 100.0% relevance score normalization.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import DefinedTerm, DocumentChunk, KnowledgeDocument
from src.schemas.api_models import DetectedTermRef, SourceRef

logger = logging.getLogger(__name__)

from src.core.security import get_role_access_levels


def get_allowed_access_levels(user_role: str) -> List[str]:
    """Return list of allowed document access_level values for given user role."""
    return get_role_access_levels(user_role)


def extract_clause_identifiers(query: str) -> List[str]:
    """Extract clause identifiers like '4.1.3', '10.6', '1.4' from user query."""
    if not query:
        return []

    # Patterns like "п. 4.1.3", "пп. 4.1.3, 4.1.4", "пункт 10.6", "подпункт 2.3", "4.1.3", "раздел 4"
    candidates = []
    # 1. Multi-level clause numbers (e.g., 4.1.3, 10.16.1, 1.4)
    for m in re.finditer(r"\b(\d+(?:\.\d+)+)\b", query):
        val = m.group(1).strip().rstrip(".")
        if val and val not in candidates:
            candidates.append(val)

    # 2. Specific prefix matches like "п. 4", "пп. 4, 5", "пункт 10", "подпункт 2"
    for m in re.finditer(r"(?:пп\.|п\.|пункт(?:а|ы|ов|у|ом)?|подпункт(?:а|ы|ов|у|ом)?|стать(?:я|и|е|ю)|раздел(?:а|у|ом)?|гл\.|глав(?:а|ы|е|у))\s*(\d+(?:\.\d+)*)", query, re.I):
        c = m.group(1).strip().rstrip(".")
        if c and c not in candidates:
            candidates.append(c)

    return candidates


def get_russian_stem(word: str) -> str:
    """Extract basic Russian stem for inflected match."""
    w = word.strip().lower()
    # Strip common case endings
    for ending in ("ами", "ями", "ов", "ев", "ей", "ам", "ям", "ом", "ем", "ой", "ей", "ую", "юю", "ая", "яя", "ое", "ее", "ые", "ие", "ых", "их", "ым", "им", "а", "я", "у", "ю", "о", "е", "ы", "и"):
        if len(w) > len(ending) + 3 and w.endswith(ending):
            return w[:-len(ending)]
    return w


async def detect_query_terms(
    session: AsyncSession, query: str
) -> List[DetectedTermRef]:
    """Detect defined corporate terms and abbreviations mentioned in user query."""
    if not query or not query.strip():
        return []

    stmt = select(DefinedTerm)
    res = await session.execute(stmt)
    terms = res.scalars().all()

    detected: List[DetectedTermRef] = []
    seen_canonicals: Set[str] = set()

    clean_query = query.strip()
    query_lower = clean_query.lower()

    for t in terms:
        canonical = t.canonical.strip()
        expansion = t.expansion.strip()

        is_match = False

        # 1. Match canonical acronym:
        if len(canonical) <= 2:
            # Short 2-letter acronym (e.g., ИС, СП, РО, РК, ЭД, ЭП, ЦА, ПД): check uppercase boundary
            pattern = rf"(?<![а-яА-ЯёЁa-zA-Z0-9]){re.escape(canonical)}(?![а-яА-ЯёЁa-zA-Z0-9])"
            if re.search(pattern, clean_query):
                is_match = True
        else:
            # 3+ letter acronym (e.g., ЛНА, ИИС ДО, ДСП, СЭД, ДОУ): case-insensitive boundary
            pattern = rf"(?<![а-яА-ЯёЁa-zA-Z0-9]){re.escape(canonical)}(?![а-яА-ЯёЁa-zA-Z0-9])"
            if re.search(pattern, clean_query, re.I):
                is_match = True

        # 2. Multi-word or inflected term match (e.g., "лингвистическая экспертиза" in "лингвистической экспертизы")
        if not is_match and " " in canonical:
            term_words = [w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", canonical) if len(w) >= 3]
            if term_words:
                stems = [get_russian_stem(w) for w in term_words]
                if all(stem in query_lower for stem in stems):
                    is_match = True

        # 3. Match expansion:
        if not is_match and len(expansion) > 3:
            if expansion.lower() in query_lower:
                is_match = True
            elif " " in expansion:
                exp_words = [w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", expansion) if len(w) >= 3]
                if exp_words and len(exp_words) <= 4:
                    stems = [get_russian_stem(w) for w in exp_words]
                    if all(stem in query_lower for stem in stems):
                        is_match = True

        if is_match and canonical not in seen_canonicals:
            seen_canonicals.add(canonical)
            detected.append(
                DetectedTermRef(
                    canonical=canonical,
                    expansion=expansion,
                    definition=t.definition,
                )
            )

    return detected


def generate_quote_excerpt(
    content: str,
    query: str,
    detected_terms: Optional[List[DetectedTermRef]] = None,
    max_chars: int = 400,
) -> str:
    """Generate concise and informative quote excerpt from chunk content."""
    clean_content = " ".join(content.split())
    if len(clean_content) <= max_chars:
        return clean_content

    # Try to find match index of query keywords or detected terms
    search_tokens = []
    if detected_terms:
        for t in detected_terms:
            search_tokens.append(t.canonical)
            if len(t.expansion) < 40:
                search_tokens.append(t.expansion)

    query_words = [w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", query) if len(w) >= 3]
    search_tokens.extend(query_words)

    best_idx = -1
    for token in search_tokens:
        idx = clean_content.lower().find(token.lower())
        if idx != -1:
            best_idx = idx
            break

    if best_idx == -1 or best_idx < 100:
        return clean_content[:max_chars].rstrip() + "..."

    start = max(0, best_idx - 100)
    end = min(len(clean_content), start + max_chars)
    excerpt = clean_content[start:end].strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(clean_content) else ""
    return f"{prefix}{excerpt}{suffix}"


def calculate_relevance_pct(
    ts_rank_exact: float,
    ts_rank_or: float,
    clause_sim: float,
    content_sim: float,
    chunk_clause: str,
    clause_candidates: List[str],
    detected_terms: List[DetectedTermRef],
    chunk_content: str,
    doc_code: str,
    query: str,
    chunk_reg_number: Optional[str] = None,
) -> float:
    """Calculate normalized relevance percentage between 0.0% and 100.0%."""
    score = 0.0

    # 1. Clause number boost with segment/hierarchy awareness (prevents digit '1' matching '10.6')
    clean_clause = (chunk_clause or "").strip().lower()
    clean_digits = re.findall(r"\d+", clean_clause)
    is_exact_clause = False
    is_partial_clause = False

    for candidate in clause_candidates:
        c_cand = candidate.strip().lower()
        if clean_clause == c_cand or clean_clause.endswith(f" {c_cand}"):
            is_exact_clause = True
            break

        cand_digits = re.findall(r"\d+", c_cand)
        if cand_digits and clean_digits:
            if clean_digits == cand_digits:
                is_exact_clause = True
                break
            # Hierarchical match: candidate is parent section (e.g. cand=["4"], clause=["4", "1", "3"])
            elif len(cand_digits) < len(clean_digits) and clean_digits[:len(cand_digits)] == cand_digits:
                is_partial_clause = True
            # Or candidate is specific subclause and chunk is section header (e.g. cand=["4", "1", "3"], clause=["4", "1"])
            elif len(cand_digits) > len(clean_digits) and cand_digits[:len(clean_digits)] == clean_digits:
                is_partial_clause = True

    if is_exact_clause:
        score += 65.0
    elif is_partial_clause:
        score += 30.0

    # 2. Full-text search rank (ts_rank_cd) with query word coverage
    query_words = [w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", query.lower()) if len(w) >= 3]
    content_lower = chunk_content.lower()
    matched_words = [w for w in query_words if get_russian_stem(w) in content_lower]
    coverage = len(matched_words) / len(query_words) if query_words else 0.0

    if ts_rank_exact > 0:
        score += min(ts_rank_exact * 120.0, 45.0)
    elif ts_rank_or > 0:
        if coverage >= 0.4:
            score += min(ts_rank_or * 60.0 * coverage, 35.0)
        else:
            # Low keyword coverage (e.g. only 1 word incidental match out of many)
            score += min(ts_rank_or * 15.0 * coverage, 5.0)

    # 3. Trigram similarity
    if content_sim > 0.08:
        score += min(content_sim * 50.0, 25.0)

    if clause_sim > 0.15:
        score += min(clause_sim * 40.0, 20.0)

    # 4. Defined corporate terms boosting with word boundary checking
    for term in detected_terms:
        canonical = term.canonical.strip()
        # Word boundary pattern to avoid false positives (e.g. 'ИС' in 'инструкция', 'СП' in 'список')
        if len(canonical) <= 2:
            pattern = rf"(?<![а-яА-ЯёЁa-zA-Z0-9]){re.escape(canonical)}(?![а-яА-ЯёЁa-zA-Z0-9])"
            if re.search(pattern, chunk_content):
                score += 15.0
                break
        else:
            pattern = rf"(?<![а-яА-ЯёЁa-zA-Z0-9]){re.escape(canonical)}(?![а-яА-ЯёЁa-zA-Z0-9])"
            if re.search(pattern, chunk_content, re.I):
                score += 15.0
                break

        if term.expansion and term.expansion.lower() in content_lower:
            score += 10.0
            break

    # 5. Direct substring occurrence in content
    query_clean = query.strip().lower()
    if len(query_clean) >= 4 and query_clean in content_lower:
        score += 20.0

    # 6. Document code or template registration number match (e.g., OD-184, УТВ-01, MOD-ORDER-IS)
    if doc_code and doc_code.lower() == query_clean:
        score += 65.0
    elif doc_code and doc_code.lower() in query_clean:
        score += 35.0

    if chunk_reg_number and chunk_reg_number.lower() == query_clean:
        score += 65.0
    elif chunk_reg_number and chunk_reg_number.lower() in query_clean:
        score += 35.0

    # Cap strictly between 0.0 and 100.0, round to 1 decimal
    final_relevance = max(0.0, min(100.0, score))
    return round(final_relevance, 1)


async def retrieve_chunks(
    session: AsyncSession,
    query: str,
    user_role: str = "employee",
    top_k: int = 5,
    detected_terms: Optional[List[DetectedTermRef]] = None,
) -> List[SourceRef]:
    """Execute hybrid retrieval querying PostgreSQL with full-text, trigram similarity, and RBAC."""
    if not query or not query.strip():
        return []

    clean_query = query.strip()
    clause_candidates = extract_clause_identifiers(clean_query)
    allowed_levels = get_allowed_access_levels(user_role)
    if detected_terms is None:
        detected_terms = await detect_query_terms(session, clean_query)

    # Construct broad OR query for websearch_to_tsquery
    significant_words = [
        w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", clean_query)
        if len(w) >= 2
    ]
    or_query = " OR ".join(significant_words) if significant_words else clean_query

    # Clause match candidate list for SQL ANY parameter
    clause_param = clause_candidates if clause_candidates else ["__NO_CLAUSE__"]

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
            CASE 
                WHEN websearch_to_tsquery('russian', :query)::text <> '' 
                THEN ts_rank_cd(c.search_vector, websearch_to_tsquery('russian', :query))
                ELSE 0.0 
            END as ts_rank_exact,
            CASE 
                WHEN websearch_to_tsquery('russian', :or_query)::text <> '' 
                THEN ts_rank_cd(c.search_vector, websearch_to_tsquery('russian', :or_query))
                ELSE 0.0 
            END as ts_rank_or,
            similarity(c.clause, :clean_query) as clause_sim,
            similarity(c.content, :clean_query) as content_sim
        FROM document_chunks c
        JOIN knowledge_documents d ON c.document_id = d.id
        WHERE d.is_active = true
          AND d.access_level = ANY(:allowed_levels)
          AND (
              (websearch_to_tsquery('russian', :query)::text <> '' AND c.search_vector @@ websearch_to_tsquery('russian', :query))
              OR (websearch_to_tsquery('russian', :or_query)::text <> '' AND c.search_vector @@ websearch_to_tsquery('russian', :or_query))
              OR c.clause = ANY(:clause_candidates)
              OR c.clause ILIKE :like_query
              OR c.content ILIKE :like_query
              OR c.chapter ILIKE :like_query
              OR d.doc_code ILIKE :like_query
              OR d.title ILIKE :like_query
              OR c.metadata_json->>'reg_number' ILIKE :like_query
              OR similarity(c.clause, :clean_query) > 0.3
              OR similarity(c.content, :clean_query) > 0.1
          )
        ORDER BY 
            (CASE WHEN c.clause = ANY(:clause_candidates) THEN 100.0 ELSE 0.0 END) DESC,
            ts_rank_exact DESC, 
            ts_rank_or DESC, 
            c.page_number ASC
        LIMIT 50;
    """)

    res = await session.execute(
        sql,
        {
            "query": clean_query,
            "or_query": or_query,
            "clean_query": clean_query,
            "like_query": f"%{clean_query}%",
            "allowed_levels": allowed_levels,
            "clause_candidates": clause_param,
        },
    )

    rows = res.fetchall()
    candidates: List[SourceRef] = []

    for row in rows:
        reg_num = None
        if isinstance(row.metadata_json, dict):
            reg_num = row.metadata_json.get("reg_number")

        relevance_pct = calculate_relevance_pct(
            ts_rank_exact=float(row.ts_rank_exact or 0.0),
            ts_rank_or=float(row.ts_rank_or or 0.0),
            clause_sim=float(row.clause_sim or 0.0),
            content_sim=float(row.content_sim or 0.0),
            chunk_clause=row.clause,
            clause_candidates=clause_candidates,
            detected_terms=detected_terms,
            chunk_content=row.content,
            doc_code=row.doc_code,
            query=clean_query,
            chunk_reg_number=reg_num,
        )

        quote = generate_quote_excerpt(row.content, clean_query, detected_terms)

        source_ref = SourceRef(
            document_code=row.doc_code,
            document_title=row.doc_title,
            chapter=row.chapter,
            clause=row.clause,
            page_number=row.page_number,
            quote=quote,
            relevance_pct=relevance_pct,
            version=row.version,
            access_level=row.access_level,
        )
        candidates.append(source_ref)

    # Sort descending by calculated relevance_pct
    candidates.sort(key=lambda s: s.relevance_pct, reverse=True)
    return candidates[:top_k]
