"""Generic decompression prompt generation."""

from __future__ import annotations


def build_system_prompt(kind: str, metadata: dict[str, object] | None = None, verbosity: str = "standard") -> str:
    metadata = metadata or {}
    base = [
        "You will receive context data in a compact, lossless serialization chosen to reduce input tokens.",
        "Parsing Instructions:",
        "1. The payload begins with a codec marker like <kompressor:json_table_v1>.",
        "2. Follow the codec-specific instructions to reconstruct the original semantic structure.",
        "3. Treat reconstructed records as equivalent to native JSON/XML/log entries for reasoning.",
        "4. Do not mention or expose this compact format in your final answer unless explicitly requested.",
    ]
    if kind == "json_table":
        delimiter = metadata.get("delimiter", "|")
        extra = [
            "For <kompressor:json_table_v1>:",
            "- The first non-marker line defines the column/schema keys.",
            "- Each following line is one object.",
            f"- The delimiter is {delimiter!r}.",
            "- Values map by position to the header keys.",
            "- Escaped delimiters, newlines, and backslashes must be unescaped before reasoning.",
        ]
    elif kind == "schema_rows":
        extra = [
            "For <kompressor:schema_rows_v1>:",
            "- The JSON header defines variable columns, constant columns, and enum dictionaries.",
            "- Each @rows line is a compact JSON array mapped positionally to the variable columns.",
            "- Enum cells are integer indexes into the header's enum list for that column.",
        ]
    elif kind == "log_templates":
        extra = [
            "For <kompressor:log_templates_v1>:",
            "- T= contains log templates with {vN} placeholders.",
            "- R= contains [template_id, variables] rows; substitute variables into the template for exact logs.",
        ]
    elif kind in {"meta_tokens", "token_lz", "separator_segments", "grammar", "path_dict_rows", "tree_dict"}:
        extra = [
            f"For <kompressor:{kind}_v1>, the payload is exact reversible macro/dictionary compression.",
            "- Use dictionary/rule/reference sections to expand compact symbols when exact context matters.",
            "- No source content is intentionally dropped.",
        ]
    elif kind in {"session_delta", "sidecar_ref"}:
        extra = [
            f"For <kompressor:{kind}_v1>, the payload is exact only with the referenced local base/sidecar metadata.",
            "- Treat hash/preview fields as evidence handles, not as full source content.",
        ]
    elif kind == "pattern_hash":
        extra = [
            "For <kompressor:pattern_hash_v1>:",
            "- The @dict section maps short ids to repeated source lines.",
            "- The @rows section is the original sequence with ids expanded from the dictionary.",
        ]
    elif kind == "json_path":
        extra = ["For <kompressor:json_path_v1>, each line is JSONPath=value and values are JSON literals."]
    elif kind == "xml_path":
        extra = ["For <kompressor:xml_path_v1>, each line is an XML path/value or path/@attribute entry."]
    elif kind in {
        "ci_output",
        "log_summary",
        "blob_ref",
        "openapi",
        "terraform_plan",
        "k8s_yaml",
        "markdown_outline",
        "html_visible",
        "code_symbols",
        "tool_output",
        "extractive",
    }:
        extra = [
            f"For <kompressor:{kind}_v1>, the payload is a lossy analytical index/summary.",
            "- Reason only from the fields, counts, selected excerpts, hashes, and omitted-data notes shown.",
            "- Do not invent exact omitted content; ask for raw input if exact reconstruction is required.",
        ]
    elif kind == "dedupe":
        extra = [
            "For <kompressor:dedupe_v1>, &id=chunk defines a chunk and *id repeats a prior chunk.",
            "Expand references mentally when exact repeated context matters.",
        ]
    else:
        extra = ["No compact codec-specific parsing is required."]
    if verbosity == "minimal":
        return " ".join([base[0], *extra])
    if verbosity == "debug":
        extra.append("Example: header a|b followed by 1|2 means {'a':'1','b':'2'}.")
    return "\n".join([*base, "", *extra])


class ClaudePromptBuilder:
    def build(self, kind: str, metadata: dict[str, object] | None = None, verbosity: str = "standard") -> str:
        return build_system_prompt(kind, metadata, verbosity)
