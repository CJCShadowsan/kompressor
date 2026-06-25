import json

import pytest

from kompressor.plugins import available_plugins, get_plugin, plugin_manifests

BIG_JSON = json.dumps([{"id": idx, "event": "auth_timeout_error", "service": "api"} for idx in range(40)])


@pytest.mark.parametrize("name", ["generic", "claude", "openai", "gemini", "hermes", "codex"])
def test_builtin_plugin_exists_for_each_harness(name: str) -> None:
    plugin = get_plugin(name, threshold_chars=20)
    assert plugin.manifest.harness == name
    assert plugin.manifest.entrypoint.startswith("kompressor.plugins.builtin:")
    assert plugin.manifest.hooks


def test_available_plugins_include_all_canonical_harnesses() -> None:
    assert set(available_plugins()) == {"generic", "claude", "openai", "gemini", "hermes", "codex"}
    assert set(plugin_manifests()) == set(available_plugins())


def test_plugin_prepares_user_input_with_harness_bundle() -> None:
    result = get_plugin("hermes", threshold_chars=20).prepare_user_input(BIG_JSON, task="Find auth failures")
    assert result.changed is True
    assert result.result is not None
    assert result.bundle is not None
    assert result.metadata["harness"] == "hermes"
    assert "KOMPRESSOR_PAYLOAD" in result.content
    assert "Find auth failures" in result.content


def test_plugin_respects_threshold() -> None:
    result = get_plugin("generic", threshold_chars=10_000).prepare_user_input(BIG_JSON)
    assert result.changed is False
    assert result.metadata["reason"] == "below_threshold"


def test_plugin_redacts_secrets_before_compression() -> None:
    secret_payload = BIG_JSON + "\nsecret=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
    result = get_plugin("generic", threshold_chars=20, redact=True).prepare_user_input(secret_payload)
    assert result.changed is True
    assert "[REDACTED_API_KEY]" in result.content


def test_plugin_refuses_secrets_by_default() -> None:
    secret_payload = BIG_JSON + "\nsecret=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
    with pytest.raises(ValueError):
        get_plugin("generic", threshold_chars=20).prepare_user_input(secret_payload)


def test_plugin_request_rewrite_records_metadata() -> None:
    request = {"messages": [{"role": "user", "content": BIG_JSON}]}
    prepared = get_plugin("claude", threshold_chars=20).prepare_request(request)
    assert prepared["messages"][0]["content"] != BIG_JSON
    assert prepared["_kompressor_plugin"]["harness"] == "claude"
    assert prepared["_kompressor_plugin"]["rewrites"][0]["strategy"] == "json_table"


def test_unknown_plugin_rejected() -> None:
    with pytest.raises(ValueError):
        get_plugin("unknown")
