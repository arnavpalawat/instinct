"""Unified LLM client using Groq with retry backoff."""

import os
import time
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """Groq LLM client with automatic retry and exponential backoff."""

    BACKOFF_DELAYS = [15, 60, 120]

    def __init__(self, config: dict):
        self.model = config.get("model", "openai/gpt-oss-120b")
        self.temperature = config.get("temperature", 0.3)
        self.max_tokens = config.get("max_tokens_per_section", 1500)
        self.max_retries = config.get("max_retries", 3)
        self._init_client()

    def _init_client(self):
        """Initialize the Groq API client."""
        self.groq_client = None

        if os.environ.get("GROQ_API_KEY"):
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
                logger.info("Groq client initialized")
            except ImportError:
                logger.warning("groq package not installed; Groq provider unavailable")

    def generate(
        self, prompt: str, system: str = "", max_tokens: int | None = None
    ) -> str:
        """Generate text with retry and exponential backoff.

        Retries up to max_retries times on rate-limit errors with
        increasing delays (15s, 60s, 120s).
        Returns an empty string if all attempts fail.
        """
        tokens = max_tokens or self.max_tokens
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                result = self._generate_groq(prompt, system, tokens)
                if result:
                    return result
            except Exception as exc:
                last_error = exc
                if self._is_rate_limit(exc) and attempt < self.max_retries - 1:
                    delay = self.BACKOFF_DELAYS[min(attempt, len(self.BACKOFF_DELAYS) - 1)]
                    logger.warning(
                        "Rate limit hit (attempt %d/%d), waiting %ds before retry",
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "Groq failed (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries,
                        exc,
                    )
                    if not self._is_rate_limit(exc):
                        break

        if last_error:
            logger.error("All LLM attempts failed. Last error: %s", last_error)
        return ""

    def _generate_groq(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
    ) -> str:
        """Generate text using the Groq API (Llama, Mixtral, etc.)."""
        if not self.groq_client:
            raise RuntimeError("Groq client not initialized (missing API key or package)")

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.groq_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        text = choice.message.content or ""
        logger.debug(
            "Groq response: %d chars, finish_reason=%s",
            len(text),
            choice.finish_reason,
        )
        return text.strip()

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        """Detect rate-limit errors."""
        exc_str = str(exc).lower()
        if "rate_limit" in exc_str or "rate limit" in exc_str or "429" in exc_str:
            return True
        exc_type = type(exc).__name__
        if exc_type in ("RateLimitError", "APIStatusError"):
            return True
        return False
