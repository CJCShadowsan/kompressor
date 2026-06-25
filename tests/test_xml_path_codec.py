from kompressor.codecs.xml_path import XmlPathCodec


def test_xml_path_round_trip_metadata() -> None:
    xml = '<root><server id="s1"><ip>10.0.1.250</ip></server></root>'
    codec = XmlPathCodec()
    result = codec.compress(xml)
    assert "/root[0]/server[0]/@id=s1" in result.payload
    assert codec.decompress(result.payload, result.metadata) == xml
