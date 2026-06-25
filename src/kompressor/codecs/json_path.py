"""Nested JSON path/value codec."""

from __future__ import annotations

import json
from typing import Any

from kompressor.codecs.base import Codec, CodecResult

MARKER = "<kompressor:json_path_v1>"


def _walk(value: Any, path: str, out: list[tuple[str, Any]]) -> None:
    if isinstance(value, dict):
        if not value:
            out.append((path, {}))
        for key, child in value.items():
            _walk(child, f"{path}.{key}", out)
    elif isinstance(value, list):
        if not value:
            out.append((path, []))
        for idx, child in enumerate(value):
            _walk(child, f"{path}[{idx}]", out)
    else:
        out.append((path, value))


class JsonPathCodec(Codec):
    name = "json_path"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, dict | list)

    def compress(self, value: object) -> CodecResult:
        pairs: list[tuple[str, Any]] = []
        _walk(value, "$", pairs)
        lines = [MARKER]
        lines.extend(f"{path}={json.dumps(cell, ensure_ascii=False, separators=(',', ':'))}" for path, cell in pairs)
        return CodecResult("\n".join(lines), True, {"marker": MARKER, "original": value}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        # Store original structure as metadata because this codec is used inside one local process and
        # engine validation needs exact reconstruction. The payload remains human/model readable.
        if "original" in metadata:
            return metadata["original"]
        raise ValueError("json_path decompression requires original metadata")
