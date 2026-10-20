"""Única puerta a la API de Claude. Solo se usa desde el backend.

Todas las llamadas piden salida estructurada validada con Pydantic. Se usa streaming
siempre: el producto principal puede superar las 30k palabras de salida y una
llamada sin streaming se arriesga al timeout HTTP.
"""

from dataclasses import dataclass
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

# USD por millón de tokens: (input, output, lectura de caché). Escritura de caché = 1.25x input.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-opus-4-8": (5.0, 25.0, 0.50),  # destino posible del fallback por categoría
}
# Reintenta en el servidor con el modelo recomendado si un clasificador rechaza la petición.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """Error de generación que no se arregla reintentando la misma petición."""


class LLMRefusal(LLMError):
    pass


class LLMTruncated(LLMError):
    pass


class LLMInvalidOutput(LLMError):
    pass


@dataclass(frozen=True)
class CallUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int

    @property
    def cost_usd(self) -> float:
        price_in, price_out, price_cache = PRICES.get(self.model, PRICES["claude-opus-5-5"])
        return (
            self.input_tokens * price_in
            + self.cache_write_tokens * price_in * 1.25
            + self.cache_read_tokens * price_cache
            + self.output_tokens * price_out
        ) / 1_000_000


class StructuredLLM(Protocol):
    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str,
        max_tokens: int,
        effort: str,
    ) -> tuple[T, CallUsage]: ...


class ClaudeClient:
    def __init__(self, api_key: str = "", max_retries: int = 3) -> None:
        # Sin api_key explícita, el SDK resuelve ANTHROPIC_API_KEY u otra credencial del entorno.
        kwargs: dict = {"max_retries": max_retries}
        if api_key:
            kwargs["api_key"] = api_key
        self._client = anthropic.AsyncAnthropic(**kwargs)

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str,
        max_tokens: int,
        effort: str,
    ) -> tuple[T, CallUsage]:
        try:
            async with self._client.beta.messages.stream(
                model=model,
                max_tokens=max_tokens,
                # El system prompt de cada mercado es fijo: se cachea entre llamadas.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                message = await stream.get_final_message()
        except ValidationError as exc:
            raise LLMInvalidOutput(_short_errors(exc)) from exc

        usage = CallUsage(
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            cache_read_tokens=message.usage.cache_read_input_tokens or 0,
            cache_write_tokens=message.usage.cache_creation_input_tokens or 0,
        )
        if message.stop_reason == "refusal":
            category = getattr(message.stop_details, "category", None)
            raise LLMRefusal(f"la IA rechazó la petición (categoría: {category})")
        if message.stop_reason == "max_tokens":
            raise LLMTruncated(f"la respuesta superó max_tokens={max_tokens}")
        if message.parsed_output is None:
            raise LLMInvalidOutput("la respuesta no trajo salida estructurada")
        return message.parsed_output, usage


def _short_errors(exc: ValidationError, limit: int = 10) -> str:
    parts = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:limit]]
    return "; ".join(parts)
