from kompressor.prompts import build_system_prompt


def test_json_table_prompt_contains_contract() -> None:
    prompt = build_system_prompt("json_table", {"delimiter": "|"})
    assert "<kompressor:json_table_v1>" in prompt
    assert "header" in prompt
    assert "delimiter" in prompt


def test_prompt_verbosity() -> None:
    minimal = build_system_prompt("json_table", verbosity="minimal")
    debug = build_system_prompt("json_table", verbosity="debug")
    assert len(minimal) < len(debug)
