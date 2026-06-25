from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kompressor.cli import app
from kompressor.hermes_install.installer import install_hermes_integration, uninstall_hermes_integration

runner = CliRunner()


def _fake_hermes(tmp_path: Path) -> Path:
    state = tmp_path / "enabled.txt"
    script = tmp_path / "hermes"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"state = pathlib.Path({str(state)!r})\n"
        "args = sys.argv[1:]\n"
        "if args[:3] == ['plugins', 'list', '--enabled']:\n"
        "    if state.exists(): print('enabled      user     0.1.0    kompressor')\n"
        "    raise SystemExit(0)\n"
        "if args[:2] == ['plugins', 'enable']:\n"
        "    state.write_text('1')\n"
        "    print('enabled')\n"
        "    raise SystemExit(0)\n"
        "if args[:2] == ['plugins', 'disable']:\n"
        "    state.unlink(missing_ok=True)\n"
        "    print('disabled')\n"
        "    raise SystemExit(0)\n"
        "if args[:1] == ['chat']:\n"
        "    import json, os\n"
        "    proof = os.environ.get('KOMPRESSOR_HERMES_PROOF_LOG')\n"
        "    if proof:\n"
        "        pathlib.Path(proof).write_text(json.dumps({\n"
        "            'strategy': 'json_table', 'original_chars': 100, 'compressed_chars': 50, 'saved_chars': 50\n"
        "        }) + '\\n')\n"
        "    print('Total: 60\\nCRITICAL: 20\\nWARNING: 20\\nINFO: 20')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _fake_hermes_agent(tmp_path: Path) -> Path:
    root = tmp_path / "hermes-agent"
    target = root / "agent" / "codex_runtime.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def f(agent, user_message, effective_task_id):\n"
        "    # NOTE: the user message is ALREADY appended to messages by the\n"
        "    # standard run_conversation() flow (line ~11823) before the early\n"
        "    # return reaches us. Do NOT append again — that would duplicate.\n"
        "\n"
        "    try:\n"
        "        turn = agent._codex_session.run_turn(user_input=user_message)\n"
        "    except Exception:\n"
        "        raise\n",
        encoding="utf-8",
    )
    return root


def test_install_and_uninstall_hermes_plugin(tmp_path: Path, monkeypatch) -> None:
    fake_bin = _fake_hermes(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    assert fake_bin.exists()
    home = tmp_path / "hermes-home"
    agent = _fake_hermes_agent(tmp_path)

    result = install_hermes_integration(hermes_home_dir=home, hermes_agent_dir=agent)
    assert result["changed"] is True
    assert (home / "plugins" / "kompressor" / "plugin.yaml").exists()
    assert (home / "plugins" / "kompressor" / "__init__.py").exists()
    config = json.loads((home / "plugins" / "kompressor" / "config.json").read_text())
    assert config["python_paths"]
    assert result["status"]["plugin_enabled"] is True

    uninstalled = uninstall_hermes_integration(hermes_home_dir=home, hermes_agent_dir=agent)
    assert uninstalled["plugin_removed"] is True
    assert not (home / "plugins" / "kompressor").exists()


def test_hermes_install_status_cli_json(tmp_path: Path, monkeypatch) -> None:
    _fake_hermes(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    agent = _fake_hermes_agent(tmp_path)
    result = runner.invoke(
        app,
        [
            "hermes",
            "status",
            "--hermes-home",
            str(tmp_path / "home"),
            "--hermes-agent-dir",
            str(agent),
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"]["plugin_installed"] is False


def test_hermes_install_cli_json_and_prove(tmp_path: Path, monkeypatch) -> None:
    _fake_hermes(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    agent = _fake_hermes_agent(tmp_path)
    result = runner.invoke(
        app,
        [
            "hermes",
            "install",
            "--hermes-home",
            str(tmp_path / "home"),
            "--hermes-agent-dir",
            str(agent),
            "--prove",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"]["plugin_installed"] is True
    assert payload["proof"]["ok"] is True

    prove = runner.invoke(app, ["hermes", "prove", "--json"])
    assert prove.exit_code == 0, prove.stdout
    assert json.loads(prove.stdout)["ok"] is True

    uninstall = runner.invoke(
        app,
        [
            "hermes",
            "uninstall",
            "--hermes-home",
            str(tmp_path / "home"),
            "--hermes-agent-dir",
            str(agent),
            "--json",
        ],
    )
    assert uninstall.exit_code == 0, uninstall.stdout
    assert json.loads(uninstall.stdout)["plugin_removed"] is True


def test_packaged_plugin_template_present() -> None:
    import importlib.resources as resources

    root = resources.files("kompressor.hermes_install.plugin_template")
    assert root.joinpath("plugin.yaml").read_text(encoding="utf-8").startswith("name: kompressor")
    assert "register(ctx)" in root.joinpath("__init__.py").read_text(encoding="utf-8")
