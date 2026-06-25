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
