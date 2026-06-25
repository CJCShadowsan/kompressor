from typer.testing import CliRunner

from kompressor.cli import app

runner = CliRunner()


def test_analyze_json_fixture() -> None:
    result = runner.invoke(app, ["analyze", "tests/fixtures/logs.json"])
    assert result.exit_code == 0
    assert "Strategy:" in result.output


def test_compress_claude_compat_format() -> None:
    result = runner.invoke(
        app,
        ["compress", "tests/fixtures/logs.json", "--format", "claude", "--include-system-prompt"],
    )
    assert result.exit_code == 0
    assert "SYSTEM:" in result.output
    assert "PAYLOAD:" in result.output


def test_compress_hermes_harness() -> None:
    result = runner.invoke(app, ["compress", "tests/fixtures/logs.json", "--harness", "hermes"])
    assert result.exit_code == 0
    assert "Hermes" in result.output
    assert "KOMPRESSOR_PAYLOAD" in result.output


def test_compress_openai_json_harness() -> None:
    result = runner.invoke(app, ["compress", "tests/fixtures/logs.json", "--harness", "openai", "--json"])
    assert result.exit_code == 0
    assert "developer" in result.output


def test_compress_codex_harness() -> None:
    result = runner.invoke(app, ["compress", "tests/fixtures/logs.json", "--harness", "codex"])
    assert result.exit_code == 0
    assert "CODEX_INPUT" in result.output


def test_plugin_list_includes_all_harnesses() -> None:
    result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    for name in ["generic", "claude", "openai", "gemini", "hermes", "codex"]:
        assert name in result.output


def test_plugin_show_hermes() -> None:
    result = runner.invoke(app, ["plugin", "show", "hermes"])
    assert result.exit_code == 0
    assert "kompressor-hermes" in result.output
    assert "pre_tool_result" in result.output


def test_plugin_preflight() -> None:
    result = runner.invoke(app, ["plugin", "preflight", "hermes", "tests/fixtures/logs.json", "--task", "Find auth"])
    assert result.exit_code == 0
    assert "KOMPRESSOR_PAYLOAD" in result.output
    assert "Find auth" in result.output


def test_bench_json() -> None:
    result = runner.invoke(app, ["bench", "tests/fixtures", "--format", "json"])
    assert result.exit_code == 0
    assert "logs.json" in result.output


def test_decompress_compare_original(tmp_path) -> None:
    compressed = tmp_path / "logs.kompressed.txt"
    compress_result = runner.invoke(
        app,
        ["compress", "tests/fixtures/logs.json", "--output", str(compressed)],
    )
    assert compress_result.exit_code == 0
    result = runner.invoke(
        app,
        ["decompress", str(compressed), "--compare-original", "tests/fixtures/logs.json"],
    )
    assert result.exit_code == 0
    assert "PASS" in result.output
