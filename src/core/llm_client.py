"""Local LLM client for Ollama with grounded prompting and offline fallback.

Connects asynchronously to local Ollama instance (qwen2.5:1.5b with fallback to qwen2.5:3b)
via OpenAI-compatible /v1/chat/completions endpoint.
Provides deterministic offline fallback if the server is unreachable.
"""

import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from src.config import settings
from src.schemas.api_models import DetectedTermRef, SourceRef

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Вы — интеллектуальный экспресс-ассистент по нормативным документам документационного обеспечения управления (ДОУ) Организации.
Ваша цель — давать предельно краткие, человечные, структурированные и точные ответы строго по приведенному нормативному контексту, без "воды", канцеляризмов и длинных цитат.

СТРУКТУРА ОТВЕТА:
1. Прямой ответ на вопрос пользователя простым деловым языком в 1–2 предложениях.
   - Если вопрос в формате «Можно ли...?» или «Разрешено ли...?» — четко начните: «Да, разрешено...» (если есть условия — перечислите их) либо «Нет, регламент запрещает...».
   - Если вопрос о ролях, составе или структуре коллегиального органа (комитета, рабочей группы, комиссии) — прямо и структурированно перечислите установленные роли (например: Председатель, Заместитель председателя, Секретарь, Члены), не оставляя шаблонных прочерков и пустых граф.
2. Ключевые требования / условия: до 3 коротких тезисов-буллетов (только самое главное).
3. Точная ссылка на пункт регламента в скобках в самом конце ответа (например: «(п. 2.1.4 ОД-184)» или «(п. 3.2, п. 5.1 ОД-184)»).

ПРАВИЛА:
- Категорически запрещено пересказывать всю главу, копировать большие полотна текста или писать вводные фразы («На основании предоставленного контекста...», «В ответ на ваш запрос...»).
- Ссылайтесь ТОЛЬКО на номера пунктов, указанные в контексте. Не придумывайте пункты от себя.
- Ответ должен быть исчерпывающим, но предельно лаконичным (до 150-200 слов)."""


def clean_template_artifacts(text: str) -> str:
    """Clean template underscores, bracket placeholders, and footnote markers."""
    cleaned = re.sub(r"\[\d+\]", "", text)
    cleaned = re.sub(r"_{2,}", "", cleaned)
    cleaned = re.sub(r"\[(?:Указать|Отменить)[^\]]*\]", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*,\s*(?:,\s*)+", ", ", cleaned)
    cleaned = re.sub(r"^\s*,\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_roles_from_sources(sources: List[SourceRef], query: str) -> List[str]:
    """Extract explicit roles/composition from retrieved sources (templates or OD-184)."""
    roles: List[str] = []
    seen = set()
    q_low = query.lower()

    for s in sources:
        text = f"{s.quote or ''} {s.full_content or ''}"

        # Check for project committee roles
        if "MOD-DISP-PROJECT" in s.document_code or ("проектн" in q_low and any(k in q_low for k in ("комитет", "состав", "рол", "кто", "входит"))):
            proj_roles = [
                "Председатель Комитета",
                "Заместитель председателя Комитета",
                "Секретарь Комитета",
                "Члены Комитета",
            ]
            for r in proj_roles:
                if r not in seen:
                    roles.append(r)
                    seen.add(r)
            if roles:
                return roles

        # Check for workgroup roles
        if "MOD-DISP-WORKGROUP" in s.document_code or ("рабоч" in q_low and any(k in q_low for k in ("групп", "состав", "рол", "кто", "входит"))):
            wg_roles = [
                "Руководитель рабочей группы",
                "Заместитель руководителя рабочей группы",
                "Секретарь рабочей группы",
                "Члены рабочей группы",
            ]
            for r in wg_roles:
                if r not in seen:
                    roles.append(r)
                    seen.add(r)
            if roles:
                return roles

        # Check for audit team roles
        if "MOD-DISP-AUDIT" in s.document_code or ("аудит" in q_low and any(k in q_low for k in ("групп", "состав", "команд", "кто", "входит"))):
            audit_roles = [
                "Руководитель группы аудита",
                "Члены группы аудита (аудиторы)",
            ]
            for r in audit_roles:
                if r not in seen:
                    roles.append(r)
                    seen.add(r)
            if roles:
                return roles

        # Check for structured summary line: "Установленный состав и роли: ..."
        m_schema = re.search(r"Установленный состав и роли:\s*([^.\n]+)", text)
        if m_schema:
            for item in m_schema.group(1).split(","):
                item_clean = item.strip()
                if item_clean and item_clean not in seen:
                    roles.append(item_clean)
                    seen.add(item_clean)
            if roles:
                return roles

        # Table rows matching: "Роль | ...", "Роль в комиссии | ...", "Должность | ...", etc.
        in_role_table = False
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if re.match(r"^(?:роль|должность|состав|наименование\s+роли)(?:\s+(?:в|для)\s+[а-яА-ЯёЁa-zA-Z0-9_\-]+)?\s*\|", line, re.I):
                in_role_table = True
                continue
            if in_role_table and "|" in line:
                parts = line.split("|")
                r_name = parts[0].strip()
                if re.match(r"^[-—_]+$", r_name) or "подразделение" in r_name.lower():
                    continue
                if r_name and len(r_name) < 60 and r_name not in seen:
                    roles.append(r_name)
                    seen.add(r_name)
            elif in_role_table and not ("|" in line):
                in_role_table = False

    return roles


def build_offline_fallback_answer(
    query: str,
    sources: List[SourceRef],
    detected_terms: Optional[List[DetectedTermRef]] = None,
) -> str:
    """Deterministic offline fallback synthesizing concise grounded answer directly from sources."""
    if not sources:
        return (
            "В действующей редакции нормативных документов ДОУ Организации "
            "данный вопрос не регламентирован. Рекомендуется обратиться в "
            "Департамент ДОУ Организации."
        )

    lines: List[str] = []

    # 1. Check if the query asks about composition / roles of a committee, group, or body
    is_roles_query = bool(re.search(
        r"\b(?:рол[иейя]|состав[ае]?|структур[аыеу]|член[ыова-я]*|участник[иова-я]*|кто\s+(?:входит|включен|является)|(?:входит|входят|включает|включаются)(?:\s+в(?:\s+состав)?)?|председател[ьяе]|руководител[ьяе]|секретар[ьяе])\b",
        query,
        re.I,
    ))
    extracted_roles = extract_roles_from_sources(sources, query) if is_roles_query else []

    primary = sources[0]
    # If user explicitly asks about modular document and a template is in sources, prefer template as primary
    if "модульн" in query.lower():
        tmpl = next((s for s in sources if s.document_code.startswith("MOD-")), None)
        if tmpl:
            primary = tmpl

    p_clause = ""
    if primary.clause and primary.clause != primary.document_code and not primary.clause.startswith("MOD-"):
        p_clause = f", п. {primary.clause}"
    doc_header = f"«{primary.document_title}» ({primary.document_code}{p_clause}, стр. {primary.page_number})"

    lines.append(f"В соответствии с документом {doc_header}:")

    if extracted_roles:
        target_entity = "коллегиального органа"
        if "проектн" in query.lower():
            target_entity = "проектного комитета"
        elif "рабоч" in query.lower():
            target_entity = "рабочей группы"
        elif "аудит" in query.lower():
            target_entity = "группы внутреннего аудита"
        elif "комитет" in query.lower():
            target_entity = "комитета"
        elif "комисси" in query.lower():
            target_entity = "комиссии"

        lines.append(f"В состав {target_entity} входят следующие роли:")
        for r in extracted_roles:
            lines.append(f"• {r};")
    else:
        raw_quote = (primary.quote or primary.full_content or "").strip()
        cleaned_quote = clean_template_artifacts(raw_quote)
        cleaned_quote = re.sub(r"^(?:\.\.\.|…|\s*,)+\s*", "", cleaned_quote)
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned_quote) if len(s.strip()) > 10]
        lead_text = " ".join(sentences[:2]) if sentences else cleaned_quote
        if len(lead_text) > 280:
            lead_text = lead_text[:275].rstrip() + "..."
        if lead_text:
            lines.append(lead_text)

    # 2. Key requirements / bullets (up to 3 short bullets)
    bullets: List[str] = []
    if is_roles_query and extracted_roles:
        if primary.document_code.startswith("MOD-"):
            tmpl_source = next((s for s in sources if s.document_code.startswith("MOD-")), primary)
            t_clause = f", п. {tmpl_source.clause}" if (tmpl_source.clause and tmpl_source.clause != tmpl_source.document_code and not tmpl_source.clause.startswith("MOD-")) else ""
            bullets.append(
                f"• По каждой роли в распоряжении указывается должность, структурное подразделение, инициалы и фамилия ({tmpl_source.document_code}{t_clause})"
            )
            od_source = next((s for s in sources if s.document_code == "OD-184"), None)
            if od_source and od_source.clause:
                bullets.append(
                    f"• Распорядительный документ о создании определяет цель, статус, персональный или должностной состав, председателя, секретаря и полномочия ({od_source.document_code}, п. {od_source.clause})"
                )
        else:
            p_clause = f", п. {primary.clause}" if (primary.clause and primary.clause != primary.document_code) else ""
            bullets.append(
                f"• Установленный состав и роли: {', '.join(extracted_roles)} ({primary.document_code}{p_clause})"
            )
    else:
        for s in sources[:3]:
            s_clause = f", п. {s.clause}" if (s.clause and s.clause != s.document_code and not s.clause.startswith("MOD-")) else ""
            s_text = clean_template_artifacts((s.quote or s.full_content or "").strip())
            s_sentences = [st.strip() for st in re.split(r"(?<=[.!?])\s+", s_text) if len(st.strip()) > 15]
            if s_sentences:
                bullet_candidate = s_sentences[0]
                bullet_candidate = re.sub(r"^(?:\.\.\.|…|\s*,)+\s*", "", bullet_candidate)
                if len(bullet_candidate) > 160:
                    bullet_candidate = bullet_candidate[:155].rstrip() + "..."
                bullets.append(f"• {bullet_candidate} ({s.document_code}{s_clause})")

    if bullets and len(bullets) > 1:
        lines.append("Ключевые требования:")
        lines.extend(bullets[:3])
    elif bullets and is_roles_query:
        lines.append("Ключевые требования:")
        lines.extend(bullets)

    # 3. Mention corporate terms if detected
    if detected_terms:
        terms_desc = "; ".join(f"{t.canonical} — {t.expansion}" for t in detected_terms)
        lines.append(f"Термины: {terms_desc}.")

    # 4. Regulatory clause citation
    ref_items = []
    relevant_sources = sources[:3]
    if primary.document_code.startswith("MOD-"):
        if is_roles_query and ("проектн" in query.lower() or "MOD-DISP-PROJECT" in primary.document_code):
            relevant_sources = [s for s in sources[:3] if s.document_code in ("MOD-DISP-PROJECT", "OD-184")] or sources[:2]
        elif is_roles_query and ("рабоч" in query.lower() or "MOD-DISP-WORKGROUP" in primary.document_code):
            relevant_sources = [s for s in sources[:3] if s.document_code in ("MOD-DISP-WORKGROUP", "OD-184")] or sources[:2]

    for s in relevant_sources:
        clause_part = f", п. {s.clause}" if (s.clause and s.clause != s.document_code and not s.clause.startswith("MOD-")) else ""
        item = f"{s.document_code}{clause_part}, стр. {s.page_number}"
        if item not in ref_items:
            ref_items.append(item)
    lines.append(f"Основание: {'; '.join(ref_items)}.")

    return "\n\n".join(lines)


class OllamaClient:
    """Asynchronous client for local Ollama LLM with failover, SSE streaming, and offline fallback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: float = 0.35,
    ):
        raw_url = base_url or settings.OLLAMA_BASE_URL
        # Normalize localhost to 127.0.0.1 to avoid IPv6 resolution latency on Windows
        if "localhost" in raw_url:
            raw_url = raw_url.replace("localhost", "127.0.0.1")
        self.base_url = raw_url.rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.fallback_model = fallback_model or settings.OLLAMA_FALLBACK_MODEL
        self.temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        self.timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS
        self.max_tokens = max_tokens if max_tokens is not None else settings.LLM_NUM_PREDICT
        self.frequency_penalty = frequency_penalty

    async def is_healthy(self) -> bool:
        """Check if local Ollama server is online and reachable."""
        try:
            host_root = self.base_url.removesuffix("/v1")
            async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
                resp = await client.get(f"{host_root}/api/tags")
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama healthcheck failed: {e}")
            return False

    def build_user_prompt(
        self,
        query: str,
        sources: List[SourceRef],
        detected_terms: Optional[List[DetectedTermRef]] = None,
        approval_summary: Optional[str] = None,
    ) -> str:
        """Assemble structured prompt with full normative clauses (no 400-char truncation)."""
        context_parts = []
        for idx, s in enumerate(sources[:3], 1):
            clause_str = f"п. {s.clause}" if s.clause else "раздел"
            full_text = (s.full_content or s.quote).strip()
            if len(full_text) > 2200:
                full_text = full_text[:2200].rstrip() + "..."
            context_parts.append(
                f"[{idx}] Документ: «{s.document_title}» (шифр: {s.document_code}, версия {s.version}, гриф {s.access_level})\n"
                f"Глава/Раздел: {s.chapter} | Пункт: {clause_str} | Страница: стр. {s.page_number}\n"
                f"Полный текст нормы:\n{full_text}"
            )

        context_text = "\n\n---\n\n".join(context_parts)

        terms_text = ""
        if detected_terms:
            t_lines = [
                f"• {t.canonical} — {t.expansion}"
                + (f" ({t.definition})" if t.definition else "")
                for t in detected_terms
            ]
            terms_text = "\n\nГЛОССАРИЙ ТЕРМИНОВ:\n" + "\n".join(t_lines)

        approval_text = ""
        if approval_summary:
            approval_text = f"\n\nРАСЧЕТ МАРШРУТА СОГЛАСОВАНИЯ ПО МАТРИЦЕ ВИЗИРОВАНИЯ:\n{approval_summary}"

        role_hint = ""
        if re.search(r"\b(?:рол[иейя]|состав|структур|член|руководител|председател)\b", query, re.I):
            role_hint = (
                "\nВАЖНО: Вопрос касается состава/ролей органов. Обязательно перечислите конкретные роли "
                "(Председатель, Заместитель председателя, Секретарь, Члены и т.д.) строго по контексту. "
                "Категорически запрещено выводить шаблонные прочерки «____»."
            )

        user_content = (
            f"НОРМАТИВНЫЙ КОНТЕКСТ:\n"
            f"{context_text}"
            f"{terms_text}"
            f"{approval_text}\n\n"
            f"ВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{query.strip()}\n\n"
            f"Сформулируйте точный, предельно лаконичный ответ по приведенному тексту (1-2 предложения прямого ответа + до 3 коротких буллетов + пункт регламента в скобках в конце).{role_hint}"
        )
        return user_content

    async def _call_completion(self, model_name: str, messages: List[Dict[str, str]]) -> str:
        """Send chat completion request to Ollama endpoint tuned for 2 vCPU / 4 GB RAM."""
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "keep_alive": settings.LLM_KEEP_ALIVE,
            "options": {
                "num_ctx": settings.LLM_NUM_CTX,
                "num_thread": settings.LLM_NUM_THREAD,
                "num_predict": self.max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            return answer.strip()

    async def generate_answer_stream(
        self,
        query: str,
        sources: List[SourceRef],
        detected_terms: Optional[List[DetectedTermRef]] = None,
        approval_summary: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream answer tokens via SSE from local Ollama with deterministic fallback."""
        if not sources:
            yield (
                "В действующей редакции нормативных документов ДОУ Организации "
                "данный вопрос не регламентирован. Рекомендуется обратиться в "
                "Департамент ДОУ Организации."
            )
            return

        user_prompt = self.build_user_prompt(query, sources, detected_terms, approval_summary=approval_summary)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "stream": True,
            "keep_alive": settings.LLM_KEEP_ALIVE,
            "options": {
                "num_ctx": settings.LLM_NUM_CTX,
                "num_thread": settings.LLM_NUM_THREAD,
                "num_predict": self.max_tokens,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                async with client.stream("POST", endpoint, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_obj = json.loads(data_str)
                            delta = chunk_obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue
            return
        except Exception as e:
            logger.warning("Streaming from Ollama failed (%s), yielding fallback answer.", e)
            yield build_offline_fallback_answer(query, sources, detected_terms)

    async def generate_answer(
        self,
        query: str,
        sources: List[SourceRef],
        detected_terms: Optional[List[DetectedTermRef]] = None,
        allow_fallback: bool = True,
        approval_summary: Optional[str] = None,
    ) -> str:
        """Generate grounded answer using Ollama with automatic model fallback and offline synthesis."""
        if not sources:
            return (
                "В действующей редакции нормативных документов ДОУ Организации "
                "данный вопрос не регламентирован. Рекомендуется обратиться в "
                "Департамент ДОУ Организации."
            )

        try:
            user_prompt = self.build_user_prompt(
                query, sources, detected_terms, approval_summary=approval_summary
            )
        except TypeError:
            user_prompt = self.build_user_prompt(query, sources, detected_terms)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # 1. Try primary model
        try:
            logger.info(f"Invoking Ollama primary model: {self.model}")
            return await self._call_completion(self.model, messages)
        except httpx.HTTPStatusError as h_err:
            logger.warning(
                f"Ollama primary model '{self.model}' HTTP error {h_err.response.status_code}: {h_err.response.text}"
            )
            # If model error (404 or 500), try fallback model
            if h_err.response.status_code in (404, 500) and self.fallback_model and self.fallback_model != self.model:
                try:
                    logger.info(f"Retrying with fallback model: {self.fallback_model}")
                    return await self._call_completion(self.fallback_model, messages)
                except Exception as fb_err:
                    logger.warning(f"Ollama fallback model failed ({type(fb_err).__name__}): {fb_err}")
            if not allow_fallback:
                raise
        except Exception as e:
            err_msg = str(e) or f"{type(e).__name__} (timeout or connection failed)"
            logger.warning(f"Ollama unreachable or error: {err_msg}")
            if not allow_fallback:
                raise

        # 2. Deterministic offline fallback
        logger.info("Using deterministic offline fallback generation.")
        return build_offline_fallback_answer(query, sources, detected_terms)
