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
    "после окончания рабочего": "регистрация входящих документов после окончания рабочего времени следующий рабочий день 4.5 5.4",
    "занести в базу": "регистрация входящих документов в день поступления следующий рабочий день 4.5 5.4",
    "приеме документа в архив": "прием электронных документов в архив проверка электронной подписи 11.4",
    "сопроводительного письма": "сопроводительное письмо внутренний документ служебная записка письмо содержит адресата заголовок 3.2 9.9 9.15.1",
    "сопроводительное письмо": "сопроводительное письмо внутренний документ служебная записка письмо содержит адресата заголовок 3.2 9.9 9.15.1",
    "служебную записку": "служебная записка внутренний документ сопроводительное письмо адресуется подразделению 3.2 9.15.1",
    "нормативный документ": "согласование проекта документа заинтересованные подразделения максимальный срок рассмотрения приказ положение регламент 10.1 10.2 10.3 10.6",
    "организовать согласование": "ответственный исполнитель одновременно направляет ПД заинтересованные подразделения первичное рассмотрение последовательность визирования 10.1 10.2 10.3 10.6",
    "сроки устанавливать": "максимальный срок каждого первичного и повторного рассмотрения рабочих дней 10.3 10.14 10.15",
    "сроки согласования": "максимальный срок каждого первичного и повторного рассмотрения рабочих дней 10.3 10.14 10.15",
    "реестр замечаний": "таблица замечаний реестр замечаний повторное рассмотрение Приложение № 1 10.4 10.5",
    "собрать замечания": "таблица замечаний автор содержание позиция исполнителя принято отклонено Приложение № 1 10.4 10.5",
    "на основе модульного": "модульный документ модуль документа Методические рекомендации проверка визирование 3.3 4.1 4.2 9.16.1",
    "проектного комитета": "проектный комитет MOD-DISP-PROJECT УТВ-06 9.5.7 роли Председатель Заместитель председателя Секретарь Члены",
    "проектный комитет": "проектный комитет MOD-DISP-PROJECT УТВ-06 9.5.7 роли Председатель Заместитель председателя Секретарь Члены",
    "рабочей группы": "рабочая группа MOD-DISP-WORKGROUP УТВ-07 9.5.7 роли руководитель заместитель секретарь члены",
    "рабочая группа": "рабочая группа MOD-DISP-WORKGROUP УТВ-07 9.5.7 роли руководитель заместитель секретарь члены",
    "от руки": "рукописный черновик изготовление проекта документа 2.1.4 5.1",
    "рукописн": "рукописный черновик изготовление проекта документа 2.1.4 5.1",
    "рукопис": "рукописный черновик изготовление проекта документа 2.1.4 5.1",
    "черновик": "проект документа черновик 2.1.4 5.1",
    "черновики": "проект документа черновик 2.1.4 5.1",
    "полужирн": "выделение текста полужирным шрифтом реквизиты 3.2 5.3",
    "полужирный": "выделение текста полужирным шрифтом реквизиты 3.2 5.3",
    "жирным": "выделение текста полужирным шрифтом реквизиты 3.2 5.3",
    "жирн": "выделение текста полужирным шрифтом реквизиты 3.2 5.3",
    "колонтитул": "колонтитулы нумерация страниц вторая последующие страницы 8.16 6.2 3.3",
    "колонтитулы": "колонтитулы нумерация страниц вторая последующие страницы 8.16 6.2 3.3",
    "нумерация страниц": "нумерация страниц колонтитулы арабскими цифрами 8.16 6.2",
    "нумераци": "нумерация страниц колонтитулы арабскими цифрами 8.16 6.2",
    "шрифт": "шрифт гарнитура размер кегль Times New Roman Arial PT Astra Serif 5.2",
    "шрифты": "шрифт гарнитура размер кегль Times New Roman Arial PT Astra Serif 5.2",
    "поля": "поля страницы левое правое верхнее нижнее 5.1",
    "полей": "поля страницы левое правое верхнее нижнее 5.1",
    "отступ": "абзацный отступ первая строка 1.25 см 5.3",
    "отступы": "абзацный отступ первая строка 1.25 см 5.3",
    "интервал": "межстрочный интервал одинарный полуторный 5.3",
    "интервалы": "межстрочный интервал одинарный полуторный 5.3",
}

RUSSIAN_STOPWORDS: Set[str] = {
    "как", "что", "кто", "где", "когда", "какой", "какая", "какие", "каков", "каковы",
    "сколько", "почему", "зачем", "куда", "откуда",
    "для", "при", "или", "его", "она", "они", "это", "все", "так", "уже", "еще", "без",
    "над", "под", "про", "через", "после", "перед", "между", "если", "чем", "тем",
    "быть", "есть", "был", "была", "были", "будет", "может", "могут", "должен", "должна",
    "должны", "нужно", "надо", "можно", "нельзя", "такое", "такой", "этот", "эта", "эти",
}

CONVERSATIONAL_FILLER_WORDS: Set[str] = {
    "мне", "меня", "мной", "мой", "моя", "мои", "нам", "наш", "вам", "ваш", "него", "нее", "них",
    "который", "которая", "которое", "которые", "которого", "которой", "которых", "которому", "которым",
    "впервые", "сейчас", "теперь", "сразу", "вообще", "очень", "просто", "пожалуйста",
    "подскажи", "подскажите", "скажи", "скажите", "расскажи", "расскажите", "объясни", "объясните",
    "помоги", "помогите", "проверь", "проверьте", "делать", "сделать", "дальше", "далее",
    "правильно", "корректно", "необходимо", "требуется", "следует", "готовлю", "подготовил", "подготовила",
    "большой", "небольшой", "несколько", "несколькими", "нескольких", "кому", "кого", "кем",
    "каким", "какими", "каких", "какую", "какому", "собрать", "организовать", "устанавливать",
    "коллега", "коллеги", "коллегой", "коллегам", "коллег",
    "сказал", "сказала", "сказали", "говорит", "говорят", "слышал", "слышала",
    "правда", "действительно", "регламенту", "регламент", "регламенте",
    "вопрос", "сомневаюсь", "уверен", "уверена", "думаю", "считаю",
    "знаешь", "знаете", "бывает", "слушай", "слушайте", "посоветуй", "посоветуйте",
    "скока", "скоко", "сколька", "скольки",
}

SLANG_SYNONYMS: Dict[str, str] = {
    "юзер": "пользователь",
    "юзеру": "пользователю",
    "юзера": "пользователя",
    "юзеров": "пользователей",
    "юзерам": "пользователям",
    "инфобез": "информационная безопасность",
    "инфобезопасности": "информационная безопасность",
    "ит": "информационные технологии",
    "иб": "информационная безопасность",
    "дбо": "дистанционное банковское обслуживание",
    "согласовалка": "маршрут согласования",
    "визирование": "согласование визирование",
    "доушник": "специалист делопроизводства",
    "кадровик": "специалист кадрового подразделения",
    "безопасник": "офицер информационной безопасности",
    "эцп": "электронная подпись",
}

CYR_TO_LAT_MAP: Dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

LAT_TO_CYR_MAP: Dict[str, str] = {
    "shch": "щ", "sch": "щ", "yo": "е", "zh": "ж", "ts": "ц", "ch": "ч", "sh": "ш",
    "yu": "ю", "ya": "я",
    "a": "а", "b": "б", "v": "в", "w": "в", "g": "г", "d": "д", "e": "е",
    "z": "з", "i": "и", "j": "й", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф",
    "h": "х", "c": "к", "y": "ы", "x": "х",
}

HOMOGLYPH_CYR_TO_LAT: Dict[str, str] = {
    "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x", "у": "y",
    "к": "k", "м": "m", "т": "t", "в": "b", "н": "h",
}

HOMOGLYPH_LAT_TO_CYR: Dict[str, str] = {
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
    "k": "к", "m": "м", "t": "т", "b": "в", "h": "н",
}


def transliterate_cyr_to_lat(text: str) -> str:
    """Transliterate Cyrillic text to Latin phonetic characters."""
    return "".join(CYR_TO_LAT_MAP.get(ch, ch) for ch in text.lower())


def transliterate_lat_to_cyr(text: str) -> str:
    """Transliterate Latin text to Cyrillic phonetic characters."""
    t = text.lower()
    for lat_multi, cyr_char in [
        ("shch", "щ"), ("sch", "щ"), ("yo", "е"), ("zh", "ж"),
        ("ts", "ц"), ("ch", "ч"), ("sh", "ш"), ("yu", "ю"), ("ya", "я")
    ]:
        t = t.replace(lat_multi, cyr_char)
    return "".join(LAT_TO_CYR_MAP.get(ch, ch) for ch in t)


def normalize_code_homoglyphs(code: str) -> Tuple[str, str]:
    """Produce pure Latin-homoglyph and pure Cyrillic-homoglyph normalized forms of a code string."""
    c_low = code.strip().lower()
    to_lat = "".join(HOMOGLYPH_CYR_TO_LAT.get(ch, ch) for ch in c_low)
    to_cyr = "".join(HOMOGLYPH_LAT_TO_CYR.get(ch, ch) for ch in c_low)
    return to_lat, to_cyr


def generate_code_variants(raw_code: str) -> Set[str]:
    """Generate all transliterated and normalized permutations for any document or template code.

    Handles novel corporate document codes (e.g., PIB-501, IT-42, SED-15, SEC-101, RKA-03, OD-184),
    keyboard layout homoglyph mismatches (e.g., mixed Cyrillic 'Р' in 'РIB-501'),
    and hyphen/spacing variations (e.g., 'PIB-501', 'PIB 501', 'PIB501', 'ПИБ-501', 'ПИБ501').
    """
    if not raw_code:
        return set()

    variants: Set[str] = set()
    clean = raw_code.strip().lower()
    variants.add(clean)
    variants.add(clean.replace("-", "").replace("_", "").replace(" ", ""))

    norm_lat, norm_cyr = normalize_code_homoglyphs(clean)
    variants.add(norm_lat)
    variants.add(norm_cyr)
    variants.add(norm_lat.replace("-", "").replace("_", "").replace(" ", ""))
    variants.add(norm_cyr.replace("-", "").replace("_", "").replace(" ", ""))

    m = re.match(r"^([a-zа-яё0-9_\-]+?)(?:[-_ ]*(\d+))?$", clean)
    if m:
        prefix = m.group(1).replace("-", "").replace("_", "")
        num = m.group(2) or ""

        norm_lat_pref = normalize_code_homoglyphs(prefix)[0]
        norm_cyr_pref = normalize_code_homoglyphs(prefix)[1]

        lat_from_orig = transliterate_cyr_to_lat(prefix)
        cyr_from_orig = transliterate_lat_to_cyr(prefix)
        lat_from_cyr_norm = transliterate_cyr_to_lat(norm_cyr_pref)
        cyr_from_lat_norm = transliterate_lat_to_cyr(norm_lat_pref)

        all_prefixes = {
            prefix,
            norm_lat_pref,
            norm_cyr_pref,
            lat_from_orig,
            cyr_from_orig,
            lat_from_cyr_norm,
            cyr_from_lat_norm,
        }

        for p in all_prefixes:
            p_clean = p.replace("-", "").replace("_", "").strip()
            if p_clean:
                if num:
                    variants.add(f"{p_clean}-{num}")
                    variants.add(f"{p_clean}{num}")
                    variants.add(f"{p_clean} {num}")
                else:
                    variants.add(p_clean)

    return {v for v in variants if v}


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
    for v_ending in ("иться", "аться", "еться", "уться", "ться", "ить", "ать", "еть", "уть", "ти", "ть"):
        if len(w) > len(v_ending) + 2 and w.endswith(v_ending):
            w = w[:-len(v_ending)]
            break
    if w.endswith(("ь", "ъ")):
        w = w[:-1]
    for ending in ("ами", "ями", "ов", "ев", "ей", "ам", "ям", "ом", "ем", "ой", "ей", "ую", "юю", "ая", "яя", "ое", "ее", "ые", "ие", "ых", "их", "ым", "им", "а", "я", "у", "ю", "о", "е", "ы", "и"):
        if len(w) > len(ending) + 2 and w.endswith(ending):
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

    best_idx = -1
    is_role_match = False

    # For composition / role queries, prioritize role and table markers in chunk content
    is_role_query = bool(re.search(
        r"\b(?:рол[иейя]|состав[ае]?|структур[аыеу]|член[ыова-я]*|участник[иова-я]*|кто\s+(?:входит|включен|является)|(?:входит|входят|включает|включаются)|председател[ьяе]|руководител[ьяе]|секретар[ьяе])\b",
        query,
        re.I,
    ))
    if is_role_query:
        role_marker_matches = [
            clean_content.lower().find(m)
            for m in (
                "роль в комитете",
                "установленный состав и роли",
                "состав комитета",
                "председатель комитета",
                "руководитель рабочей группы",
                "состав группы аудита",
                "роль | должность",
            )
            if clean_content.lower().find(m) != -1
        ]
        if role_marker_matches:
            best_idx = min(role_marker_matches)
            is_role_match = True

    if best_idx == -1:
        # Try to find match index of query keywords or detected terms
        search_tokens = []
        if detected_terms:
            for t in detected_terms:
                search_tokens.append(t.canonical)
                if len(t.expansion) < 40:
                    search_tokens.append(t.expansion)

        query_words = [w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", query) if len(w) >= 3]
        search_tokens.extend(query_words)
        for w in query_words:
            if len(w) >= 4 and not w[0].isdigit():
                stem = get_russian_stem(w)
                if stem not in search_tokens:
                    search_tokens.append(stem)

        for token in search_tokens:
            idx = clean_content.lower().find(token.lower())
            if idx != -1:
                best_idx = idx
                break

    if best_idx == -1:
        clean_lead = re.sub(r"_{3,}", "____", clean_content[:max_chars]).rstrip()
        return clean_lead + ("..." if len(clean_content) > max_chars else "")

    if is_role_match:
        start = best_idx
    elif best_idx < 100:
        start = 0
    else:
        start = max(0, best_idx - 100)

    end = min(len(clean_content), start + max_chars)
    excerpt = clean_content[start:end].strip()
    # Clean leading orphaned punctuation/commas
    excerpt = re.sub(r"^(?:[,\.;:—\-\s]+)", "", excerpt)
    # Collapse multiple underscores
    excerpt = re.sub(r"_{3,}", "____", excerpt)
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
        if cand_digits and clean_digits and ("правило" not in clean_clause or "правил" in query.lower()):
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

    # 2. Full-text search rank (ts_rank_cd) + query content word coverage (with deep/multi-part query support)
    all_stop_and_filler = RUSSIAN_STOPWORDS | CONVERSATIONAL_FILLER_WORDS
    all_query_words = [
        w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", query.lower())
        if len(w) >= 3 and w not in all_stop_and_filler
    ]
    if not all_query_words:
        all_query_words = [
            w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", query.lower())
            if len(w) >= 3 and w not in RUSSIAN_STOPWORDS
        ]
    if not all_query_words:
        all_query_words = [w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", query.lower()) if len(w) >= 3]
    content_lower = f"{doc_code} {chunk_clause} {chunk_content}".lower()
    matched_words = []
    for w in all_query_words:
        stems_to_try = [get_russian_stem(w)]
        if w in SLANG_SYNONYMS:
            stems_to_try.append(get_russian_stem(SLANG_SYNONYMS[w]))
        if any(re.search(rf"(?<![а-яА-ЯёЁa-zA-Z0-9]){re.escape(st)}", content_lower) for st in stems_to_try):
            matched_words.append(w)
    raw_coverage = len(matched_words) / len(all_query_words) if all_query_words else 0.0

    # For deep/multi-aspect queries (2+ sentences or 6+ domain words), prevent coverage dilution
    # across sub-questions while strictly requiring >= 2 matched domain stems to block out-of-domain noise
    best_sub_coverage = raw_coverage
    if len(matched_words) >= 2:
        if len(matched_words) >= 3:
            effective_denom = min(len(all_query_words), 6)
            best_sub_coverage = max(best_sub_coverage, min(1.0, len(matched_words) / effective_denom))
        elif len(all_query_words) >= 6:
            effective_denom = min(len(all_query_words), 6)
            best_sub_coverage = max(best_sub_coverage, min(1.0, len(matched_words) / effective_denom))

        sub_parts = re.split(r"[?.!;]+|\b(?:а если|а также|и как|и какие|и кому)\b", query.lower())
        if len(sub_parts) >= 2:
            for part in sub_parts:
                part_words = [
                    w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", part)
                    if len(w) >= 3 and w not in all_stop_and_filler
                ]
                if len(part_words) >= 2:
                    part_matched = [
                        w
                        for w in part_words
                        if re.search(rf"(?<![а-яА-ЯёЁa-zA-Z0-9]){re.escape(get_russian_stem(w))}", content_lower)
                    ]
                    if len(part_matched) >= 3 or (len(part_matched) == 2 and len(part_words) <= 4):
                        best_sub_coverage = max(best_sub_coverage, len(part_matched) / len(part_words))

    coverage = best_sub_coverage

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

    # 7. Document code or template registration number match (e.g., OD-184, УТВ-01, MOD-ORDER-IS, PIB-501, IT-42, SEC-101)
    is_code_match = False
    if doc_code:
        doc_variants = generate_code_variants(doc_code)
        query_code_variants: Set[str] = set()
        for cm in re.finditer(r"\b([a-zA-Zа-яА-ЯёЁ]{1,10})[-_ ]*(\d+)\b", query):
            query_code_variants.update(generate_code_variants(cm.group(0)))

        q_norm_lat, q_norm_cyr = normalize_code_homoglyphs(query_clean)

        if (
            query_clean in doc_variants
            or bool(doc_variants & query_code_variants)
            or any(
                re.search(rf"\b{re.escape(v)}\b", query_clean)
                or re.search(rf"\b{re.escape(v)}\b", q_norm_lat)
                or re.search(rf"\b{re.escape(v)}\b", q_norm_cyr)
                for v in doc_variants
            )
            or any(
                re.search(rf"\b{re.escape(v.replace('-', ''))}\b", query_clean.replace("-", ""))
                for v in doc_variants
            )
        ):
            is_code_match = True
            score += 65.0 if query_clean in doc_variants else 50.0

    if chunk_reg_number and chunk_reg_number.lower() == query_clean:
        score += 65.0
    elif chunk_reg_number and chunk_reg_number.lower() in query_clean:
        score += 35.0

    # 8. Calibration: prevent artificial saturation to 100% on partial matches
    is_fully_grounded = (
        is_exact_clause
        or (doc_code and doc_code.lower() == query_clean)
        or is_code_match
        or (chunk_reg_number and chunk_reg_number.lower() == query_clean)
        or (coverage >= 0.95 and has_multi_match and (ts_rank_exact > 0.05 or bm25_norm > 0.4))
    )

    if not is_fully_grounded:
        if score > 75.0:
            score = 75.0
        elif score >= 35.0 and has_multi_match and coverage >= 0.4:
            score = 45.0 + ((score - 35.0) / 40.0) * 30.0

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
        if len(trigger_phrase) <= 3:
            if re.search(rf"\b{re.escape(trigger_phrase)}\b", q_low):
                expanded_query = f"{expanded_query} {expansion_str}"
        else:
            if re.search(rf"\b{re.escape(trigger_phrase)}", q_low):
                expanded_query = f"{expanded_query} {expansion_str}"

    for slang, standard in SLANG_SYNONYMS.items():
        if re.search(rf"\b{re.escape(slang)}\b", q_low):
            expanded_query = f"{expanded_query} {standard}"

    query_code_candidates: Set[str] = set()
    # Expand novel document code variants generically (Cyrillic <-> Latin, homoglyphs, with/without hyphen)
    for cm in re.finditer(r"\b([a-zA-Zа-яА-ЯёЁ]{1,10})[-_ ]*(\d+)\b", clean_query):
        code_token = cm.group(0)
        variants = generate_code_variants(code_token)
        for var in variants:
            if var not in expanded_query.lower():
                expanded_query = f"{expanded_query} {var}"
            query_code_candidates.add(var.lower())
            query_code_candidates.add(var.lower().replace("-", "").replace("_", "").replace(" ", ""))

    clause_candidates = extract_clause_identifiers(expanded_query)
    allowed_levels = get_allowed_access_levels(user_role)
    if detected_terms is None:
        detected_terms = await detect_query_terms(session, clean_query)

    # Also expand query with detected glossary term expansions
    for dt in detected_terms:
        if dt.expansion and dt.expansion.lower() not in expanded_query.lower():
            expanded_query = f"{expanded_query} {dt.expansion}"

    # Construct broad OR query for websearch_to_tsquery (filtering stopwords & conversational fillers)
    all_stop_and_filler = RUSSIAN_STOPWORDS | CONVERSATIONAL_FILLER_WORDS
    significant_words = [
        w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", expanded_query)
        if len(w) >= 2 and w.lower() not in all_stop_and_filler
    ]
    if not significant_words:
        significant_words = [
            w for w in re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", clean_query)
            if len(w) >= 2 and w.lower() not in RUSSIAN_STOPWORDS
        ]
    or_query = " OR ".join(significant_words) if significant_words else clean_query

    # Clause and code match candidate lists for SQL ANY parameters
    clause_param = clause_candidates if clause_candidates else ["__NO_CLAUSE__"]
    code_param = list(query_code_candidates) if query_code_candidates else ["__NO_CODE__"]

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
              OR lower(d.doc_code) = ANY(:code_candidates)
              OR lower(replace(d.doc_code, '-', '')) = ANY(:code_candidates)
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
            (CASE WHEN lower(d.doc_code) = ANY(:code_candidates) THEN 80.0 ELSE 0.0 END) DESC,
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
            "code_candidates": code_param,
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
    scored_candidates: List[Tuple[Tuple[float, int, float, float], SourceRef]] = []

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
        is_exact_cand = 1 if (row.clause and row.clause in clause_candidates) else 0
        sort_key = (
            relevance_pct,
            is_exact_cand,
            float(rrf_val),
            float(bm25_norms[idx]),
        )
        scored_candidates.append((sort_key, source_ref))

    # Sort descending by calculated relevance_pct, then exact clause match, RRF, and BM25
    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    candidates = [item[1] for item in scored_candidates]
    return candidates[:top_k]
