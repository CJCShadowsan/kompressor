"""Command-line interface for Kompressor."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import typer

from kompressor import __version__
from kompressor.anthropic_proxy import serve_anthropic_proxy
from kompressor.claude_code import (
    get_claude_code_status,
    install_claude_code_shims,
    prove_claude_code_shim,
    run_claude_code_proxy,
    run_claude_code_shim,
    uninstall_claude_code_shims,
)
from kompressor.codecs.json_table import MARKER as JSON_TABLE_MARKER
from kompressor.codecs.json_table import JsonTableCodec
from kompressor.engine import KompressorEngine
from kompressor.harnesses import get_harness_adapter
from kompressor.hermes_install import (
    get_hermes_install_status,
    install_hermes_integration,
    prove_hermes_integration,
    uninstall_hermes_integration,
)
from kompressor.hermes_patch import (
    apply_codex_bridge_patch,
    get_codex_bridge_status,
    uninstall_codex_bridge_patch,
)
from kompressor.plugins import available_plugins, get_plugin, plugin_manifests
from kompressor.proxy import healthz

app = typer.Typer(
    add_completion=False,
    help="Client-side LLM context optimization toolkit.",
    invoke_without_command=True,
    no_args_is_help=True,
)
plugin_app = typer.Typer(help="Inspect transparent harness plugins.", no_args_is_help=True)
hermes_app = typer.Typer(help="Manage explicit Hermes compatibility integrations.", no_args_is_help=True)
claude_code_app = typer.Typer(help="Manage Claude Code / claudish shim integrations.", no_args_is_help=True)
hermes_patch_app = typer.Typer(help="Manage reversible Hermes source compatibility patches.", no_args_is_help=True)
app.add_typer(plugin_app, name="plugin")
app.add_typer(hermes_app, name="hermes")
app.add_typer(claude_code_app, name="claude-code")
hermes_app.add_typer(hermes_patch_app, name="patch")


@app.callback()
def main(version: bool = typer.Option(False, "--version", help="Show version and exit.")) -> None:
    if version:
        typer.echo(f"kompressor {__version__}")
        raise typer.Exit()


def _load(path: Path) -> object:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return text


def _result_json(result) -> str:  # type: ignore[no-untyped-def]
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)


@app.command()
def status() -> None:
    """Show current implementation status."""
    typer.echo("Kompressor is installed and ready.")


@app.command()
def analyze(path: Path, json_output: bool = typer.Option(False, "--json")) -> None:
    """Analyze an input payload and report estimated savings."""
    result = KompressorEngine().optimize(_load(path))
    if json_output:
        typer.echo(_result_json(result))
        return
    stats = result.token_stats
    typer.echo(f"Input: {path}")
    typer.echo(f"Strategy: {result.kind}")
    typer.echo(f"Reversible: {'yes' if result.reversible else 'no'}")
    typer.echo(f"Baseline estimate: {stats.baseline_tokens_estimate:,} tokens")
    typer.echo(f"Optimized estimate: {stats.optimized_tokens_estimate:,} tokens")
    typer.echo(f"Estimated savings: {stats.percent_saved_estimate}%")
    typer.echo(f"Estimated input cost delta: ${stats.saved_cost_estimate_usd:.6f}")
    if result.warnings:
        typer.echo("Warnings: " + "; ".join(result.warnings))


@app.command()
def compress(
    path: Path,
    output: Path | None = typer.Option(None, "--output"),
    include_system_prompt: bool = typer.Option(False, "--include-system-prompt"),
    format_: str = typer.Option("payload", "--format"),
    harness: str = typer.Option("generic", "--harness"),
    task: str = typer.Option("", "--task"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compress an input payload for a target harness."""
    result = KompressorEngine().optimize(_load(path))
    selected_harness = harness
    if format_ in {"claude", "anthropic", "openai", "gemini", "hermes", "generic", "codex"}:
        selected_harness = format_
    if json_output:
        bundle = get_harness_adapter(selected_harness).package(result, task)
        text = json.dumps(bundle.data | {"harness": bundle.harness}, indent=2, ensure_ascii=False)
    elif include_system_prompt or format_ != "payload" or harness != "generic":
        text = get_harness_adapter(selected_harness).package(result, task).content
    else:
        text = result.optimized_payload
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        typer.echo(text)


@app.command()
def decompress(path: Path, compare_original: Path | None = typer.Option(None, "--compare-original")) -> None:
    """Decompress supported payload files and optionally compare to the original."""
    payload = path.read_text(encoding="utf-8")
    first_line = payload.split("\n", 1)[0]
    if first_line.startswith(JSON_TABLE_MARKER):
        delimiter = first_line.split('delimiter="', 1)[1].split('"', 1)[0]
        restored = JsonTableCodec((delimiter,)).decompress(payload, {"delimiter": delimiter})
    elif first_line.startswith("<kompressor:schema_rows_v1>"):
        from kompressor.codecs import SchemaRowsCodec

        restored = SchemaRowsCodec().decompress(payload, {"marker": "<kompressor:schema_rows_v1>"})
    else:
        raise typer.BadParameter("only json_table and schema_rows payload files are currently CLI-decompressible")
    if compare_original:
        original = _load(compare_original)
        if restored != original:
            raise typer.Exit(2)
        typer.echo("Round-trip comparison: PASS")
    else:
        typer.echo(json.dumps(restored, ensure_ascii=False, indent=2))


@app.command()
def bench(
    directory: Path,
    format_: str = typer.Option("markdown", "--format"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Benchmark all fixture files in a directory."""
    rows = []
    for path in sorted(p for p in directory.iterdir() if p.is_file()):
        result = KompressorEngine().optimize(_load(path))
        stats = result.token_stats
        rows.append(
            {
                "fixture": path.name,
                "strategy": result.kind,
                "reversible": result.reversible,
                "baseline_chars": stats.baseline_chars,
                "optimized_chars": stats.optimized_chars,
                "baseline_tokens": stats.baseline_tokens_estimate,
                "optimized_tokens": stats.optimized_tokens_estimate,
                "percent_saved": stats.percent_saved_estimate,
                "estimator": stats.estimator,
            }
        )
    if format_ == "json":
        text = json.dumps(rows, indent=2)
    elif format_ == "csv":
        import io

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
        text = buf.getvalue()
    else:
        header = "| fixture | strategy | reversible | percent_saved | estimator |"
        sep = "|---|---|---:|---:|---|"
        body = ["| {fixture} | {strategy} | {reversible} | {percent_saved} | {estimator} |".format(**r) for r in rows]
        text = "\n".join([header, sep, *body])
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        typer.echo(text)


@plugin_app.command("list")
def plugin_list(json_output: bool = typer.Option(False, "--json")) -> None:
    """List built-in transparent harness plugins."""
    manifests = plugin_manifests()
    if json_output:
        typer.echo(
            json.dumps(
                {name: manifest.__dict__ for name, manifest in manifests.items()},
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    for name in available_plugins():
        manifest = manifests[name]
        transparency = "transparent" if manifest.transparent else "manual"
        typer.echo(f"{name}\t{manifest.mode}\t{transparency}\t{manifest.entrypoint}")


@plugin_app.command("show")
def plugin_show(name: str, json_output: bool = typer.Option(False, "--json")) -> None:
    """Show installation and hook details for a harness plugin."""
    manifest = get_plugin(name).manifest
    if json_output:
        typer.echo(json.dumps(manifest.__dict__, indent=2, ensure_ascii=False))
        return
    typer.echo(f"Name: {manifest.name}")
    typer.echo(f"Harness: {manifest.harness}")
    typer.echo(f"Entrypoint: {manifest.entrypoint}")
    typer.echo(f"Mode: {manifest.mode}")
    typer.echo(f"Transparent: {'yes' if manifest.transparent else 'no'}")
    typer.echo("Hooks: " + ", ".join(manifest.hooks))
    typer.echo("Install hint: " + manifest.install_hint)
    if manifest.notes:
        typer.echo("Notes:")
        for note in manifest.notes:
            typer.echo(f"- {note}")


@plugin_app.command("preflight")
def plugin_preflight(
    name: str,
    path: Path,
    output: Path | None = typer.Option(None, "--output"),
    task: str = typer.Option("", "--task"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run a plugin pre-send hook over a file."""
    plugin = get_plugin(name)
    result = plugin.prepare_user_input(path.read_text(encoding="utf-8"), task=task)
    if json_output:
        text = json.dumps(
            {
                "plugin": plugin.manifest.name,
                "changed": result.changed,
                "warnings": result.warnings,
                "metadata": result.metadata,
                "content": result.content,
            },
            indent=2,
            ensure_ascii=False,
        )
    else:
        text = result.content
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        typer.echo(text)


def _parse_targets(target: str) -> tuple[str, ...]:
    if target == "both":
        return ("claude", "claudish")
    if target in {"claude", "claudish"}:
        return (target,)
    raise typer.BadParameter("target must be one of: claude, claudish, both")


def _echo_claude_code_status(status: dict[str, object]) -> None:
    typer.echo("Kompressor:")
    typer.echo(f"  version: {status.get('kompressor_version')}")
    typer.echo("Binaries:")
    typer.echo(f"  claude: {status.get('claude_binary')}")
    typer.echo(f"  claudish: {status.get('claudish_binary')}")
    typer.echo("Shims:")
    typer.echo(f"  bin_dir: {status.get('bin_dir')}")
    claude_installed = "yes" if status.get("claude_shim_installed") else "no"
    claudish_installed = "yes" if status.get("claudish_shim_installed") else "no"
    claude_proxy_installed = "yes" if status.get("claude_proxy_shim_installed") else "no"
    claudish_proxy_installed = "yes" if status.get("claudish_proxy_shim_installed") else "no"
    typer.echo(f"  kompressor-claude: {status.get('claude_shim')} installed={claude_installed}")
    typer.echo(f"  kompressor-claudish: {status.get('claudish_shim')} installed={claudish_installed}")
    typer.echo(f"  kompressor-claude-proxy: {status.get('claude_proxy_shim')} installed={claude_proxy_installed}")
    typer.echo(f"  kompressor-claudish-proxy: {status.get('claudish_proxy_shim')} installed={claudish_proxy_installed}")
    findings = status.get("native_hook_findings") if isinstance(status.get("native_hook_findings"), dict) else {}
    typer.echo("Native Claude Code hooks:")
    typer.echo(f"  recommended_mode: {findings.get('recommended_mode')}")
    typer.echo(f"  prompt_replacement_supported: {'yes' if findings.get('prompt_replacement_supported') else 'no'}")
    typer.echo(f"  reason: {findings.get('reason')}")


@claude_code_app.command("status")
def claude_code_status(
    bin_dir: Path | None = typer.Option(None, "--bin-dir"),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show Claude Code / claudish shim status and native-hook findings."""
    status = get_claude_code_status(bin_dir, config_dir).to_dict()
    if json_output:
        typer.echo(json.dumps({"status": status}, indent=2, ensure_ascii=False))
    else:
        _echo_claude_code_status(status)


@claude_code_app.command("install")
def claude_code_install(
    bin_dir: Path | None = typer.Option(None, "--bin-dir"),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
    target: str = typer.Option("both", "--target", help="claude, claudish, or both"),
    mode: str = typer.Option("shim", "--mode", help="shim or proxy"),
    port: int = typer.Option(8765, "--port", help="Proxy port for --mode proxy wrappers."),
    force: bool = typer.Option(False, "--force"),
    prove: bool = typer.Option(False, "--prove"),
    live: bool = typer.Option(
        False,
        "--live",
        help="With --prove, invoke claude/claudish instead of structural proof only.",
    ),
    model: str | None = typer.Option(None, "--model", help="Model for claudish live proof, e.g. ollama@qwen2.5:3b."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Install one-shot prompt-rewriting or Anthropic proxy shims for Claude Code and/or claudish."""
    if mode not in {"shim", "proxy"}:
        raise typer.BadParameter("mode must be shim or proxy")
    try:
        payload = install_claude_code_shims(
            bin_dir=bin_dir,
            config_dir=config_dir,
            targets=_parse_targets(target),  # type: ignore[arg-type]
            force=force,
            mode=mode,
            port=port,
        )
        proof_target = "claudish" if target in {"both", "claudish"} else "claude"
        proof_payload = prove_claude_code_shim(target=proof_target, model=model, live=live) if prove else None
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps({**payload, "proof": proof_payload}, indent=2, ensure_ascii=False))
        return
    typer.echo(str(payload.get("message")))
    for path in payload.get("installed", []):
        typer.echo(f"  {path}")
    _echo_claude_code_status(payload["status"])  # type: ignore[arg-type]
    if proof_payload:
        typer.echo("Proof:")
        typer.echo(json.dumps(proof_payload, indent=2, ensure_ascii=False))
        if not proof_payload.get("ok"):
            raise typer.Exit(2)


@claude_code_app.command("uninstall")
def claude_code_uninstall(
    bin_dir: Path | None = typer.Option(None, "--bin-dir"),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
    target: str = typer.Option("both", "--target", help="claude, claudish, or both"),
    mode: str = typer.Option("all", "--mode", help="shim, proxy, or all"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Remove Kompressor-managed Claude Code / claudish shims."""
    payload = uninstall_claude_code_shims(
        bin_dir=bin_dir,
        config_dir=config_dir,
        targets=_parse_targets(target),  # type: ignore[arg-type]
        mode=mode,
    )
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(str(payload.get("message")))
    for path in payload.get("removed", []):
        typer.echo(f"  {path}")


@claude_code_app.command("run")
def claude_code_run(
    context: Path,
    target: str = typer.Option("claudish", "--target", help="claude or claudish"),
    task: str = typer.Option("", "--task"),
    model: str | None = typer.Option(None, "--model", help="Model for claudish, e.g. ollama@qwen2.5:3b."),
    command: str | None = typer.Option(None, "--command", help="Override binary path for claude or claudish."),
    output: Path | None = typer.Option(None, "--output", help="Write generated compressed prompt before invocation."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print generated command/prompt without invoking Claude Code.",
    ),
    allow_tools: bool = typer.Option(False, "--allow-tools", help="For claude target, do not force --tools ''."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compress a context file, then invoke claude or claudish with compressed stdin."""
    if target not in {"claude", "claudish"}:
        raise typer.BadParameter("target must be claude or claudish")
    payload = run_claude_code_shim(
        context,
        target=target,  # type: ignore[arg-type]
        task=task,
        model=model,
        command=command,
        output=output,
        dry_run=dry_run,
        allow_tools=allow_tools,
    )
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if dry_run:
        typer.echo("Command: " + " ".join(str(part) for part in payload.get("command", [])))
        typer.echo(str(payload.get("prompt", "")))
        return
    if payload.get("stdout"):
        typer.echo(str(payload["stdout"]).rstrip())
    if payload.get("stderr"):
        typer.echo(str(payload["stderr"]).rstrip(), err=True)
    if not payload.get("ok"):
        raise typer.Exit(int(payload.get("returncode") or 1))


@claude_code_app.command("proxy")
def claude_code_proxy(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    upstream: str = typer.Option("https://api.anthropic.com", "--upstream"),
    api_key: str | None = typer.Option(None, "--api-key"),
    threshold_chars: int = typer.Option(512, "--threshold-chars"),
    allow_sensitive: bool = typer.Option(False, "--allow-sensitive"),
    redact: bool = typer.Option(False, "--redact"),
) -> None:
    """Serve an Anthropic-compatible request-rewriting proxy for Claude Code."""
    typer.echo(f"Serving Kompressor Anthropic proxy on http://{host}:{port} -> {upstream}", err=True)
    serve_anthropic_proxy(
        host=host,
        port=port,
        upstream=upstream,
        api_key=api_key,
        threshold_chars=threshold_chars,
        allow_sensitive=allow_sensitive,
        redact=redact,
    )


@claude_code_app.command("run-proxy", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def claude_code_run_proxy(
    ctx: typer.Context,
    target: str = typer.Option("claude", "--target", help="claude or claudish"),
    port: int = typer.Option(8765, "--port"),
    upstream: str = typer.Option("https://api.anthropic.com", "--upstream"),
    model: str | None = typer.Option(None, "--model", help="Model for claudish."),
    command: str | None = typer.Option(None, "--command", help="Override binary path for claude or claudish."),
    allow_tools: bool = typer.Option(False, "--allow-tools", help="For claude target, do not force --tools ''."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Start the proxy, route Claude Code through it, then stop the proxy."""
    if target not in {"claude", "claudish"}:
        raise typer.BadParameter("target must be claude or claudish")
    payload = run_claude_code_proxy(
        target=target,  # type: ignore[arg-type]
        port=port,
        upstream=upstream,
        model=model,
        command=command,
        allow_tools=allow_tools,
        args=tuple(ctx.args),
    )
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if payload.get("stdout"):
        typer.echo(str(payload["stdout"]).rstrip())
    if payload.get("stderr"):
        typer.echo(str(payload["stderr"]).rstrip(), err=True)
    if not payload.get("ok"):
        raise typer.Exit(int(payload.get("returncode") or 1))


@claude_code_app.command("prove")
def claude_code_prove(
    target: str = typer.Option("claudish", "--target", help="claude or claudish"),
    model: str | None = typer.Option(None, "--model", help="Model for claudish live proof, e.g. ollama@qwen2.5:3b."),
    command: str | None = typer.Option(None, "--command", help="Override binary path for claude or claudish."),
    live: bool = typer.Option(False, "--live", help="Invoke claude/claudish and compare the answer to the oracle."),
    allow_tools: bool = typer.Option(False, "--allow-tools", help="For claude target, do not force --tools ''."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Prove Claude Code shim prompt generation, optionally with a live claude/claudish call."""
    if target not in {"claude", "claudish"}:
        raise typer.BadParameter("target must be claude or claudish")
    payload = prove_claude_code_shim(
        target=target,  # type: ignore[arg-type]
        model=model,
        command=command,
        live=live,
        allow_tools=allow_tools,
    )
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        typer.echo(str(payload.get("message")))
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    if not payload.get("ok"):
        raise typer.Exit(2)


def _echo_patch_result(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    status = payload.get("status")
    if isinstance(status, dict):
        typer.echo(f"Target: {status.get('target_file')}")
        typer.echo(f"Bridge present: {'yes' if status.get('bridge_present') else 'no'}")
        typer.echo(f"Managed patch: {'yes' if status.get('marker_present') else 'no'}")
        typer.echo(f"Patch needed: {'yes' if status.get('patch_needed') else 'no'}")
        typer.echo(f"Can apply: {'yes' if status.get('can_apply') else 'no'}")
        typer.echo(f"Can uninstall: {'yes' if status.get('can_uninstall') else 'no'}")
        typer.echo(f"Reason: {status.get('reason')}")
    if "changed" in payload:
        typer.echo(f"Changed: {'yes' if payload.get('changed') else 'no'}")
    if payload.get("backup"):
        typer.echo(f"Backup: {payload['backup']}")
    if payload.get("message"):
        typer.echo(str(payload["message"]))


def _echo_hermes_status(status: dict[str, object]) -> None:
    patch = status.get("patch_status") if isinstance(status.get("patch_status"), dict) else {}
    typer.echo("Kompressor:")
    typer.echo(f"  version: {status.get('kompressor_version')}")
    typer.echo(f"  cli: {status.get('kompressor_cli')}")
    typer.echo("Hermes:")
    typer.echo(f"  binary: {status.get('hermes_binary')}")
    typer.echo(f"  home: {status.get('hermes_home')}")
    typer.echo("Plugin:")
    typer.echo(f"  path: {status.get('plugin_dir')}")
    typer.echo(f"  installed: {'yes' if status.get('plugin_installed') else 'no'}")
    typer.echo(f"  enabled: {'yes' if status.get('plugin_enabled') else 'no'}")
    typer.echo(f"  version: {status.get('plugin_version')}")
    typer.echo("Codex bridge:")
    typer.echo(f"  target: {patch.get('target_file')}")
    typer.echo(f"  present: {'yes' if patch.get('bridge_present') else 'no'}")
    typer.echo(f"  patch_needed: {'yes' if patch.get('patch_needed') else 'no'}")
    typer.echo(f"  reason: {patch.get('reason')}")


@hermes_app.command("status")
def hermes_status(
    hermes_home_dir: Path | None = typer.Option(None, "--hermes-home"),
    hermes_agent_dir: Path | None = typer.Option(None, "--hermes-agent-dir"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show Kompressor's Hermes plugin, enablement, and patch status."""
    status = get_hermes_install_status(hermes_home_dir, hermes_agent_dir).to_dict()
    if json_output:
        typer.echo(json.dumps({"status": status}, indent=2, ensure_ascii=False))
    else:
        _echo_hermes_status(status)


@hermes_app.command("install")
def hermes_install(
    hermes_home_dir: Path | None = typer.Option(None, "--hermes-home"),
    hermes_agent_dir: Path | None = typer.Option(None, "--hermes-agent-dir"),
    force: bool = typer.Option(False, "--force"),
    prove: bool = typer.Option(False, "--prove"),
    skip_patch: bool = typer.Option(False, "--skip-patch"),
    skip_enable: bool = typer.Option(False, "--skip-enable"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Install and enable Kompressor's native Hermes plugin."""
    try:
        payload = install_hermes_integration(
            hermes_home_dir=hermes_home_dir,
            hermes_agent_dir=hermes_agent_dir,
            force=force,
            skip_enable=skip_enable,
            skip_patch=skip_patch,
        )
        proof_payload = prove_hermes_integration() if prove else None
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps({**payload, "proof": proof_payload}, indent=2, ensure_ascii=False))
        return
    typer.echo(str(payload.get("message")))
    _echo_hermes_status(payload["status"])  # type: ignore[arg-type]
    if proof_payload:
        typer.echo("Proof:")
        typer.echo(f"  ok: {'yes' if proof_payload.get('ok') else 'no'}")
        typer.echo(f"  proof_log: {proof_payload.get('proof_log')}")
        events = proof_payload.get("events")
        if isinstance(events, list) and events:
            event = events[0]
            typer.echo(f"  strategy: {event.get('strategy')}")
            typer.echo(f"  original_chars: {event.get('original_chars')}")
            typer.echo(f"  compressed_chars: {event.get('compressed_chars')}")
            typer.echo(f"  saved_chars: {event.get('saved_chars')}")
        if not proof_payload.get("ok"):
            raise typer.Exit(2)


@hermes_app.command("uninstall")
def hermes_uninstall(
    hermes_home_dir: Path | None = typer.Option(None, "--hermes-home"),
    hermes_agent_dir: Path | None = typer.Option(None, "--hermes-agent-dir"),
    remove_patch: bool = typer.Option(False, "--remove-patch"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Disable and remove Kompressor's Hermes plugin."""
    try:
        payload = uninstall_hermes_integration(
            hermes_home_dir=hermes_home_dir,
            hermes_agent_dir=hermes_agent_dir,
            remove_patch=remove_patch,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(str(payload.get("message")))
    _echo_hermes_status(payload["status"])  # type: ignore[arg-type]


@hermes_app.command("prove")
def hermes_prove(json_output: bool = typer.Option(False, "--json")) -> None:
    """Run a new-session proof that Hermes is compressing raw structured input."""
    try:
        payload = prove_hermes_integration()
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(str(payload.get("message")))
    typer.echo(f"proof_log: {payload.get('proof_log')}")
    events = payload.get("events")
    if isinstance(events, list) and events:
        typer.echo(json.dumps(events[0], indent=2, ensure_ascii=False))
    if not payload.get("ok"):
        raise typer.Exit(2)


@hermes_patch_app.command("status")
def hermes_patch_status(
    hermes_agent_dir: Path | None = typer.Option(None, "--hermes-agent-dir"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Report whether the Hermes Codex middleware bridge patch is needed."""
    status = get_codex_bridge_status(hermes_agent_dir)
    _echo_patch_result({"status": status.to_dict()}, json_output=json_output)


@hermes_patch_app.command("apply")
def hermes_patch_apply(
    hermes_agent_dir: Path | None = typer.Option(None, "--hermes-agent-dir"),
    force: bool = typer.Option(False, "--force", help="Reserved for future known-shape patches; never guesses."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Explicitly apply the reversible Hermes Codex middleware bridge patch."""
    try:
        payload = apply_codex_bridge_patch(hermes_agent_dir, force=force)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _echo_patch_result(payload, json_output=json_output)


@hermes_patch_app.command("uninstall")
def hermes_patch_uninstall(
    hermes_agent_dir: Path | None = typer.Option(None, "--hermes-agent-dir"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Remove the Kompressor-managed Hermes Codex middleware bridge patch."""
    try:
        payload = uninstall_codex_bridge_patch(hermes_agent_dir)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _echo_patch_result(payload, json_output=json_output)


@hermes_patch_app.command("prove")
def hermes_patch_prove() -> None:
    """Print a proof recipe for native Hermes compression after applying the patch."""
    typer.echo(
        "Run:\n"
        "  export KOMPRESSOR_HERMES_PROOF_LOG=/tmp/kompressor-hermes-native-proof.jsonl\n"
        '  query="Answer with total count and severity counts from this raw JSON:\\n\\n'
        '$(cat tests/fixtures/logs.json)"\n'
        '  hermes chat -Q -t safe -q "$query"\n'
        "Then verify /tmp/kompressor-hermes-native-proof.jsonl contains strategy=json_table "
        "and compressed_chars < original_chars."
    )


@app.command()
def proxy(
    dry_run: bool = typer.Option(True, "--dry-run/--forward"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Show proxy readiness. Network forwarding is implemented through proxy helpers."""
    typer.echo(json.dumps({"health": healthz(), "dry_run": dry_run, "port": port}))
