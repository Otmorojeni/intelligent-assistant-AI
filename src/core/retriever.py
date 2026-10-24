"""Hybrid retrieval core for regulatory knowledge base.

Implements PostgreSQL full-text search (ts_rank_cd on Russian search_vector),
pg_trgm trigram similarity, clause number boosting, defined terms boosting,
RBAC access level filtering, and 0.0% - 100.0% relevance score normalization.
"""

import logging
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import DefinedTerm, DocumentChunk, KnowledgeDocument
from src.schemas.api_models import DetectedTermRef, SourceRef

logger = logging.getLogger(__name__)

from src.core.security import get_role_access_levels

# Domain query expansion dictionary for DOU terminology & synonyms
DOU_QUERY_EXPANSIONS: Dict[str, str] = {
    "мэдо": "межведомственного электронного документооборота МЭДО 3.1.1 4.1.2",
    "иод": "информационно-обзорный документ ИОД 2.11",
    "особое мнение": "особое мнение отказ от подписания акта замечания 9.14 10.14",
    "отказ от подписания": "отказ от подписания фиксируется в акте особое мнение 9.14",
    "приемочных испытаний": "акт приемочных испытаний 9.14",
    "гербовая печать": "печать с воспроизведением Государственного герба гербовая печать 6.4",
    "гербовой печатью": "печать с воспроизведением Государственного герба гербовая печать 6.4",
    "после работы": "регистрация входящих документов после окончания рабочего времени следующий рабочий день 4.5 5.4",
    "занести в базу": "регистрация входящих документов в день поступления следующий рабочий день 4.5 5.4",
    "приеме документа в архив": "прием электронных документов в архив проверка электронной подписи 11.4",
}

RUSSIAN_STOPWORDS: Set[str] = {
    "как", "что", "кто", "где", "когда", "какой", "какая", "какие", "каков", "каковы",
    "сколько", "почему", "зачем", "куда", "откуда",
    "для", "при", "или", "его", "она", "они", "это", "все", "так", "уже", "еще", "без",
    "над", "под", "про", "через", "после", "перед", "между", "если", "чем", "тем",
    "быть", "есть", "был", "была", "были", "будет", "может", "могут", "должен", "должна",
    "должны", "нужно", "надо", "можно", "нельзя", "такое", "такой", "этот", "эта", "эти",
}


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
    max_chars: int = 1200,
) -> str:
    """Generate informative quote excerpt from chunk content while preserving normative context."""
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


def _tokenize_for_bm25(text_str: str) -> List[str]:
    """Tokenize Russian & alphanumeric text into stemmed tokens + clause numbers for BM25."""
    raw_tokens = re.findall(r"\d+(?:\.\d+)+|[а-яА-ЯёЁa-zA-Z0-9]{2,}", text_str.lower())
    out: List[str] = []
    for tok in raw_tokens:
        if tok in RUSSIAN_STOPWORDS:
            continue
        out.append(tok)
        if len(tok) >= 4 and not tok[0].isdigit():
            stem = get_russian_stem(tok)
            if stem != tok:
                out.append(stem)
    return out


def _char_ngram_vector(text_str: str, dim: int = 256) -> np.ndarray:
    """Compute fast L2-normalized hashed char-4gram + word-stem semantic vector (0 MB external weights)."""
    vec = np.zeros(dim, dtype=np.float32)
    clean = re.sub(r"\s+", " ", text_str.lower()).strip()
    if not clean:
        return vec
    # Word stems (higher weight)
    for tok in _tokenize_for_bm25(clean):
        idx = hash(tok) % dim
        vec[idx] += 2.0
    # Char 4-grams for morphological & semantic robustness
    padded = f" {clean[:1500]} "
    for i in range(len(padded) - 3):
        ng = padded[i : i + 4]
        idx = hash(ng) % dim
        vec[idx] += 0.5
    norm = float(np.linalg.norm(vec))
    if norm > 1e-8:
        vec /= norm
    return vec


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
    bm25_norm: float = 0.0,
    semantic_sim: float = 0.0,
    rrf_boost: float = 0.0,
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

    # 2. Full-text search rank (ts_rank_cd) + query content word coverage
    all_query_words = [
        w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", query.lower())
        if len(w) >= 3 and w not in RUSSIAN_STOPWORDS
    ]
    if not all_query_words:
        all_query_words = [w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", query.lower()) if len(w) >= 3]
    content_lower = chunk_content.lower()
    matched_words = [
        w
        for w in all_query_words
        if re.search(rf"(?<![а-яА-ЯёЁa-zA-Z0-9]){re.escape(get_russian_stem(w))}", content_lower)
    ]
    coverage = len(matched_words) / len(all_query_words) if all_query_words else 0.0

    exact_contrib = min(ts_rank_exact * 120.0, 45.0) if ts_rank_exact > 0 else 0.0
    or_contrib = 0.0
    if ts_rank_or > 0:
        if coverage >= 0.4 and (len(matched_words) >= 2 or len(all_query_words) == 1):
            or_contrib = min(ts_rank_or * 60.0 * coverage, 35.0)
        else:
            # Low keyword coverage (e.g. only 1 word incidental match out of many)
            or_contrib = min(ts_rank_or * 15.0 * coverage, 5.0)

    score += max(exact_contrib, or_contrib)

    # High stem-coverage bonus on long normative chunks where ts_rank_cd is diluted by length
    has_multi_match = len(matched_words) >= 2 or (len(all_query_words) == 1 and len(matched_words) == 1)
    if (ts_rank_exact > 0 or ts_rank_or > 0 or bm25_norm > 0.25) and coverage >= 0.5 and has_multi_match:
        score += min(coverage * 24.0, 24.0)

    # 3. Hybrid BM25 + Semantic Vector + Reciprocal Rank Fusion (RRF) contribution
    if has_multi_match and coverage >= 0.4:
        if bm25_norm > 0.15:
            score += min(bm25_norm * 22.0, 22.0)
        if semantic_sim > 0.22:
            score += min((semantic_sim - 0.15) * 25.0, 15.0)
        if rrf_boost > 0:
            score += min(rrf_boost, 12.0)

    # 4. Trigram similarity
    if content_sim > 0.08:
        score += min(content_sim * 50.0, 25.0)

    if clause_sim > 0.15:
        score += min(clause_sim * 40.0, 20.0)

    # 5. Defined corporate terms boosting with word boundary checking
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

    # 6. Direct substring occurrence in content
    query_clean = query.strip().lower()
    if len(query_clean) >= 4 and query_clean in content_lower:
        score += 20.0

    # 7. Document code or template registration number match (e.g., OD-184, УТВ-01, MOD-ORDER-IS)
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
    """Execute hybrid retrieval (PostgreSQL FTS + BM25Okapi + Semantic Vector + RRF) with RBAC."""
    if not query or not query.strip():
        return []

    clean_query = query.strip()
    expanded_query = clean_query
    q_low = clean_query.lower()
    for trigger_phrase, expansion_str in DOU_QUERY_EXPANSIONS.items():
        if trigger_phrase in q_low:
            expanded_query = f"{expanded_query} {expansion_str}"

    clause_candidates = extract_clause_identifiers(expanded_query)
    allowed_levels = get_allowed_access_levels(user_role)
    if detected_terms is None:
        detected_terms = await detect_query_terms(session, clean_query)

    # Also expand query with detected glossary term expansions
    for dt in detected_terms:
        if dt.expansion and dt.expansion.lower() not in expanded_query.lower():
            expanded_query = f"{expanded_query} {dt.expansion}"

    # Construct broad OR query for websearch_to_tsquery
    significant_words = [
        w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", expanded_query)
        if len(w) >= 2 and w.lower() not in RUSSIAN_STOPWORDS
    ]
    if not significant_words:
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
        LIMIT 80;
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
    if not rows:
        return []

    # Compute Hybrid BM25Okapi + Dense Semantic Vector + Reciprocal Rank Fusion (RRF) over candidate set
    query_bm25_tokens = _tokenize_for_bm25(expanded_query)
    corpus_tokens = [
        _tokenize_for_bm25(f"{r.chapter} {r.clause} {r.content}") for r in rows
    ]
    bm25_scores = np.zeros(len(rows), dtype=np.float32)
    if query_bm25_tokens and any(corpus_tokens):
        try:
            bm25 = BM25Okapi(corpus_tokens)
            bm25_scores = np.array(bm25.get_scores(query_bm25_tokens), dtype=np.float32)
        except Exception as e:
            logger.debug("BM25 scoring skipped: %s", e)

    max_bm25 = float(np.max(bm25_scores)) if len(bm25_scores) > 0 else 0.0
    bm25_norms = (bm25_scores / max_bm25) if max_bm25 > 1e-6 else np.zeros(len(rows), dtype=np.float32)

    q_vec = _char_ngram_vector(expanded_query)
    sem_scores = np.array(
        [float(np.dot(q_vec, _char_ngram_vector(f"{r.chapter} {r.clause} {r.content}"))) for r in rows],
        dtype=np.float32,
    )

    # Reciprocal Rank Fusion (RRF) across FTS rank, BM25 rank, and Semantic Vector rank
    fts_order = np.argsort(-np.array([float(r.ts_rank_exact or 0.0) * 2.0 + float(r.ts_rank_or or 0.0) for r in rows]))
    bm25_order = np.argsort(-bm25_scores)
    sem_order = np.argsort(-sem_scores)

    fts_rank = {int(idx): rank + 1 for rank, idx in enumerate(fts_order)}
    bm25_rank = {int(idx): rank + 1 for rank, idx in enumerate(bm25_order)}
    sem_rank = {int(idx): rank + 1 for rank, idx in enumerate(sem_order)}

    k_rrf = 20.0
    max_rrf = 3.0 / (k_rrf + 1.0)
    candidates: List[SourceRef] = []

    for idx, row in enumerate(rows):
        reg_num = None
        if isinstance(row.metadata_json, dict):
            reg_num = row.metadata_json.get("reg_number")

        rrf_val = (
            1.0 / (k_rrf + fts_rank[idx])
            + 1.0 / (k_rrf + bm25_rank[idx])
            + 1.0 / (k_rrf + sem_rank[idx])
        )
        rrf_boost = (rrf_val / max_rrf) * 12.0 if max_rrf > 0 else 0.0

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
            bm25_norm=float(bm25_norms[idx]),
            semantic_sim=float(sem_scores[idx]),
            rrf_boost=rrf_boost,
        )

        quote = generate_quote_excerpt(row.content, clean_query, detected_terms)

        source_ref = SourceRef(
            document_code=row.doc_code,
            document_title=row.doc_title,
            chapter=row.chapter,
            clause=row.clause,
            page_number=row.page_number,
            quote=quote,
            full_content=row.content,
            relevance_pct=relevance_pct,
            version=row.version,
            access_level=row.access_level,
        )
        candidates.append(source_ref)

    # Sort descending by calculated relevance_pct
    candidates.sort(key=lambda s: s.relevance_pct, reverse=True)
    return candidates[:top_k]
