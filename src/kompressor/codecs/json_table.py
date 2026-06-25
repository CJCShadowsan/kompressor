"""Reversible flat JSON table codec."""

from __future__ import annotations

import json
from typing import Any

from kompressor.codecs.base import Codec, CodecResult

MARKER = "<kompressor:json_table_v1>"
ESCAPE = "\\"
NULL = "∅"


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


class JsonTableCodec(Codec):
    name = "json_table"

    def __init__(self, delimiter_candidates: tuple[str, ...] = ("|", "\t", "¦", "~")) -> None:
        self.delimiter_candidates = delimiter_candidates

    def can_handle(self, value: object) -> bool:
        return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)

    def _keys(self, rows: list[dict[str, Any]]) -> list[str]:
        keys: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    keys.append(key)
                    seen.add(key)
        return keys

    def _choose_delimiter(self, rows: list[dict[str, Any]], keys: list[str]) -> str:
        text = "\n".join([*keys, *(str(row.get(k, "")) for row in rows for k in keys)])
        return min(self.delimiter_candidates, key=lambda candidate: text.count(candidate))

    def _escape(self, value: str, delimiter: str) -> str:
        return value.replace(ESCAPE, ESCAPE + ESCAPE).replace("\n", ESCAPE + "n").replace(delimiter, ESCAPE + delimiter)

    def _unescape(self, value: str, delimiter: str) -> str:
        output: list[str] = []
        i = 0
        while i < len(value):
            char = value[i]
            if char == ESCAPE and i + 1 < len(value):
                nxt = value[i + 1]
                output.append("\n" if nxt == "n" else nxt)
                i += 2
            else:
                output.append(char)
                i += 1
        return "".join(output)

    def _split(self, line: str, delimiter: str) -> list[str]:
        parts: list[str] = []
        current: list[str] = []
        escaped = False
        for char in line:
            if escaped:
                current.extend([ESCAPE, char])
                escaped = False
            elif char == ESCAPE:
                escaped = True
            elif char == delimiter:
                parts.append("".join(current))
                current = []
            else:
                current.append(char)
        if escaped:
            current.append(ESCAPE)
        parts.append("".join(current))
        return parts

    def _encode_value(self, value: object, delimiter: str) -> str:
        if value is None:
            return "n:"
        if isinstance(value, str):
            return "s:" + self._escape(value, delimiter)
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        return "j:" + self._escape(encoded, delimiter)

    def _decode_value(self, value: str, delimiter: str) -> object:
        if value.startswith("n:"):
            return None
        if value.startswith("s:"):
            return self._unescape(value[2:], delimiter)
        if value.startswith("j:"):
            return json.loads(self._unescape(value[2:], delimiter))
        raw = self._unescape(value, delimiter)
        if raw == NULL:
            return None
        return raw

    def compress(self, value: object) -> CodecResult:
        if not self.can_handle(value):
            raise TypeError("JsonTableCodec requires a non-empty list of dictionaries")
        rows = value  # type: ignore[assignment]
        assert isinstance(rows, list)
        dict_rows: list[dict[str, Any]] = rows  # type: ignore[assignment]
        warnings: list[str] = []
        if any(not _is_scalar(cell) for row in dict_rows for cell in row.values()):
            warnings.append("nested values are JSON-encoded inside table cells")
        keys = self._keys(dict_rows)
        delimiter = self._choose_delimiter(dict_rows, keys)
        lines = [MARKER + f' delimiter="{delimiter}" escape="{ESCAPE}" null="{NULL}"']
        lines.append(delimiter.join(self._escape(key, delimiter) for key in keys))
        for row in dict_rows:
            cells = [self._encode_value(row.get(key, None), delimiter) for key in keys]
            lines.append(delimiter.join(cells))
        return CodecResult(
            payload="\n".join(lines),
            reversible=True,
            metadata={"delimiter": delimiter, "keys": keys, "marker": MARKER},
            warnings=warnings,
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        delimiter = str(metadata.get("delimiter") or "|")
        lines = payload.split("\n")
        if lines and lines[0].startswith(MARKER):
            lines = lines[1:]
        if not lines:
            return []
        keys = [self._unescape(part, delimiter) for part in self._split(lines[0], delimiter)]
        rows: list[dict[str, object]] = []
        for line in lines[1:]:
            parts = self._split(line, delimiter)
            row: dict[str, object] = {}
            for key, value in zip(keys, parts, strict=False):
                row[key] = self._decode_value(value, delimiter)
            rows.append(row)
        return rows
