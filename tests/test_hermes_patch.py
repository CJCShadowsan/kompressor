from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kompressor.cli import app
from kompressor.hermes_patch import (
    apply_codex_bridge_patch,
    get_codex_bridge_status,
    uninstall_codex_bridge_patch,
)

runner = CliRunner()

FAKE_CODEX_RUNTIME = """from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

def run_codex_app_server_turn(agent, *, user_message, effective_task_id):
    # NOTE: the user message is ALREADY appended to messages by the
    # standard run_conversation() flow (line ~11823) before the early
    # return reaches us. Do NOT append again — that would duplicate.

    try:
        turn = agent._codex_session.run_turn(user_input=user_message)
    except Exception:
        raise
    return turn
"""


def _fake_hermes(tmp_path: Path) -> Path:
    root = tmp_path / "hermes-agent"
    target = root / "agent" / "codex_runtime.py"
    target.parent.mkdir(parents=True)
    target.write_text(FAKE_CODEX_RUNTIME, encoding="utf-8")
    return root


def test_codex_bridge_patch_apply_status_uninstall(tmp_path: Path) -> None:
    root = _fake_hermes(tmp_path)

    status = get_codex_bridge_status(root)
    assert status.can_apply is True
    assert status.patch_needed is True

    applied = apply_codex_bridge_patch(root)
    assert applied["changed"] is True
    patched_status = get_codex_bridge_status(root)
    assert patched_status.marker_present is True
    assert patched_status.bridge_present is True
    assert "BEGIN KOMPRESSOR" in (root / "agent" / "codex_runtime.py").read_text()

    second = apply_codex_bridge_patch(root)
    assert second["changed"] is False

    removed = uninstall_codex_bridge_patch(root)
    assert removed["changed"] is True
    final_status = get_codex_bridge_status(root)
    assert final_status.marker_present is False
    assert final_status.can_apply is True


def test_codex_bridge_status_treats_unmanaged_bridge_as_upstream(tmp_path: Path) -> None:
    root = _fake_hermes(tmp_path)
    apply_codex_bridge_patch(root)
    target = root / "agent" / "codex_runtime.py"
    text = target.read_text(encoding="utf-8")
    text = text.replace("    # BEGIN KOMPRESSOR HERMES CODEX MIDDLEWARE BRIDGE\n", "")
    text = text.replace("    # END KOMPRESSOR HERMES CODEX MIDDLEWARE BRIDGE\n", "")
    target.write_text(text, encoding="utf-8")

    status = get_codex_bridge_status(root)
    assert status.supported_upstream is True
    assert status.patch_needed is False
    assert status.can_uninstall is False


def test_hermes_patch_cli_status_json(tmp_path: Path) -> None:
    root = _fake_hermes(tmp_path)
    result = runner.invoke(app, ["hermes", "patch", "status", "--hermes-agent-dir", str(root), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"]["can_apply"] is True


def test_hermes_patch_cli_apply_and_uninstall(tmp_path: Path) -> None:
    root = _fake_hermes(tmp_path)
    apply_result = runner.invoke(app, ["hermes", "patch", "apply", "--hermes-agent-dir", str(root)])
    assert apply_result.exit_code == 0
    assert "Changed: yes" in apply_result.stdout

    uninstall_result = runner.invoke(app, ["hermes", "patch", "uninstall", "--hermes-agent-dir", str(root)])
    assert uninstall_result.exit_code == 0
    assert "Changed: yes" in uninstall_result.stdout
