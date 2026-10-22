"""Gemini (generación de imagen). NO tiene cuota gratis: solo corre si hay un tope diario en USD."""

import base64
from typing import ClassVar

import httpx

from app.ads.images.base import (
    ImageRequest,
    ProviderError,
    ProviderImage,
    ProviderQuota,
    ProviderRejected,
)

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiImageProvider:
    name: ClassVar[str] = "gemini"
    kind: ClassVar[str] = "generate"

    def __init__(
        self,
        api_key: str,
        model: str,
        price_usd: float,
        daily_cap_usd: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._key, self._model, self._price, self._cap = api_key, model, price_usd, daily_cap_usd
        self._client = client or httpx.AsyncClient(timeout=90)

    def enabled(self) -> bool:
        return bool(self._key) and self._cap > 0

    def unit_cost(self) -> float:
        return self._price

    @property
    def daily_cap(self) -> float:
        return self._cap

    async def fetch(self, request: ImageRequest) -> ProviderImage:
        style = request.style or "clean modern photo"
        prompt = f"{request.prompt}. Style: {style}. Avoid: {request.negative_prompt}."
        response = await self._client.post(
            f"{BASE}/{self._model}:generateContent",
            headers={"x-goog-api-key": self._key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {"aspectRatio": request.aspect},
                },
            },
        )
        if response.status_code == 429:
            raise ProviderQuota("Gemini 429")
        if response.status_code in (400, 403) and "quota" in response.text.lower():
            raise ProviderQuota("Gemini sin cuota")
        if response.status_code != 200:
            raise ProviderError(f"Gemini {response.status_code}")
        body = response.json()
        if body.get("promptFeedback", {}).get("blockReason"):
            raise ProviderRejected("Gemini rechazó el prompt")
        for candidate in body.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return ProviderImage(
                        data=base64.b64decode(inline["data"]),
                        mime=inline.get("mimeType") or inline.get("mime_type") or "image/png",
                        provider=self.name,
                        cost_usd=self._price,
                        credit={"provider": self.name, "model": self._model, "generated": True},
                    )
        raise ProviderRejected("Gemini no devolvió imagen")
