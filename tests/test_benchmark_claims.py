from pathlib import Path


def test_readme_claims_are_estimate_qualified() -> None:
    text = Path("README.md").read_text()
    assert "cannot alter provider tokenizers or pricing" in text
    assert "estimates are proxies" in text
    assert "30%" not in text or "benchmark" in text.lower()
    assert "--harness hermes" in text
