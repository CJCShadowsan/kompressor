from kompressor.legacy import ClaudeTokenSaver


def test_legacy_api_calculate_savings() -> None:
    payload = [{"id": "AX-912", "event": "auth_timeout_error"}] * 10
    analysis = ClaudeTokenSaver().calculate_savings(payload)
    assert analysis["standard_tokens"] > analysis["optimized_tokens"]
    assert "optimized_payload" in analysis
