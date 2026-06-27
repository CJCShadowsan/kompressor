"""Agent wrapper helpers for launching clients through Kompressor Gateway."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WrapPlan:
    agent: str
    command: list[str]
    env: dict[str, str]
    settings: dict[str, str]


def build_wrap_plan(agent: str, *, gateway_url: str = "http://127.0.0.1:8787", args: tuple[str, ...] = ()) -> WrapPlan:
    known = {"claude", "claudish", "codex", "aider", "opencode"}
    if agent not in known:
        raise ValueError(f"unsupported agent {agent!r}; expected one of {', '.join(sorted(known))}")
    binary = shutil.which(agent) or agent
    env = os.environ.copy()
    settings = {
        "OPENAI_BASE_URL": f"{gateway_url.rstrip('/')}/v1",
        "ANTHROPIC_BASE_URL": gateway_url.rstrip("/"),
        "ANTHROPIC_API_URL": gateway_url.rstrip("/"),
    }
    env.update(settings)
    command = [binary, *args]
    if agent == "claudish" and "--stdin" not in command and not args:
        command.append("--stdin")
    return WrapPlan(agent=agent, command=command, env=env, settings=settings)


def print_cursor_settings(gateway_url: str = "http://127.0.0.1:8787") -> dict[str, str]:
    return {
        "openai_base_url": f"{gateway_url.rstrip('/')}/v1",
        "anthropic_base_url": gateway_url.rstrip("/"),
    }


def run_wrapped_agent(agent: str, *, gateway_url: str, args: tuple[str, ...]) -> dict[str, Any]:
    plan = build_wrap_plan(agent, gateway_url=gateway_url, args=args)
    proc = subprocess.run(plan.command, env=plan.env, text=True, capture_output=True, check=False)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": plan.command,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def wait_for_gateway(url: str, *, timeout: float = 10.0) -> bool:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=1) as response:
                return response.status == 200
        except Exception:
            time.sleep(0.1)
    return False
