import pytest

from kompressor.proxy import prepare_messages_request
from kompressor.security import find_secrets, redact_secrets


def test_find_and_redact_secret() -> None:
    text = "api_key=abcdefghijklmnopqrstuvwxyz"
    assert find_secrets(text)
    assert "REDACTED" in redact_secrets(text)


def test_proxy_refuses_secrets_by_default() -> None:
    with pytest.raises(ValueError):
        prepare_messages_request({"messages": [{"role": "user", "content": "api_key=abcdefghijklmnopqrstuvwxyz"}]})
