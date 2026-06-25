"""Compression codecs."""

from kompressor.codecs.base import Codec, CodecResult
from kompressor.codecs.binary import BinaryCodec
from kompressor.codecs.json_path import JsonPathCodec
from kompressor.codecs.json_table import JsonTableCodec
from kompressor.codecs.pattern_hash import PatternHashCodec
from kompressor.codecs.xml_path import XmlPathCodec

__all__ = [
    "BinaryCodec",
    "Codec",
    "CodecResult",
    "JsonPathCodec",
    "JsonTableCodec",
    "PatternHashCodec",
    "XmlPathCodec",
]
