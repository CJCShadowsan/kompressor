from kompressor.codecs.json_path import JsonPathCodec


def test_json_path_round_trip_nested_metadata() -> None:
    value = {"users": [{"id": "u1", "roles": ["admin"]}], "ok": True}
    codec = JsonPathCodec()
    result = codec.compress(value)
    assert "$.users[0].id" in result.payload
    assert codec.decompress(result.payload, result.metadata) == value
