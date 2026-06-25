from kompressor.codecs.pattern_hash import PatternHashCodec


def test_repeated_lines_compress_and_round_trip() -> None:
    text = "alpha repeated line\nalpha repeated line\nunique\nalpha repeated line"
    codec = PatternHashCodec()
    result = codec.compress(text)
    assert "@dict" in result.payload
    assert codec.decompress(result.payload, result.metadata) == text


def test_unique_lines_warn() -> None:
    result = PatternHashCodec().compress("one\ntwo\nthree")
    assert result.warnings
