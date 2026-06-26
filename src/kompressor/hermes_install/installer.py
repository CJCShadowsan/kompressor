"""User-facing installer for Kompressor's Hermes integration."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from kompressor import __version__
from kompressor.hermes_patch import apply_codex_bridge_patch, get_codex_bridge_status, uninstall_codex_bridge_patch

PLUGIN_NAME = "kompressor"


@dataclass(frozen=True)
class HermesInstallStatus:
    """Status for the installed Hermes plugin and compatibility bridge."""

    kompressor_version: str
    hermes_binary: str | None
    hermes_home: str
    plugin_dir: str
    plugin_installed: bool
    plugin_enabled: bool
    plugin_version: str | None
    python_paths: tuple[str, ...]
    kompressor_cli: str | None
    patch_status: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def hermes_home(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()


def _plugin_dir(home: Path) -> Path:
    return home / "plugins" / PLUGIN_NAME


def _current_python_paths() -> tuple[str, ...]:
    import kompressor

    package = Path(kompressor.__file__).resolve().parent
    return (str(package.parent),)


def _kompressor_cli() -> str | None:
    return shutil.which("kompressor")


def _hermes_binary() -> str | None:
    return shutil.which("hermes")


def _read_plugin_version(plugin_dir: Path) -> str | None:
    manifest = plugin_dir / "plugin.yaml"
    if not manifest.exists():
        return None
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def _enabled_plugin_names() -> set[str]:
    hermes = _hermes_binary()
    if hermes is None:
        return set()
    proc = subprocess.run(
        [hermes, "plugins", "list", "--enabled", "--plain"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    names: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if parts:
            names.add(parts[-1])
    return names


def get_hermes_install_status(
    hermes_home_dir: Path | None = None,
    hermes_agent_dir: Path | None = None,
) -> HermesInstallStatus:
    home = hermes_home(hermes_home_dir)
    plugin_dir = _plugin_dir(home)
    patch = get_codex_bridge_status(hermes_agent_dir).to_dict()
    return HermesInstallStatus(
        kompressor_version=__version__,
        hermes_binary=_hermes_binary(),
        hermes_home=str(home),
        plugin_dir=str(plugin_dir),
        plugin_installed=(plugin_dir / "plugin.yaml").exists() and (plugin_dir / "__init__.py").exists(),
        plugin_enabled=PLUGIN_NAME in _enabled_plugin_names(),
        plugin_version=_read_plugin_version(plugin_dir),
        python_paths=_current_python_paths(),
        kompressor_cli=_kompressor_cli(),
        patch_status=patch,
    )


def _template_text(name: str) -> str:
    resource = resources.files("kompressor.hermes_install.plugin_template").joinpath(name)
    text = resource.read_text(encoding="utf-8")
    if name == "plugin.yaml":
        text = re.sub(r'^version:\s*["\']?[^"\'\n]+["\']?$', f'version: "{__version__}"', text, flags=re.MULTILINE)
    return text


def _write_plugin_files(plugin_dir: Path, *, force: bool) -> bool:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    changed = False
    for name in ("plugin.yaml", "__init__.py"):
        target = plugin_dir / name
        desired = _template_text(name)
        if target.exists() and target.read_text(encoding="utf-8") == desired:
            continue
        if target.exists() and not force:
            # Existing generated plugin from an older Kompressor version is OK to replace;
            # user-modified files require --force unless they include the install marker.
            existing = target.read_text(encoding="utf-8", errors="ignore")
            if "Kompressor" in existing or "kompressor" in existing:
                pass
            else:
                raise RuntimeError(f"refusing to overwrite non-Kompressor file: {target}")
        if target.exists():
            backup = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, backup)
        target.write_text(desired, encoding="utf-8")
        changed = True
    config = {
        "kompressor_version": __version__,
        "python_paths": list(_current_python_paths()),
        "kompressor_cli": _kompressor_cli(),
    }
    config_target = plugin_dir / "config.json"
    desired_config = json.dumps(config, indent=2, sort_keys=True) + "\n"
    if not config_target.exists() or config_target.read_text(encoding="utf-8") != desired_config:
        config_target.write_text(desired_config, encoding="utf-8")
        changed = True
    return changed


def _enable_plugin() -> dict[str, object]:
    hermes = _hermes_binary()
    if hermes is None:
        return {"changed": False, "ok": False, "message": "hermes executable not found"}
    before = PLUGIN_NAME in _enabled_plugin_names()
    proc = subprocess.run(
        [hermes, "plugins", "enable", PLUGIN_NAME],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    after = PLUGIN_NAME in _enabled_plugin_names()
    return {
        "changed": not before and after,
        "ok": after,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _disable_plugin() -> dict[str, object]:
    hermes = _hermes_binary()
    if hermes is None:
        return {"changed": False, "ok": False, "message": "hermes executable not found"}
    before = PLUGIN_NAME in _enabled_plugin_names()
    proc = subprocess.run(
        [hermes, "plugins", "disable", PLUGIN_NAME],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    after = PLUGIN_NAME in _enabled_plugin_names()
    return {
        "changed": before and not after,
        "ok": not after,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def install_hermes_integration(
    *,
    hermes_home_dir: Path | None = None,
    hermes_agent_dir: Path | None = None,
    force: bool = False,
    skip_enable: bool = False,
    skip_patch: bool = False,
) -> dict[str, object]:
    home = hermes_home(hermes_home_dir)
    plugin_dir = _plugin_dir(home)
    files_changed = _write_plugin_files(plugin_dir, force=force)
    enable = {"changed": False, "ok": True, "skipped": True}
    if not skip_enable:
        enable = _enable_plugin()
        if not enable.get("ok"):
            raise RuntimeError(f"failed to enable Hermes plugin: {enable}")
    patch = {"changed": False, "skipped": True, "message": "skipped"}
    if not skip_patch:
        patch = apply_codex_bridge_patch(hermes_agent_dir)
    status = get_hermes_install_status(hermes_home_dir, hermes_agent_dir)
    return {
        "changed": files_changed or bool(enable.get("changed")) or bool(patch.get("changed")),
        "plugin_files_changed": files_changed,
        "enable": enable,
        "patch": patch,
        "status": status.to_dict(),
        "message": "Kompressor Hermes integration installed",
    }


def uninstall_hermes_integration(
    *,
    hermes_home_dir: Path | None = None,
    hermes_agent_dir: Path | None = None,
    remove_patch: bool = False,
) -> dict[str, object]:
    home = hermes_home(hermes_home_dir)
    plugin_dir = _plugin_dir(home)
    disable = _disable_plugin()
    removed = False
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
        removed = True
    patch = {"changed": False, "skipped": True, "message": "patch removal not requested"}
    if remove_patch:
        patch = uninstall_codex_bridge_patch(hermes_agent_dir)
    status = get_hermes_install_status(hermes_home_dir, hermes_agent_dir)
    return {
        "changed": bool(disable.get("changed")) or removed or bool(patch.get("changed")),
        "disable": disable,
        "plugin_removed": removed,
        "patch": patch,
        "status": status.to_dict(),
        "message": "Kompressor Hermes integration uninstalled",
    }


def prove_hermes_integration(*, fixture: Path | None = None, threshold_chars: int = 256) -> dict[str, Any]:
    hermes = _hermes_binary()
    if hermes is None:
        raise RuntimeError("hermes executable not found")
    if fixture is None:
        fixture = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "logs.json"
    if fixture.exists():
        raw = fixture.read_text(encoding="utf-8")
    else:
        records = [
            {"id": i, "event": "auth_timeout_error", "severity": ["CRITICAL", "WARNING", "INFO"][i % 3]}
            for i in range(60)
        ]
        raw = json.dumps(records, indent=2)
    proof = Path(tempfile.gettempdir()) / f"kompressor-hermes-proof-{os.getpid()}.jsonl"
    proof.unlink(missing_ok=True)
    query = (
        "Kompressor install proof. Answer only with total record count and counts by severity from the raw JSON "
        "below. Use labels Total, CRITICAL, WARNING, INFO.\n\n" + raw
    )
    env = os.environ.copy()
    env["KOMPRESSOR_HERMES_PROOF_LOG"] = str(proof)
    env["KOMPRESSOR_HERMES_THRESHOLD_CHARS"] = str(threshold_chars)
    proc = subprocess.run(
        [hermes, "chat", "-Q", "-t", "safe", "-q", query],
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
        env=env,
    )
    events: list[dict[str, Any]] = []
    if proof.exists():
        events = [json.loads(line) for line in proof.read_text(encoding="utf-8").splitlines() if line.strip()]
    reversible_proof_strategies = {
        "json_table",
        "schema_rows",
        "meta_tokens",
        "token_lz",
        "separator_segments",
        "grammar",
        "path_dict_rows",
        "tree_dict",
    }
    compressed = [
        e
        for e in events
        if e.get("strategy") in reversible_proof_strategies
        and e.get("compressed_chars", 10**9) < e.get("original_chars", 0)
    ]
    output = proc.stdout + proc.stderr
    correct = all(label in output for label in ("Total", "CRITICAL", "WARNING", "INFO"))
    ok = proc.returncode == 0 and bool(compressed) and correct
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "proof_log": str(proof),
        "events": events,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "message": "new-session proof passed" if ok else "new-session proof failed",
    }
