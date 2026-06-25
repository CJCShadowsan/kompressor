"""Safe binary handling."""

from __future__ import annotations

import base64

from kompressor.codecs.base import Codec, CodecResult

MARKER = "<kompressor:binary_v1>"


class BinaryCodec(Codec):
    name = "binary"

    def __init__(self, encoding: str | None = None, experimental_base122: bool = False) -> None:
        self.encoding = encoding
        self.experimental_base122 = experimental_base122

    def can_handle(self, value: object) -> bool:
        return isinstance(value, bytes)

    def compress(self, value: object) -> CodecResult:
        if not isinstance(value, bytes):
            raise TypeError("BinaryCodec requires bytes")
        if not self.encoding:
            return CodecResult(
                "",
                False,
                {"marker": MARKER},
                ["binary prompt compression is disabled by default; attach, extract, or summarize bytes"],
            )
        if self.encoding == "base85":
            payload = base64.b85encode(value).decode("ascii")
        elif self.encoding == "base64":
            payload = base64.b64encode(value).decode("ascii")
        elif self.encoding == "base122" and self.experimental_base122:
            payload = base64.b85encode(value).decode("ascii")
        else:
            raise ValueError("unsupported or disabled binary encoding")
        return CodecResult(f"{MARKER} encoding={self.encoding}\n{payload}", True, {"encoding": self.encoding}, [])

    def decompress(self, payload: str, metadata: dict[str, object]) -> object:
        encoding = metadata.get("encoding")
        body = payload.split("\n", 1)[1] if "\n" in payload else payload
        if encoding in {"base85", "base122"}:
            return base64.b85decode(body.encode("ascii"))
        if encoding == "base64":
            return base64.b64decode(body.encode("ascii"))
        raise ValueError("binary decompression requires encoding metadata")
