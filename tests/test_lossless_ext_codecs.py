from __future__ import annotations

from kompressor.codecs import (
    AtomDictCodec,
    ChunkStoreCodec,
    CodeTokensCodec,
    DomainTableCodec,
    ShapeRowsCodec,
    XmlShapeRowsCodec,
)
from kompressor.engine import KompressorEngine
from kompressor.models import KompressorConfig


def _roundtrip(codec, value):
    result = codec.compress(value)
    assert result.reversible
    assert codec.decompress(result.payload, result.metadata) == value
    return result


def test_shape_rows_roundtrips_dict_of_dicts() -> None:
    value = {
        "cluster": "c1",
        "services": {
            f"svc-{i}": {
                "metadata": {"name": f"svc-{i}", "namespace": "default"},
                "spec": {"replicas": i, "image": f"registry.example.com/svc:{i}"},
            }
            for i in range(8)
        },
    }
    result = _roundtrip(ShapeRowsCodec(), value)
    assert result.payload.startswith("<kompressor:shape_rows_v1>")
    assert len(result.payload) < len(str(value))


def test_atom_dict_roundtrips_repeated_strings() -> None:
    value = {
        "items": [
            {"kind": "Deployment", "namespace": "default", "image": "registry.example.com/api:latest"}
            for _ in range(16)
        ]
    }
    result = _roundtrip(AtomDictCodec(), value)
    assert result.payload.startswith("<kompressor:atom_dict_v1>")


def test_xml_shape_rows_roundtrips_repeated_xml() -> None:
    value = "<root>" + "".join(
        f'<item kind="pod"><name>pod-{i}</name><ns>default</ns></item>' for i in range(8)
    ) + "</root>"
    result = _roundtrip(XmlShapeRowsCodec(), value)
    assert result.payload.startswith("<kompressor:xml_shape_rows_v1>")


def test_transport_deflate_is_explicitly_gated() -> None:
    value = {"items": [{"id": i, "payload": "same-value" * 20} for i in range(20)]}
    default = KompressorEngine().optimize(value)
    assert default.kind != "transport_deflate"
    config = KompressorConfig(enable_transport_compression=True, reversible_only=True)
    enabled = KompressorEngine(config).optimize(value)
    assert enabled.kind == "transport_deflate"
    assert KompressorEngine(config).decompress(enabled.optimized_payload, enabled.metadata) == value


def test_chunk_store_roundtrips_repeated_blocks() -> None:
    text = ("alpha beta gamma\n\n" * 40) + "unique block\n\n" + ("alpha beta gamma\n\n" * 40)
    result = _roundtrip(ChunkStoreCodec(), text)
    assert result.payload.startswith("<kompressor:chunk_store_v1>")


def test_code_tokens_roundtrips_python_source() -> None:
    code = "import os\n\n" + "\n".join(f"def f{i}():\n    return {i}" for i in range(30))
    result = _roundtrip(CodeTokensCodec(), code)
    assert result.payload.startswith("<kompressor:code_tokens_v1>")


def test_domain_table_roundtrips_openapi_with_embedded_deflate() -> None:
    spec = {"openapi": "3.1.0", "paths": {f"/x/{i}": {"get": {"responses": {"200": {}}}} for i in range(20)}}
    result = _roundtrip(DomainTableCodec(), spec)
    assert result.payload.startswith("<kompressor:domain_table_v1>")
