"""Secret detection and redaction."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    value: str


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}")),
    ("api_key", re.compile(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*['\"]?[A-Za-z0-9._\-]{16,}")),
    ("database_url", re.compile(r"[a-z]+://[^\s:]+:[^\s@]+@[^\s]+")),
)


def find_secrets(text: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            findings.append(SecretFinding(kind, match.group(0)))
    return findings


def redact_secrets(text: str) -> str:
    redacted = text
    for kind, pattern in _PATTERNS:
        redacted = pattern.sub(f"[REDACTED_{kind.upper()}]", redacted)
    return redacted
