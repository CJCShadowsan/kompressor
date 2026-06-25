"""XML path/value codec."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from kompressor.codecs.base import Codec, CodecResult

MARKER = "<kompressor:xml_path_v1>"


class XmlPathCodec(Codec):
    name = "xml_path"

    def can_handle(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        text = value.lstrip()
        return text.startswith("<") and text.endswith(">")

    def compress(self, value: object) -> CodecResult:
        if not isinstance(value, str):
            raise TypeError("XmlPathCodec requires XML text")
        root = ET.fromstring(value)
        lines = [MARKER]

        def walk(elem: ET.Element, path: str) -> None:
            for key, attr in sorted(elem.attrib.items()):
                lines.append(f"{path}/@{key}={attr}")
            text = (elem.text or "").strip()
            if text:
                lines.append(f"{path}/text()={text}")
            counts: dict[str, int] = {}
            for child in list(elem):
                idx = counts.get(child.tag, 0)
                counts[child.tag] = idx + 1
                walk(child, f"{path}/{child.tag}[{idx}]")

        walk(root, f"/{root.tag}[0]")
        return CodecResult("\n".join(lines), True, {"marker": MARKER, "original": value}, [])

    def decompress(self, payload: str, metadata: dict[str, object]) -> object:
        if "original" in metadata:
            return metadata["original"]
        raise ValueError("xml_path decompression requires original metadata")
