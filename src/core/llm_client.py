"""Local LLM client for Ollama with grounded prompting and offline fallback.

Connects asynchronously to local Ollama instance (qwen2.5:1.5b with fallback to qwen2.5:3b)
via OpenAI-compatible /v1/chat/completions endpoint.
Provides deterministic offline fallback if the server is unreachable.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from src.config import settings
from src.schemas.api_models import DetectedTermRef, SourceRef

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Вы — официальный интеллектуальный ассистент по нормативным документам документационного обеспечения управления (ДОУ).
Ваша задача — сформировать точный, строгий и аргументированный ответ на вопрос пользователя ИСКЛЮЧИТЕЛЬНО на основе приведенных фрагментов нормативных документов.

ОБЯЗАТЕЛЬНЫЕ ТРЕБОВАНИЯ:
1. Опирайтесь ИСКЛЮЧИТЕЛЬНО на предоставленный нормативный контекст. Категорически запрещено добавлять внешние данные, домыслы или нерегламентированные сведения.
2. В ответе ОБЯЗАТЕЛЬНО явно приводите ссылки на первоисточник: название документа, его шифр/код, главу/раздел, пункт (например, п. 4.1.3 или п. 10.6) и номер страницы.
3. Если приведены термины и сокращения, используйте их официальные формулировки и расшифровки.
4. Излагайте ответ четко, структурированно, профессиональным деловым языком."""


def build_offline_fallback_answer(
    query: str,
    sources: List[SourceRef],
    detected_terms: Optional[List[DetectedTermRef]] = None,
) -> str:
    """Deterministic offline fallback synthesizing grounded answer directly from sources."""
    if not sources:
        return (
            "В действующей редакции нормативных документов ДОУ Организации "
            "данный вопрос не регламентирован. Рекомендуется обратиться в "
            "Департамент ДОУ Организации."
        )

    lines = ["На основании действующих нормативных документов ДОУ Организации:"]

    if detected_terms:
        terms_desc = "; ".join(f"{t.canonical} — {t.expansion}" for t in detected_terms)
        lines.append(f"Используемые термины и сокращения: {terms_desc}.")

    for idx, s in enumerate(sources[:3], 1):
        clause_str = f"п. {s.clause}" if s.clause else "раздел регламента"
        lines.append(
            f"{idx}. В соответствии с документом «{s.document_title}» "
            f"({s.document_code}, {s.chapter}, {clause_str}, стр. {s.page_number}):\n"
            f"«{s.quote.strip()}»"
        )

    return "\n\n".join(lines)


class OllamaClient:
    """Asynchronous client for local Ollama LLM with failover and offline fallback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
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

    async def is_healthy(self) -> bool:
        """Check if local Ollama server is online and reachable."""
        try:
            # Check native /api/tags or OpenAI /models
            host_root = self.base_url.replace("/v1", "")
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
    ) -> str:
        """Assemble structured prompt with citation context blocks."""
        context_parts = []
        for idx, s in enumerate(sources[:4], 1):
            clause_str = f"п. {s.clause}" if s.clause else "раздел"
            context_parts.append(
                f"[{idx}] Документ: «{s.document_title}» ({s.document_code}, версия {s.version}, гриф {s.access_level})\n"
                f"Раздел/Глава: {s.chapter}\n"
                f"Пункт: {clause_str}\n"
                f"Страница: {s.page_number}\n"
                f"Текст:\n{s.quote.strip()}"
            )

        context_text = "\n\n---\n\n".join(context_parts)

        terms_text = ""
        if detected_terms:
            t_lines = [f"• {t.canonical}: {t.expansion}" for t in detected_terms]
            terms_text = f"\n\nГЛОССАРИЙ ПРИМЕНИМЫХ ТЕРМИНОВ:\n" + "\n".join(t_lines)

        user_content = (
            f"НОРМАТИВНЫЙ КОНТЕКСТ:\n"
            f"{context_text}"
            f"{terms_text}\n\n"
            f"ВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{query.strip()}\n\n"
            f"Дайте исчерпывающий и строго регламентированный ответ со ссылками на пункты и страницы."
        )
        return user_content

    async def _call_completion(self, model_name: str, messages: List[Dict[str, str]]) -> str:
        """Send chat completion request to Ollama endpoint."""
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 600,
        }

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            return answer.strip()

    async def generate_answer(
        self,
        query: str,
        sources: List[SourceRef],
        detected_terms: Optional[List[DetectedTermRef]] = None,
        allow_fallback: bool = True,
    ) -> str:
        """Generate grounded answer using Ollama with automatic model fallback and offline synthesis."""
        if not sources:
            return (
                "В действующей редакции нормативных документов ДОУ Организации "
                "данный вопрос не регламентирован. Рекомендуется обратиться в "
                "Департамент ДОУ Организации."
            )

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
            logger.warning(f"Ollama primary model '{self.model}' HTTP error: {h_err.response.status_code}")
            # If model not found (404), try fallback model
            if h_err.response.status_code == 404 and self.fallback_model and self.fallback_model != self.model:
                try:
                    logger.info(f"Retrying with fallback model: {self.fallback_model}")
                    return await self._call_completion(self.fallback_model, messages)
                except Exception as fb_err:
                    logger.warning(f"Ollama fallback model failed: {fb_err}")
            if not allow_fallback:
                raise
        except Exception as e:
            logger.warning(f"Ollama unreachable or error: {e}")
            if not allow_fallback:
                raise

        # 2. Deterministic offline fallback
        logger.info("Using deterministic offline fallback generation.")
        return build_offline_fallback_answer(query, sources, detected_terms)
