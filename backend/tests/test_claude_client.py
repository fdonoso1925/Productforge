import asyncio
from types import SimpleNamespace

import pytest

from app.content.claude_client import (
    CallUsage,
    ClaudeClient,
    LLMRefusal,
    LLMTruncated,
)
from app.content.schemas import ProblemProposals
from tests.fakes import make_problem


def test_cost_uses_model_prices() -> None:
    usage = CallUsage("claude-opus-5-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000)
    # 4 input + 5 escritura (1.25x) + 0.20 lectura + 20 output
    assert usage.cost_usd == pytest.approx(29.20)


class FakeStream:
    def __init__(self, message):
        self.message = message
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self.message


def fake_message(stop_reason: str, parsed=None):
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=5,
    )
    return SimpleNamespace(
        model="claude-opus-5-5",
        usage=usage,
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber"),
        parsed_output=parsed,
    )


def call(message):
    client = ClaudeClient(api_key="test-key")
    stream = FakeStream(message)
    client._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    result = asyncio.run(
        client.structured(
            system="s",
            user="u",
            schema=ProblemProposals,
            model="claude-opus-5-5",
            max_tokens=100,
            effort="high",
        )
    )
    return result, stream.kwargs


def test_success_returns_parsed_and_usage_and_sends_expected_params() -> None:
    parsed = ProblemProposals(problems=[make_problem()])
    (result, usage), kwargs = call(fake_message("end_turn", parsed))
    assert result is parsed
    assert usage.cache_read_tokens == 0 and usage.cache_write_tokens == 5
    assert kwargs["output_format"] is ProblemProposals
    assert kwargs["output_config"] == {"effort": "high"}
    assert kwargs["fallbacks"] == "default"
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_refusal_raises() -> None:
    with pytest.raises(LLMRefusal, match="cyber"):
        call(fake_message("refusal"))


def test_truncation_raises() -> None:
    with pytest.raises(LLMTruncated):
        call(fake_message("max_tokens"))
