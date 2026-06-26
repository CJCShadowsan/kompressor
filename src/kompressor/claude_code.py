"""Claude Code and claudish shim integration helpers."""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from kompressor import __version__
from kompressor.plugins import get_plugin

Target = Literal["claude", "claudish"]

SHIM_MARKER = "# Managed by Kompressor Claude Code shim installer"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "kompressor"
CONFIG_FILE = "claude-code.json"


@dataclass(frozen=True)
class ClaudeCodeStatus:
    kompressor_version: str
    bin_dir: str
    config_path: str
    claude_binary: str | None
    claudish_binary: str | None
    claude_shim: str
    claudish_shim: str
    claude_proxy_shim: str
    claudish_proxy_shim: str
    claude_shim_installed: bool
    claudish_shim_installed: bool
    claude_proxy_shim_installed: bool
    claudish_proxy_shim_installed: bool
    native_hook_findings: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _config_path(config_dir: Path | None = None) -> Path:
    return (config_dir or DEFAULT_CONFIG_DIR) / CONFIG_FILE


def _shim_path(target: Target, bin_dir: Path | None = None, *, proxy: bool = False) -> Path:
    if proxy:
        name = "kompressor-claude-proxy" if target == "claude" else "kompressor-claudish-proxy"
    else:
        name = "kompressor-claude" if target == "claude" else "kompressor-claudish"
    return (bin_dir or DEFAULT_BIN_DIR) / name


def _is_managed_shim(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        return SHIM_MARKER in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _native_hook_findings() -> dict[str, object]:
    """Summarize known Claude Code hook capability boundaries.

    This is intentionally conservative: Claude Code plugins expose hooks that can
    observe prompts/tool use and run commands, but Kompressor has not found a
    documented hook contract that replaces the submitted user prompt before it is
    added to the model request. Prompt replacement is required for Hermes-like
    token savings.
    """

    return {
        "known_hook_events": [
            "UserPromptSubmit",
            "SessionStart",
            "PreToolUse",
            "PostToolUse",
            "PreCompact",
        ],
        "prompt_replacement_supported": False,
        "recommended_mode": "proxy",
        "reason": (
            "Claude Code plugin hooks can run around prompt and tool lifecycle events, "
            "but the locally observed plugin API does not prove that UserPromptSubmit "
            "can replace the prompt before provider dispatch. Proxy mode rewrites Anthropic "
            "Messages requests before provider dispatch and can provide Hermes-like savings."
        ),
    }


def get_claude_code_status(bin_dir: Path | None = None, config_dir: Path | None = None) -> ClaudeCodeStatus:
    claude_shim = _shim_path("claude", bin_dir)
    claudish_shim = _shim_path("claudish", bin_dir)
    claude_proxy_shim = _shim_path("claude", bin_dir, proxy=True)
    claudish_proxy_shim = _shim_path("claudish", bin_dir, proxy=True)
    return ClaudeCodeStatus(
        kompressor_version=__version__,
        bin_dir=str(bin_dir or DEFAULT_BIN_DIR),
        config_path=str(_config_path(config_dir)),
        claude_binary=shutil.which("claude"),
        claudish_binary=shutil.which("claudish"),
        claude_shim=str(claude_shim),
        claudish_shim=str(claudish_shim),
        claude_proxy_shim=str(claude_proxy_shim),
        claudish_proxy_shim=str(claudish_proxy_shim),
        claude_shim_installed=_is_managed_shim(claude_shim),
        claudish_shim_installed=_is_managed_shim(claudish_shim),
        claude_proxy_shim_installed=_is_managed_shim(claude_proxy_shim),
        claudish_proxy_shim_installed=_is_managed_shim(claudish_proxy_shim),
        native_hook_findings=_native_hook_findings(),
    )


def _script_for(target: Target, *, mode: str = "shim", port: int = 8765) -> str:
    if mode == "proxy":
        return f"""#!/usr/bin/env bash
{SHIM_MARKER}
set -euo pipefail
exec kompressor claude-code run-proxy --target {target} --port "${{KOMPRESSOR_CLAUDE_PROXY_PORT:-{port}}}" "$@"
"""
    return f"""#!/usr/bin/env bash
{SHIM_MARKER}
set -euo pipefail
exec kompressor claude-code run --target {target} "$@"
"""


def install_claude_code_shims(
    *,
    bin_dir: Path | None = None,
    config_dir: Path | None = None,
    targets: tuple[Target, ...] = ("claude", "claudish"),
    force: bool = False,
    mode: str = "shim",
    port: int = 8765,
) -> dict[str, object]:
    actual_bin_dir = bin_dir or DEFAULT_BIN_DIR
    actual_config_dir = config_dir or DEFAULT_CONFIG_DIR
    actual_bin_dir.mkdir(parents=True, exist_ok=True)
    actual_config_dir.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for target in targets:
        path = _shim_path(target, actual_bin_dir, proxy=mode == "proxy")
        if path.exists() and not _is_managed_shim(path) and not force:
            raise RuntimeError(f"refusing to overwrite unmanaged file: {path}")
        path.write_text(_script_for(target, mode=mode, port=port), encoding="utf-8")
        file_mode = path.stat().st_mode
        path.chmod(file_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(str(path))

    config = {
        "version": __version__,
        "mode": mode,
        "targets": list(targets),
        "port": port,
        "notes": "Managed by `kompressor claude-code install`; remove with `kompressor claude-code uninstall`.",
    }
    _config_path(actual_config_dir).write_text(json.dumps(config, indent=2), encoding="utf-8")
    return {
        "message": "Installed Kompressor Claude Code shim(s).",
        "installed": installed,
        "status": get_claude_code_status(actual_bin_dir, actual_config_dir).to_dict(),
    }


def uninstall_claude_code_shims(
    *,
    bin_dir: Path | None = None,
    config_dir: Path | None = None,
    targets: tuple[Target, ...] = ("claude", "claudish"),
    mode: str = "all",
) -> dict[str, object]:
    removed: list[str] = []
    for target in targets:
        paths = []
        if mode in {"all", "shim"}:
            paths.append(_shim_path(target, bin_dir))
        if mode in {"all", "proxy"}:
            paths.append(_shim_path(target, bin_dir, proxy=True))
        for path in paths:
            if _is_managed_shim(path):
                path.unlink()
                removed.append(str(path))
    config = _config_path(config_dir)
    if config.exists():
        config.unlink()
        removed.append(str(config))
    return {
        "message": "Removed Kompressor Claude Code shim(s).",
        "removed": removed,
        "status": get_claude_code_status(bin_dir, config_dir).to_dict(),
    }


def build_claude_prompt(context_path: Path, *, task: str = "") -> str:
    plugin = get_plugin("claude")
    return plugin.prepare_user_input(context_path.read_text(encoding="utf-8"), task=task).content


def _command_for(
    target: Target,
    *,
    command: str | None = None,
    model: str | None = None,
    allow_tools: bool = False,
) -> list[str]:
    binary = command or target
    if target == "claudish":
        cmd = [binary]
        if model:
            cmd.extend(["--model", model])
        cmd.append("--stdin")
        return cmd
    cmd = [binary, "-p"]
    if not allow_tools:
        cmd.extend(["--tools", ""])
    return cmd


def run_claude_code_shim(
    context_path: Path,
    *,
    target: Target = "claudish",
    task: str = "",
    model: str | None = None,
    command: str | None = None,
    output: Path | None = None,
    dry_run: bool = False,
    allow_tools: bool = False,
) -> dict[str, object]:
    prompt = build_claude_prompt(context_path, task=task)
    if output:
        output.write_text(prompt, encoding="utf-8")
    cmd = _command_for(target, command=command, model=model, allow_tools=allow_tools)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "command": cmd,
            "prompt": prompt,
            "output_path": str(output) if output else None,
        }
    proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, check=False)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": cmd,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "output_path": str(output) if output else None,
    }


def run_claude_code_proxy(
    *,
    target: Target = "claude",
    port: int = 8765,
    upstream: str = "https://api.anthropic.com",
    model: str | None = None,
    command: str | None = None,
    allow_tools: bool = False,
    args: tuple[str, ...] = (),
) -> dict[str, object]:
    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"
    proxy_cmd = [
        "kompressor",
        "claude-code",
        "proxy",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--upstream",
        upstream,
    ]
    proxy_proc = subprocess.Popen(proxy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    time.sleep(0.5)
    if proxy_proc.poll() is not None:
        stderr = proxy_proc.stderr.read() if proxy_proc.stderr else ""
        return {"ok": False, "returncode": proxy_proc.returncode, "proxy_command": proxy_cmd, "stderr": stderr}
    cmd = _command_for(target, command=command, model=model, allow_tools=allow_tools)
    cmd.extend(args)
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False, env=env)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "proxy_command": proxy_cmd,
            "command": cmd,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    finally:
        proxy_proc.send_signal(signal.SIGTERM)
        try:
            proxy_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proxy_proc.kill()


def prove_claude_code_shim(
    *,
    target: Target = "claudish",
    model: str | None = None,
    command: str | None = None,
    live: bool = False,
    allow_tools: bool = False,
) -> dict[str, object]:
    rows = []
    for _ in range(40):
        rows.append({"id": "AX-912", "event": "auth_timeout_error", "ip": "10.0.1.250", "severity": "CRITICAL"})
        rows.append({"id": "AX-913", "event": "db_query_slow_exec", "ip": "10.0.4.12", "severity": "WARNING"})
    task = (
        "Use only compact context. The first row after @rows is [0,0,0,0]. "
        "What IP does index 0 in the ip enum decode to? Reply with IP only."
    )
    expected = "10.0.1.250"
    with tempfile.TemporaryDirectory(prefix="kompressor-claude-proof-") as tmp:
        context_path = Path(tmp) / "context.json"
        prompt_path = Path(tmp) / "prompt.txt"
        context_path.write_text(json.dumps(rows), encoding="utf-8")
        prompt = build_claude_prompt(context_path, task=task)
        prompt_path.write_text(prompt, encoding="utf-8")
        structural_ok = "<kompressor:schema_rows_v1>" in prompt and "@rows" in prompt and "[0,0,0,0]" in prompt
        payload: dict[str, object] = {
            "ok": structural_ok,
            "live": live,
            "expected": expected,
            "prompt_bytes": len(prompt),
            "structural_checks": {
                "schema_rows_marker": "<kompressor:schema_rows_v1>" in prompt,
                "rows_marker": "@rows" in prompt,
                "first_row": "[0,0,0,0]" in prompt,
            },
        }
        if not live:
            payload["message"] = (
                "Claude Code shim structural proof passed." if structural_ok else "Structural proof failed."
            )
            return payload
        result = run_claude_code_shim(
            context_path,
            target=target,
            task=task,
            model=model,
            command=command,
            allow_tools=allow_tools,
        )
        stdout = str(result.get("stdout", "")).strip()
        live_ok = bool(result.get("ok")) and expected in stdout
        payload.update(
            {
                "ok": structural_ok and live_ok,
                "message": "Claude Code shim live proof passed." if live_ok else "Claude Code shim live proof failed.",
                "result": result,
                "observed": stdout,
            }
        )
        return payload
