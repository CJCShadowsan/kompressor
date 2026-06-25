"""Reversible Hermes Codex runtime compatibility patch.

The patch is intentionally explicit. Kompressor never mutates Hermes at package
install time; users run the CLI command after reviewing status. This module
keeps the patch small, marker-bounded, syntax-checked, and removable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

BEGIN_MARKER = "# BEGIN KOMPRESSOR HERMES CODEX MIDDLEWARE BRIDGE"
END_MARKER = "# END KOMPRESSOR HERMES CODEX MIDDLEWARE BRIDGE"
ANCHOR = """    # NOTE: the user message is ALREADY appended to messages by the
    # standard run_conversation() flow (line ~11823) before the early
    # return reaches us. Do NOT append again — that would duplicate.

    try:
        turn = agent._codex_session.run_turn(user_input=user_message)
"""

PATCH_BLOCK = """    # BEGIN KOMPRESSOR HERMES CODEX MIDDLEWARE BRIDGE
    # Temporary compatibility bridge for Hermes Codex app-server runtimes.
    # The normal chat-completions path applies llm_request middleware before
    # provider dispatch; this runtime bypasses that path, so expose the same
    # rewrite opportunity before handing user input to the Codex subprocess.
    try:
        from hermes_cli.middleware import apply_llm_request_middleware

        _mw = apply_llm_request_middleware(
            {"messages": [{"role": "user", "content": user_message}]},
            task_id=effective_task_id,
            session_id=agent.session_id or "",
            platform=agent.platform or "",
            model=agent.model,
            provider=agent.provider,
            base_url=agent.base_url,
            api_mode=agent.api_mode,
            api_call_count=1,
        )
        _mw_messages = _mw.payload.get("messages") if isinstance(_mw.payload, dict) else None
        if isinstance(_mw_messages, list):
            for _mw_msg in reversed(_mw_messages):
                if isinstance(_mw_msg, dict) and _mw_msg.get("role") == "user":
                    _mw_content = _mw_msg.get("content")
                    if isinstance(_mw_content, str) and _mw_content:
                        user_message = _mw_content
                    break
    except Exception:
        logger.debug("codex app-server request middleware bridge failed", exc_info=True)
    # END KOMPRESSOR HERMES CODEX MIDDLEWARE BRIDGE

"""

PATCHED_REPLACEMENT = ANCHOR.replace("    try:\n", PATCH_BLOCK + "    try:\n", 1)


@dataclass(frozen=True)
class PatchStatus:
    """Status for the Hermes Codex middleware bridge patch."""

    hermes_agent_dir: str | None
    target_file: str | None
    exists: bool
    marker_present: bool
    bridge_present: bool
    patch_needed: bool
    supported_upstream: bool
    can_apply: bool
    can_uninstall: bool
    reason: str
    backup_dir: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _backup_root() -> Path:
    return Path.home() / ".kompressor" / "patches" / "hermes"


def find_hermes_agent_dir(explicit: Path | None = None) -> Path | None:
    """Locate a Hermes Agent checkout/install directory."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    env_dir = os.environ.get("HERMES_AGENT_DIR")
    if env_dir:
        candidates.append(Path(env_dir).expanduser())
    candidates.append(Path.home() / ".hermes" / "hermes-agent")

    hermes_bin = shutil.which("hermes")
    if hermes_bin:
        try:
            script = Path(hermes_bin).read_text(encoding="utf-8", errors="ignore")
            for token in script.replace('"', " ").split():
                if token.endswith("/venv/bin/hermes"):
                    candidates.append(Path(token).parents[2])
        except OSError:
            pass

    for candidate in candidates:
        target = candidate / "agent" / "codex_runtime.py"
        if target.exists():
            return candidate.resolve()
    return None


def _target_file(hermes_agent_dir: Path | None = None) -> Path | None:
    root = find_hermes_agent_dir(hermes_agent_dir)
    if root is None:
        return None
    return root / "agent" / "codex_runtime.py"


def _bridge_present(text: str) -> bool:
    return (
        "apply_llm_request_middleware" in text
        and "_codex_session.run_turn(user_input=user_message)" in text
        and "codex app-server request middleware bridge" in text
    )


def get_codex_bridge_status(hermes_agent_dir: Path | None = None) -> PatchStatus:
    target = _target_file(hermes_agent_dir)
    backup_dir = str(_backup_root())
    if target is None:
        return PatchStatus(
            None,
            None,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            "Hermes Agent directory not found",
            backup_dir,
        )
    if not target.exists():
        return PatchStatus(
            str(target.parents[1]),
            str(target),
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            "target file missing",
            backup_dir,
        )
    text = target.read_text(encoding="utf-8")
    marker_present = BEGIN_MARKER in text and END_MARKER in text
    bridge_present = _bridge_present(text)
    anchor_present = ANCHOR in text
    supported_upstream = bridge_present and not marker_present
    patch_needed = not bridge_present
    can_apply = patch_needed and anchor_present
    can_uninstall = marker_present
    if marker_present:
        reason = "Kompressor-managed bridge patch is installed"
    elif supported_upstream:
        reason = "Hermes already contains a Codex llm_request middleware bridge"
    elif can_apply:
        reason = "patch can be applied"
    else:
        reason = "target shape is unknown; refusing without a compatible anchor"
    return PatchStatus(
        str(target.parents[1]),
        str(target),
        True,
        marker_present,
        bridge_present,
        patch_needed,
        supported_upstream,
        can_apply,
        can_uninstall,
        reason,
        backup_dir,
    )


def _syntax_check(path: Path, python: str | None = None) -> None:
    interpreter = python or sys.executable
    result = subprocess.run(
        [interpreter, "-m", "py_compile", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"py_compile failed for {path}")


def _backup(target: Path) -> Path:
    root = _backup_root()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / f"codex_runtime.py.{timestamp}.bak"
    shutil.copy2(target, backup)
    return backup


def apply_codex_bridge_patch(
    hermes_agent_dir: Path | None = None,
    *,
    force: bool = False,
    python: str | None = None,
) -> dict[str, object]:
    """Apply the marker-bounded Codex middleware bridge patch."""
    status = get_codex_bridge_status(hermes_agent_dir)
    if status.bridge_present and not force:
        return {"changed": False, "status": status.to_dict(), "message": status.reason}
    if not status.can_apply and not force:
        raise RuntimeError(status.reason)
    if status.target_file is None:
        raise RuntimeError("target file not found")

    target = Path(status.target_file)
    text = target.read_text(encoding="utf-8")
    if BEGIN_MARKER in text and END_MARKER in text:
        return {"changed": False, "status": status.to_dict(), "message": "patch already installed"}
    if ANCHOR not in text:
        if not force:
            raise RuntimeError("target file does not contain expected anchor")
        raise RuntimeError("force cannot apply without a known insertion anchor")

    backup = _backup(target)
    target.write_text(text.replace(ANCHOR, PATCHED_REPLACEMENT, 1), encoding="utf-8")
    try:
        _syntax_check(target, python=python)
    except Exception:
        shutil.copy2(backup, target)
        raise
    new_status = get_codex_bridge_status(hermes_agent_dir)
    return {
        "changed": True,
        "backup": str(backup),
        "status": new_status.to_dict(),
        "message": "Kompressor Hermes Codex middleware bridge applied",
    }


def uninstall_codex_bridge_patch(
    hermes_agent_dir: Path | None = None,
    *,
    python: str | None = None,
) -> dict[str, object]:
    """Remove the marker-bounded patch if Kompressor installed it."""
    status = get_codex_bridge_status(hermes_agent_dir)
    if not status.marker_present:
        return {"changed": False, "status": status.to_dict(), "message": "no Kompressor-managed patch installed"}
    if status.target_file is None:
        raise RuntimeError("target file not found")

    target = Path(status.target_file)
    text = target.read_text(encoding="utf-8")
    start = text.index(BEGIN_MARKER)
    # Remove whole indented line containing BEGIN plus through END line and following blank line if present.
    line_start = text.rfind("\n", 0, start) + 1
    end = text.index(END_MARKER, start) + len(END_MARKER)
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    else:
        line_end += 1
        if text[line_end : line_end + 1] == "\n":
            line_end += 1
    backup = _backup(target)
    target.write_text(text[:line_start] + text[line_end:], encoding="utf-8")
    try:
        _syntax_check(target, python=python)
    except Exception:
        shutil.copy2(backup, target)
        raise
    new_status = get_codex_bridge_status(hermes_agent_dir)
    return {
        "changed": True,
        "backup": str(backup),
        "status": new_status.to_dict(),
        "message": "Kompressor Hermes Codex middleware bridge removed",
    }
