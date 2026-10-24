"""Local LLM client for Ollama with grounded prompting and offline fallback.

Connects asynchronously to local Ollama instance (qwen2.5:1.5b with fallback to qwen2.5:3b)
via OpenAI-compatible /v1/chat/completions endpoint.
Provides deterministic offline fallback if the server is unreachable.
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from src.config import settings
from src.schemas.api_models import DetectedTermRef, SourceRef

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Вы — официальный интеллектуальный ассистент по нормативным документам документационного обеспечения управления (ДОУ) Организации.
Ваша задача — дать точный, строгий и аргументированный ответ на вопрос пользователя ИСКЛЮЧИТЕЛЬНО на основе приведенных фрагментов нормативных документов.

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА:
1. Используйте ТОЛЬКО факты, сроки, условия и формулировки из раздела «НОРМАТИВНЫЙ КОНТЕКСТ». Категорически запрещено додумывать сведения или искажать смысл норм (например, путать сквозную и самостоятельную нумерацию или менять запрет «не ставится» на разрешение).
2. Цитируйте ТОЛЬКО те номера пунктов, глав и страниц, которые прямо указаны в заголовках блоков [1], [2], [3] предоставленного контекста. Никогда не придумывайте номера пунктов от себя.
3. Если в контексте указан обязательный маршрут согласования из Матрицы визирования, перечислите все согласующие подразделения и подписанта строго по этому маршруту.
4. Отвечайте кратко, четко, по существу вопроса, в официально-деловом стиле, без повторов и тавтологий."""


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
        body_txt = (s.full_content or s.quote).strip()
        lines.append(
            f"{idx}. В соответствии с документом «{s.document_title}» "
            f"({s.document_code}, {s.chapter}, {clause_str}, стр. {s.page_number}):\n"
            f"«{body_txt}»"
        )

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
        max_tokens: int = 420,
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
        self.max_tokens = max_tokens
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

        user_content = (
            f"НОРМАТИВНЫЙ КОНТЕКСТ:\n"
            f"{context_text}"
            f"{terms_text}"
            f"{approval_text}\n\n"
            f"ВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{query.strip()}\n\n"
            f"Сформулируйте точный ответ строго по приведенному тексту с указанием шифра документа, пункта и номера страницы."
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
