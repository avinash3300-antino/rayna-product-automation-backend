"""Minimal Gemini REST client — httpx-based, no google-genai dep.

Used for FAQ generation. Same signature shape as claude_client.generate().
"""
import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiClient:
    def __init__(self):
        self.api_key = getattr(settings, "GEMINI_API_KEY", None)

    async def generate(
        self,
        prompt: str,
        system: str = "",
        model: str = DEFAULT_MODEL,
        max_tokens: int = 4096,
        temperature: float = 0.4,
        json_mode: bool = True,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set in settings")

        url = f"{GEMINI_BASE}/models/{model}:generateContent"
        gen_config: dict = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": gen_config,
            # Loosen safety filters — travel content occasionally trips
            # HARM_CATEGORY_DANGEROUS_CONTENT on battlefield/adventure tours.
            "safetySettings": [
                {"category": c, "threshold": "BLOCK_ONLY_HIGH"}
                for c in (
                    "HARM_CATEGORY_HARASSMENT",
                    "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "HARM_CATEGORY_DANGEROUS_CONTENT",
                )
            ],
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

        # Retry on 429/503 rate-limit / capacity errors (transient)
        # Backoff: 5s, 15s, 30s, 60s, 90s, 120s — total ~5 min, survives daily-quota bursts
        import asyncio as _asyncio
        backoff_schedule = [5, 15, 30, 60, 90, 120]
        last_err = None
        data = None
        for attempt, delay in enumerate([0] + backoff_schedule):
            if delay:
                await _asyncio.sleep(delay)
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, json=body, headers=headers)
            if r.status_code < 400:
                data = r.json()
                break
            if r.status_code in (429, 503):
                last_err = f"Gemini API {r.status_code}: {r.text[:200]}"
                continue
            raise RuntimeError(f"Gemini API {r.status_code}: {r.text[:400]}")
        if data is None:
            raise RuntimeError(f"Gemini API retries exhausted: {last_err}")

        # Extract text; be explicit about finishReason so caller sees WHY on empty
        cand = (data.get("candidates") or [{}])[0]
        finish = cand.get("finishReason", "UNKNOWN")
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        text_out = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if text_out:
            return text_out
        # Empty output — return a descriptive error the runner will log properly
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise RuntimeError(
            f"Gemini empty response finishReason={finish} blockReason={block_reason}"
        )


gemini_client = GeminiClient()
