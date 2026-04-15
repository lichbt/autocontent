"""Centralized LLM client with retry, backoff, and provider fallback."""

from __future__ import annotations

import time
from typing import Optional

import requests

from core.config import CONFIG
from core.logging import get_logger

logger = get_logger("core.llm")


def generate(
    prompt: str,
    system: str = "You are an expert SEO copywriter.",
    temperature: float = 0.4,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """
    Generate text using configured providers in priority order.
    Falls back to next provider on failure.
    """
    for provider_name in CONFIG.provider_priority:
        cfg = CONFIG.get_provider(provider_name)
        if not cfg or not cfg.enabled or not cfg.api_key:
            logger.debug(f"Skipping disabled/missing provider: {provider_name}")
            continue

        # Set default base URLs for known providers
        if not cfg.base_url:
            if provider_name in ("router", "9router"):
                base_url = "http://localhost:20128/v1"
            elif provider_name == "deepseek":
                base_url = "https://api.deepseek.com/v1"
            elif provider_name == "openai":
                base_url = "https://api.openai.com/v1"
            elif provider_name == "anthropic":
                base_url = "https://api.anthropic.com"
            elif provider_name == "gemini":
                base_url = "https://generativelanguage.googleapis.com/v1beta"
            else:
                logger.warning(f"No base_url configured for {provider_name}, skipping.")
                continue
        else:
            base_url = cfg.base_url.rstrip("/")
        model = cfg.model

        for attempt in range(3):
            try:
                payload: dict = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "stream": False,  # Always use non-streaming for reliability
                }
                # Limit tokens for SEO drafts to avoid long generation
                if max_tokens:
                    payload["max_tokens"] = max_tokens
                elif provider_name in ("router", "9router"):
                    payload["max_tokens"] = 500  # Cap local router generation

                logger.debug(
                    f"LLM request: provider={provider_name}, model={model}, attempt={attempt + 1}"
                )

                # Use longer timeout for local, shorter for remote
                timeout = 30 if "localhost" in base_url else cfg.timeout_seconds

                response = requests.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {cfg.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout,
                )

                if response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(
                        f"Rate limited by {provider_name}, backing off {wait}s"
                    )
                    time.sleep(wait)
                    continue

                if response.status_code >= 400:
                    logger.warning(
                        f"LLM provider error: {provider_name} returned {response.status_code}",
                        extra_data={"response": response.text[:200]},
                    )
                    break  # No point retrying 4xx errors, move to next provider

                response.raise_for_status()
                data = response.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if content:
                    logger.info(
                        f"LLM generation success: provider={provider_name}, model={model}"
                    )
                    return content

            except requests.exceptions.Timeout:
                logger.warning(
                    f"Timeout on {provider_name}, attempt {attempt + 1}/3"
                )
                if attempt < 2:
                    time.sleep(2)  # brief pause before retry
            except requests.exceptions.RequestException as exc:
                logger.warning(
                    f"Request failed for {provider_name}",
                    extra_data={"error": str(exc)},
                )
                if attempt < 2:
                    time.sleep(2)

    logger.error("All configured LLM providers failed")
    return None