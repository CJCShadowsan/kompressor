# ruff: noqa: E501
from __future__ import annotations

import json

from kompressor.codecs import (
    GrammarCodec,
    MetaTokensCodec,
    PathDictRowsCodec,
    SeparatorSegmentsCodec,
    SessionDeltaCodec,
    SidecarRefCodec,
    TokenLzCodec,
    TreeDictCodec,
)
from kompressor.engine import KompressorEngine


def _roundtrip(codec, value):
    result = codec.compress(value)
    assert result.reversible
    assert codec.decompress(result.payload, result.metadata) == value
    return result


def test_meta_tokens_reversible() -> None:
    text = ("alpha beta gamma delta epsilon\n" * 80) + ("metadata namespace default service auth\n" * 80)
    result = _roundtrip(MetaTokensCodec(), text)
    assert result.payload.startswith("<kompressor:meta_tokens_v1>")
    assert len(result.payload) < len(text)


def test_token_lz_reversible() -> None:
    text = "".join(f"resource/{i % 5}/metadata/name/default namespace service account\n" for i in range(240))
    result = _roundtrip(TokenLzCodec(), text)
    assert result.payload.startswith("<kompressor:token_lz_v1>")


def test_separator_segments_reversible() -> None:
    paragraph = "kind: Deployment\nmetadata:\n  namespace: default\n  labels:\n    app: api"
    text = "\n\n".join([paragraph, "unique: 1", paragraph, paragraph, "unique: 2", paragraph])
    result = _roundtrip(SeparatorSegmentsCodec(), text)
    assert result.payload.startswith("<kompressor:separator_segments_v1>")


def test_grammar_reversible() -> None:
    text = "apiVersion kind metadata namespace default " * 200
    result = _roundtrip(GrammarCodec(), text)
    assert result.payload.startswith("<kompressor:grammar_v1>")


def test_path_dict_rows_reversible() -> None:
    value = {
        "items": [
            {"metadata": {"name": f"pod-{i}", "namespace": "default"}, "status": {"phase": "Running"}}
            for i in range(12)
        ]
    }
    result = _roundtrip(PathDictRowsCodec(), value)
    assert result.payload.startswith("<kompressor:path_dict_rows_v1>")


def test_tree_dict_reversible() -> None:
    subtree = {"limits": {"cpu": "1", "memory": "1Gi"}, "labels": {"managed-by": "kompressor"}}
    value = {"items": [{"name": f"svc-{i}", "template": subtree} for i in range(24)]}
    result = _roundtrip(TreeDictCodec(), value)
    assert result.payload.startswith("<kompressor:tree_dict_v1>")


def test_session_delta_reversible() -> None:
    base = "line 1\nline 2\nline 3\n"
    current = "line 1\nline changed\nline 3\nline 4\n"
    result = SessionDeltaCodec().compress({"base": base, "current": current})
    assert result.reversible
    assert SessionDeltaCodec().decompress(result.payload, result.metadata) == current


def test_sidecar_ref_reversible() -> None:
    text = "large payload\n" * 400
    result = SidecarRefCodec().compress(text)
    assert result.payload.startswith("<kompressor:sidecar_ref_v1>")
    assert SidecarRefCodec().decompress(result.payload, result.metadata) == text


def test_engine_can_decompress_research_reversible_codecs() -> None:
    engine = KompressorEngine()
    value = "repeated phrase alpha beta gamma delta " * 300
    result = engine.optimize(value)
    assert result.reversible
    assert result.kind in {"meta_tokens", "token_lz", "grammar", "sidecar_ref"}
    assert engine.decompress(result.optimized_payload, result.metadata) == value
    json.dumps(result.to_dict())
