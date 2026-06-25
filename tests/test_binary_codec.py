from kompressor.codecs.binary import BinaryCodec


def test_binary_disabled_by_default() -> None:
    result = BinaryCodec().compress(b"abc")
    assert not result.reversible
    assert "disabled" in result.warnings[0]


def test_binary_base64_round_trip() -> None:
    codec = BinaryCodec("base64")
    result = codec.compress(b"abc")
    assert codec.decompress(result.payload, result.metadata) == b"abc"
