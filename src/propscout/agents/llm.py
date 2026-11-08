"""Thin OpenRouter client: OpenAI SDK + JSON mode + pydantic validation + model fallback."""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from propscout.config import Settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    def complete_json(self, system: str, user: str, schema: type[T]) -> T: ...


def _extract_json(text: str) -> str:
    """Models sometimes wrap JSON in ``` fences or add prose; pull out the object."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


class OpenRouterLLM:
    def __init__(self, settings: Settings, model: str | None = None):
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set (see .env.example)")
        self.model = model or settings.model
        self.fallbacks = [m for m in settings.fallback_model_list if m != self.model]
        self.client = OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            default_headers={"X-Title": "PropScout"},
            timeout=90,
            max_retries=2,
        )
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}

    def _chat(self, messages: list[dict]) -> str:
        extra: dict = {"usage": {"include": True}}
        if self.fallbacks:
            extra["models"] = [self.model, *self.fallbacks]
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
            extra_body=extra,
        )
        if resp.usage:
            self.usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
            self.usage["completion_tokens"] += resp.usage.completion_tokens or 0
            self.usage["cost"] += float(getattr(resp.usage, "cost", 0) or 0)
        return resp.choices[0].message.content or ""

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        schema_txt = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        messages = [
            {
                "role": "system",
                "content": f"{system}\n\nRespond with ONLY a JSON object matching this JSON schema:\n"
                f"{schema_txt}",
            },
            {"role": "user", "content": user},
        ]
        text = self._chat(messages)
        try:
            return schema.model_validate_json(_extract_json(text))
        except ValidationError as err:
            log.info("LLM JSON invalid, retrying once: %s", err)
            messages += [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": f"That JSON was invalid: {err}. Return corrected JSON only.",
                },
            ]
            return schema.model_validate_json(_extract_json(self._chat(messages)))
