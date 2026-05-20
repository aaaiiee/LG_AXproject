from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class LlmResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cache_hit: bool = False


@runtime_checkable
class LlmClient(Protocol):
    model: str

    def complete(self, *, system: str, user: str) -> LlmResponse: ...


_PRICES_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
    "mock-haiku": (1.00, 5.00),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICES_PER_M_TOKENS.get(model, (1.00, 5.00))
    return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price


class AnthropicClient:
    def __init__(self, *, model: str | None = None) -> None:
        self.model = model or os.environ.get("LLM_MODEL", "claude-haiku-4-5")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK not installed. pip install anthropic"
            ) from exc
        self._client = Anthropic()

    def complete(self, *, system: str, user: str) -> LlmResponse:
        started = time.monotonic()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=[
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ],
            messages=[{"role": "user", "content": user}],
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        usage = response.usage
        cache_hit = bool(getattr(usage, "cache_read_input_tokens", 0))
        return LlmResponse(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=elapsed_ms,
            cache_hit=cache_hit,
        )
