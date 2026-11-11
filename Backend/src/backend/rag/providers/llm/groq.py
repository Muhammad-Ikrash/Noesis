import logging

import openai

from backend.rag.interfaces import ChatMessage, LLMResult, ProviderError

logger = logging.getLogger(__name__)


class GroqLLMProvider:
    """Groq through its OpenAI-compatible endpoint."""

    def __init__(self, *, api_key: str, model: str, base_url: str, temperature: float, timeout: float) -> None:
        self.model = model
        self._temperature = temperature
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=2)

    def complete(self, messages: list[ChatMessage], *, json_mode: bool = False) -> LLMResult:
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=self._temperature,
                **kwargs,
            )
        except openai.RateLimitError as exc:
            raise ProviderError("The LLM provider rate limit was reached. Try again shortly.") from exc
        except openai.APIError as exc:
            logger.warning("Groq request failed: %s", type(exc).__name__)
            raise ProviderError("The LLM provider request failed.") from exc

        usage = response.usage.model_dump() if response.usage else {}
        return LLMResult(text=response.choices[0].message.content or "", model=response.model, usage=usage)
