import pytest

from kompressor.engine import KompressorEngine
from kompressor.harnesses import get_harness_adapter


def _result():
    return KompressorEngine().optimize([{"id": "AX-912", "event": "auth_timeout_error"}] * 20)


@pytest.mark.parametrize("name", ["generic", "claude", "openai", "gemini", "hermes", "codex"])
def test_harnesses_package_context(name: str) -> None:
    bundle = get_harness_adapter(name).package(_result(), "Find auth failures")
    assert bundle.harness == name
    assert "auth_timeout_error" in bundle.content
    assert bundle.data


def test_claude_harness_shape() -> None:
    bundle = get_harness_adapter("claude").package(_result(), "Summarize")
    assert "system" in bundle.data
    assert bundle.data["messages"][0]["role"] == "user"


def test_openai_harness_shape() -> None:
    bundle = get_harness_adapter("openai").package(_result(), "Summarize")
    assert bundle.data["messages"][0]["role"] == "developer"


def test_codex_harness_shape() -> None:
    bundle = get_harness_adapter("codex").package(_result(), "Summarize")
    assert bundle.data["messages"][0]["role"] == "developer"
    assert "CODEX_INPUT" in bundle.content


def test_gemini_harness_shape() -> None:
    bundle = get_harness_adapter("gemini").package(_result(), "Summarize")
    assert "system_instruction" in bundle.data


def test_hermes_harness_mentions_task_local_rules() -> None:
    bundle = get_harness_adapter("hermes").package(_result(), "Summarize")
    assert "Hermes" in bundle.content
    assert "task-local parsing rules" in bundle.content


def test_unknown_harness_rejected() -> None:
    with pytest.raises(ValueError):
        get_harness_adapter("unknown")
