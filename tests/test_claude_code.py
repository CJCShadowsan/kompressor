import json
import os

from typer.testing import CliRunner

from kompressor.claude_code import (
    build_claude_prompt,
    get_claude_code_status,
    install_claude_code_shims,
    prove_claude_code_shim,
    run_claude_code_shim,
    uninstall_claude_code_shims,
)
from kompressor.cli import app

runner = CliRunner()


def test_build_claude_prompt_uses_compressed_claude_bundle(tmp_path) -> None:
    context = tmp_path / "context.json"
    context.write_text(json.dumps([{"id": "AX-912", "event": "auth_timeout_error"}] * 40), encoding="utf-8")

    prompt = build_claude_prompt(context, task="Find auth failures")

    assert "SYSTEM:" in prompt
    assert "PAYLOAD:" in prompt
    assert "<kompressor:" in prompt
    assert "Find auth failures" in prompt


def test_run_claude_code_shim_dry_run_builds_claudish_command(tmp_path) -> None:
    context = tmp_path / "context.json"
    output = tmp_path / "prompt.txt"
    context.write_text(json.dumps([{"id": "AX-912", "event": "auth_timeout_error"}] * 40), encoding="utf-8")

    result = run_claude_code_shim(
        context,
        target="claudish",
        task="Find auth failures",
        model="ollama@qwen2.5:3b",
        output=output,
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["command"] == ["claudish", "--model", "ollama@qwen2.5:3b", "--stdin"]
    assert output.exists()
    assert "<kompressor:" in output.read_text(encoding="utf-8")


def test_install_and_uninstall_managed_shims(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    config_dir = tmp_path / "config"

    installed = install_claude_code_shims(bin_dir=bin_dir, config_dir=config_dir)
    assert installed["installed"] == [str(bin_dir / "kompressor-claude"), str(bin_dir / "kompressor-claudish")]
    assert os.access(bin_dir / "kompressor-claude", os.X_OK)
    assert "kompressor claude-code run --target claude" in (bin_dir / "kompressor-claude").read_text()

    status = get_claude_code_status(bin_dir=bin_dir, config_dir=config_dir)
    assert status.claude_shim_installed is True
    assert status.claudish_shim_installed is True

    removed = uninstall_claude_code_shims(bin_dir=bin_dir, config_dir=config_dir)
    assert str(bin_dir / "kompressor-claude") in removed["removed"]
    assert not (bin_dir / "kompressor-claude").exists()


def test_prove_structural_shim() -> None:
    result = prove_claude_code_shim(live=False)
    assert result["ok"] is True
    assert result["structural_checks"] == {
        "schema_rows_marker": True,
        "rows_marker": True,
        "first_row": True,
    }


def test_cli_claude_code_status_json() -> None:
    result = runner.invoke(app, ["claude-code", "status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"]["native_hook_findings"]["recommended_mode"] == "proxy"


def test_cli_claude_code_run_dry_run(tmp_path) -> None:
    context = tmp_path / "context.json"
    context.write_text(json.dumps([{"id": "AX-912", "event": "auth_timeout_error"}] * 40), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "claude-code",
            "run",
            str(context),
            "--target",
            "claudish",
            "--model",
            "ollama@qwen2.5:3b",
            "--task",
            "Find auth failures",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Command: claudish --model ollama@qwen2.5:3b --stdin" in result.output
    assert "<kompressor:" in result.output
