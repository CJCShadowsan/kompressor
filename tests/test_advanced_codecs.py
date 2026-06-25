# ruff: noqa: E501
from __future__ import annotations

import base64
import json

from kompressor.codecs import (
    BlobRefCodec,
    CiOutputCodec,
    CodeSymbolsCodec,
    HtmlVisibleCodec,
    K8sYamlCodec,
    LogTemplatesCodec,
    MarkdownOutlineCodec,
    OpenApiCodec,
    TerraformPlanCodec,
    ToolOutputCodec,
)
from kompressor.engine import KompressorEngine


def test_schema_rows_reversible_and_selected() -> None:
    rows = [{"id": i, "service": "auth", "severity": ["INFO", "WARN"][i % 2], "latency": 100 + i} for i in range(50)]
    result = KompressorEngine().optimize(rows)
    assert result.kind == "schema_rows"
    assert result.reversible
    assert KompressorEngine().decompress(result.optimized_payload, result.metadata) == rows


def test_log_templates_reversible() -> None:
    text = "\n".join(
        f"2026-06-25T00:{i:02d}:00Z ERROR service=auth request=req-{i % 3} failed user={1000 + i}" for i in range(40)
    )
    codec = LogTemplatesCodec()
    result = codec.compress(text)
    assert result.reversible
    assert codec.decompress(result.payload, result.metadata) == text
    assert len(result.payload) < len(text)


def test_domain_codecs_emit_markers() -> None:
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "Demo"},
        "paths": {"/users": {"get": {"operationId": "listUsers", "responses": {"200": {}}}}},
        "components": {"schemas": {"User": {}}},
    }
    assert OpenApiCodec().compress(openapi).payload.startswith("<kompressor:openapi_v1>")

    terraform = {
        "resource_changes": [
            {"address": "aws_s3_bucket.logs", "type": "aws_s3_bucket", "change": {"actions": ["create"]}}
        ]
    }
    assert TerraformPlanCodec().compress(terraform).payload.startswith("<kompressor:terraform_plan_v1>")

    k8s = "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\nspec:\n  template:\n    spec:\n      containers:\n      - image: ghcr.io/acme/api:v1\n"
    assert K8sYamlCodec().compress(k8s).payload.startswith("<kompressor:k8s_yaml_v1>")

    ci = "pytest\nFAILED tests/test_demo.py::test_x\nTraceback error\n" * 20
    assert CiOutputCodec().compress(ci).payload.startswith("<kompressor:ci_output_v1>")

    blob = base64.b64encode(b"x" * 200).decode()
    assert BlobRefCodec().compress({"payload": blob}).payload.startswith("<kompressor:blob_ref_v1>")


def test_text_outline_codecs_emit_markers() -> None:
    md = "\n\n".join(f"## Section {i}\n" + "word " * 80 for i in range(8))
    assert MarkdownOutlineCodec().compress(md).payload.startswith("<kompressor:markdown_outline_v1>")

    html = "<html><title>T</title><body><h1>Hello</h1><a href='/x'>X</a></body></html>"
    assert HtmlVisibleCodec().compress(html).payload.startswith("<kompressor:html_visible_v1>")

    code = "import os\n" + "\n".join(f"def f{i}():\n    return {i}" for i in range(40))
    assert CodeSymbolsCodec().compress(code).payload.startswith("<kompressor:code_symbols_v1>")

    tool = "\n".join(f"{i}|line {i}" for i in range(150))
    assert ToolOutputCodec().compress(tool).payload.startswith("<kompressor:tool_output_v1>")


def test_engine_routes_specialized_payloads() -> None:
    openapi = {
        "openapi": "3.1.0",
        "paths": {
            f"/x/{i}": {"get": {"operationId": f"getX{i}", "responses": {"200": {"description": "ok"}}}}
            for i in range(30)
        },
    }
    result = KompressorEngine().optimize(openapi)
    assert result.kind == "openapi"
    assert not result.reversible
    assert json.loads(json.dumps(result.to_dict()))
