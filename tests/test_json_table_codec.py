from hypothesis import given
from hypothesis import strategies as st

from kompressor.codecs.json_table import JsonTableCodec


def test_json_table_round_trip_with_escaping() -> None:
    rows = [{"a": "x|y", "b": "line\nbreak", "c": None}, {"a": "π", "d": 3}]
    codec = JsonTableCodec()
    result = codec.compress(rows)
    assert result.reversible
    assert codec.decompress(result.payload, result.metadata) == [
        {"a": "x|y", "b": "line\nbreak", "c": None, "d": None},
        {"a": "π", "b": None, "c": None, "d": 3},
    ]


json_rows = st.lists(
    st.dictionaries(
        st.text(min_size=1, max_size=5),
        st.one_of(st.text(), st.integers(), st.none()),
        min_size=1,
        max_size=4,
    ),
    min_size=1,
    max_size=5,
)


@given(json_rows)
def test_json_table_property_round_trip(rows):
    codec = JsonTableCodec()
    result = codec.compress(rows)
    restored = codec.decompress(result.payload, result.metadata)
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    expected = [{key: row.get(key, None) for key in keys} for row in rows]
    assert restored == expected
