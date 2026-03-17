"""Wrapper centralisé pour tous les appels à Claude API."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import anthropic

from backend.utils.logger import logger

# Tarifs par million de tokens (USD)
_PRICING: dict[str, tuple[float, float]] = {
    # (input $/M, output $/M)
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}


@dataclass
class ClaudeResponse:
    content: str
    json_data: dict[str, Any] | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_ms: int
    model: str


class ClaudeClient:
    """Appels async vers Claude avec retries, logging et calcul de coût."""

    def __init__(self, api_key: str, default_max_tokens: int = 1024) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.default_max_tokens = default_max_tokens
        self.total_cost: float = 0.0

    async def ask(
        self,
        model: str,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float = 0.3,
    ) -> ClaudeResponse:
        """Appelle Claude et retourne la réponse + métadonnées.

        3 tentatives avec backoff exponentiel en cas d'erreur transitoire.
        """
        max_tokens = max_tokens or self.default_max_tokens
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                response = await self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                duration_ms = int((time.perf_counter() - t0) * 1000)

                content = response.content[0].text
                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens
                cost = self._compute_cost(model, tokens_in, tokens_out)
                self.total_cost += cost

                json_data = self._try_parse_json(content)

                logger.info(
                    "Claude {} — {}tok in / {}tok out — ${:.4f} — {}ms",
                    model,
                    tokens_in,
                    tokens_out,
                    cost,
                    duration_ms,
                )

                return ClaudeResponse(
                    content=content,
                    json_data=json_data,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    duration_ms=duration_ms,
                    model=model,
                )
            except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
                last_error = exc
                wait = 2**attempt
                logger.warning("Claude retry {}/3 après {}s — {}", attempt + 1, wait, exc)
                await asyncio.sleep(wait)
            except anthropic.APIStatusError as exc:
                logger.error("Claude erreur API — {}", exc)
                raise

        raise RuntimeError(f"Claude API — 3 tentatives échouées: {last_error}")

    async def ask_json(
        self,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.3,
    ) -> ClaudeResponse:
        """Comme ask() mais force une réponse JSON valide.

        Ajoute une instruction JSON au prompt, retry une fois si JSON invalide.
        """
        json_instruction = "\n\nRéponds UNIQUEMENT en JSON valide."
        if schema:
            json_instruction += f"\nSchéma attendu:\n```json\n{json.dumps(schema, indent=2)}\n```"
        full_prompt = prompt + json_instruction

        response = await self.ask(model, system, full_prompt, max_tokens, temperature)

        if response.json_data is None:
            logger.warning("JSON invalide, retry…")
            response = await self.ask(
                model, system, full_prompt + "\n\n(Ta réponse précédente n'était pas du JSON valide. Réessaie.)",
                max_tokens, temperature,
            )
        return response

    @staticmethod
    def _compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
        price_in, price_out = _PRICING.get(model, (3.0, 15.0))
        return (tokens_in * price_in + tokens_out * price_out) / 1_000_000

    @staticmethod
    def _try_parse_json(text: str) -> dict[str, Any] | None:
        """Tente d'extraire un objet JSON depuis le texte."""
        # Essai direct
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Essai avec extraction entre ```json ... ```
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass
        # Essai avec extraction entre { ... }
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                return json.loads(text[first : last + 1])
            except json.JSONDecodeError:
                pass
        return None
