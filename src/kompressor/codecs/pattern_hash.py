"""Repeating pattern dictionary codec."""

from __future__ import annotations

from collections import Counter

from kompressor.codecs.base import Codec, CodecResult

MARKER = "<kompressor:pattern_hash_v1>"


class PatternHashCodec(Codec):
    name = "pattern_hash"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, str) and "\n" in value

    def compress(self, value: object) -> CodecResult:
        if not isinstance(value, str):
            raise TypeError("PatternHashCodec requires text")
        lines = value.splitlines()
        counts = Counter(lines)
        repeated = [line for line, count in counts.items() if count > 1 and len(line) > 8]
        if not repeated:
            return CodecResult(value, True, {"marker": MARKER, "dictionary": {}}, ["no repeated lines"])
        dictionary = {line: f"#{idx}" for idx, line in enumerate(repeated)}
        out = [MARKER, "@dict"]
        for line, ident in dictionary.items():
            out.append(f"{ident}={line}")
        out.append("@rows")
        out.extend(dictionary.get(line, line) for line in lines)
        payload = "\n".join(out)
        return CodecResult(payload, True, {"marker": MARKER, "dictionary": dictionary}, [])

    def decompress(self, payload: str, metadata: dict[str, object]) -> object:
        dictionary = metadata.get("dictionary", {})
        if not isinstance(dictionary, dict):
            dictionary = {}
        reverse = {ident: line for line, ident in dictionary.items()}
        lines = payload.splitlines()
        try:
            start = lines.index("@rows") + 1
        except ValueError:
            return payload
        return "\n".join(str(reverse.get(line, line)) for line in lines[start:])
