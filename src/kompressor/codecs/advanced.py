# ruff: noqa: E501
"""Additional high-compression codecs for structured LLM context.

These codecs favor model-readable compact representations. Some are exactly
reversible, while domain codecs are analytical/lossy by design and carry an
explicit warning in their metadata.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from kompressor.codecs.base import Codec, CodecResult
from kompressor.codecs.lossless_ext import _apply_column_transforms, _restore_column_transforms

SCHEMA_ROWS_MARKER = "<kompressor:schema_rows_v1>"
LOG_TEMPLATES_MARKER = "<kompressor:log_templates_v1>"
LOG_SUMMARY_MARKER = "<kompressor:log_summary_v1>"
CI_OUTPUT_MARKER = "<kompressor:ci_output_v1>"
BLOB_REF_MARKER = "<kompressor:blob_ref_v1>"
OPENAPI_MARKER = "<kompressor:openapi_v1>"
TERRAFORM_MARKER = "<kompressor:terraform_plan_v1>"
K8S_MARKER = "<kompressor:k8s_yaml_v1>"
MARKDOWN_MARKER = "<kompressor:markdown_outline_v1>"
HTML_MARKER = "<kompressor:html_visible_v1>"
CODE_MARKER = "<kompressor:code_symbols_v1>"
TOOL_MARKER = "<kompressor:tool_output_v1>"
DEDUPE_MARKER = "<kompressor:dedupe_v1>"
EXTRACTIVE_MARKER = "<kompressor:extractive_v1>"


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _j(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def _lines(text: str) -> list[str]:
    return text.splitlines()


class SchemaRowsCodec(Codec):
    """Reversible typed columnar codec for homogeneous JSON records."""

    name = "schema_rows"

    def can_handle(self, value: object) -> bool:
        if not (isinstance(value, list) and len(value) >= 3 and all(isinstance(row, dict) for row in value)):
            return False
        rows: list[dict[str, Any]] = value  # type: ignore[assignment]
        return all(_is_scalar(cell) for row in rows for cell in row.values())

    def _keys(self, rows: list[dict[str, Any]]) -> list[str]:
        keys: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        return keys

    def compress(self, value: object) -> CodecResult:
        if not self.can_handle(value):
            raise TypeError("SchemaRowsCodec requires homogeneous scalar record rows")
        rows: list[dict[str, Any]] = value  # type: ignore[assignment]
        keys = self._keys(rows)
        constants: dict[str, Any] = {}
        enum_maps: dict[str, dict[Any, int]] = {}
        variable_keys: list[str] = []
        for key in keys:
            vals = [row.get(key) for row in rows]
            unique = []
            seen = set()
            for val in vals:
                marker = _j(val)
                if marker not in seen:
                    seen.add(marker)
                    unique.append(val)
            if len(unique) == 1:
                constants[key] = unique[0]
            else:
                variable_keys.append(key)
                if all(isinstance(v, str) or v is None for v in unique) and len(unique) <= min(
                    64, max(2, len(rows) // 2)
                ):
                    enum_maps[key] = {v: idx for idx, v in enumerate(unique)}
        transforms, encoded_rows = _apply_column_transforms(variable_keys, [
            [enum_maps[key][row.get(key)] if key in enum_maps else row.get(key) for key in variable_keys]
            for row in rows
        ])
        header = {
            "columns": variable_keys,
            "constants": constants,
            "enums": {k: vals for k, vals in ((k, list(m)) for k, m in enum_maps.items())},
            "transforms": transforms,
        }
        lines = [SCHEMA_ROWS_MARKER, _j(header), "@rows"]
        for cells in encoded_rows:
            lines.append(_j(cells))
        return CodecResult(
            "\n".join(lines),
            True,
            {"marker": SCHEMA_ROWS_MARKER},
            ["schema_rows uses dictionary/constant-column encoding and is exactly reversible"],
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        if lines and lines[0].startswith(SCHEMA_ROWS_MARKER):
            lines = lines[1:]
        header = json.loads(lines[0])
        row_start = lines.index("@rows") + 1
        columns: list[str] = header["columns"]
        constants: dict[str, Any] = header.get("constants", {})
        enum_values: dict[str, list[Any]] = header.get("enums", {})
        out = []
        encoded_rows = [json.loads(line) for line in lines[row_start:]]
        decoded_rows = _restore_column_transforms(columns, encoded_rows, header.get("transforms", {}))
        for values in decoded_rows:
            row = dict(constants)
            for key, value in zip(columns, values, strict=False):
                row[key] = enum_values[key][value] if key in enum_values else value
            out.append(row)
        return out


class LogTemplatesCodec(Codec):
    """Reversible Drain-like log template codec with variable extraction."""

    name = "log_templates"
    _token = re.compile(r"([A-Za-z_]+)=([^\s]+)|\b\d{1,4}(?:[-:/]\d{1,4})+(?:Z)?\b|\b\d+\b|[0-9a-f]{8,}\b")

    def can_handle(self, value: object) -> bool:
        return isinstance(value, str) and len(value.splitlines()) >= 8

    def _template(self, line: str) -> tuple[str, list[str]]:
        vals: list[str] = []

        def repl(match: re.Match[str]) -> str:
            vals.append(match.group(0))
            return f"{{v{len(vals) - 1}}}"

        return self._token.sub(repl, line), vals

    def compress(self, value: object) -> CodecResult:
        if not isinstance(value, str):
            raise TypeError("LogTemplatesCodec requires text")
        templates: dict[str, int] = {}
        template_text: list[str] = []
        rows: list[list[Any]] = []
        for line in value.splitlines():
            templ, vals = self._template(line)
            if templ not in templates:
                templates[templ] = len(template_text)
                template_text.append(templ)
            rows.append([templates[templ], vals])
        if len(template_text) > len(rows) * 0.85:
            return CodecResult(value, True, {"marker": LOG_TEMPLATES_MARKER}, ["too few repeated log templates"])
        payload = "\n".join(
            [
                LOG_TEMPLATES_MARKER,
                "@templates",
                *(f"{idx} {template}" for idx, template in enumerate(template_text)),
                "@rows",
                *(" ".join([str(tid), *vals]) for tid, vals in rows),
            ]
        )
        return CodecResult(payload, True, {"marker": LOG_TEMPLATES_MARKER}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        template_start = lines.index("@templates") + 1
        row_start = lines.index("@rows")
        templates = {}
        for line in lines[template_start:row_start]:
            ident, template = line.split(" ", 1)
            templates[int(ident)] = template
        out = []
        for line in lines[row_start + 1 :]:
            parts = line.split(" ")
            tid = int(parts[0])
            vals = parts[1:]
            restored = templates[tid]
            for idx, val in enumerate(vals):
                restored = restored.replace(f"{{v{idx}}}", val, 1)
            out.append(restored)
        return "\n".join(out)


class LogSummaryCodec(Codec):
    """Lossy analytical log compression: counts, templates, and exemplars."""

    name = "log_summary"
    _level = re.compile(r"\b(ERROR|WARN|WARNING|INFO|DEBUG|TRACE|CRITICAL)\b")

    def can_handle(self, value: object) -> bool:
        return isinstance(value, str) and len(value.splitlines()) >= 20 and bool(self._level.search(value))

    def compress(self, value: object) -> CodecResult:
        text = str(value)
        lines = text.splitlines()
        levels = Counter(m.group(1) for line in lines if (m := self._level.search(line)))
        templater = LogTemplatesCodec()
        templates = Counter(templater._template(line)[0] for line in lines)
        top_templates = [f"{count}x {template}" for template, count in templates.most_common(20)]
        error_examples = [line for line in lines if re.search(r"ERROR|CRITICAL|WARN|WARNING", line)][:30]
        payload = "\n".join(
            [
                LOG_SUMMARY_MARKER,
                f"lines={len(lines)} levels={_j(dict(levels))} sha={_sha(text)}",
                "@top_templates",
                *top_templates,
                "@examples",
                *error_examples,
            ]
        )
        return CodecResult(
            payload,
            False,
            {"marker": LOG_SUMMARY_MARKER, "mode": "lossy_analytical"},
            ["lossy log template/count summary"],
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("log_summary is lossy")


@dataclass(frozen=True)
class DomainPattern:
    marker: str
    name: str
    hints: tuple[str, ...]


class CiOutputCodec(Codec):
    name = "ci_output"

    def can_handle(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        text = value.lower()
        return (
            any(h in text for h in ("failed", "traceback", "error:", "pytest", "passed", "exit code")) and "\n" in value
        )

    def compress(self, value: object) -> CodecResult:
        text = str(value)
        lines = text.splitlines()
        failed = [
            line for line in lines if re.search(r"FAILED|ERROR|Traceback|AssertionError|exit code|Exception", line)
        ]
        warnings = [line for line in lines if "warning" in line.lower()]
        passed = sum(1 for line in lines if re.search(r"\bPASSED\b|\bpassed\b", line))
        selected = failed[:80] + (
            [f"... {max(0, len(failed) - 80)} more failure/error lines omitted"] if len(failed) > 80 else []
        )
        payload = "\n".join(
            [
                CI_OUTPUT_MARKER,
                f"lines={len(lines)} passed_lines={passed} warnings={len(warnings)} failures={len(failed)} sha={_sha(text)}",
                "@important",
                *selected,
            ]
        )
        return CodecResult(
            payload, False, {"marker": CI_OUTPUT_MARKER, "mode": "lossy_analytical"}, ["lossy CI summary"]
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("ci_output is a lossy analytical codec")


class BlobRefCodec(Codec):
    name = "blob_ref"
    _b64 = re.compile(r"(?P<blob>[A-Za-z0-9+/]{160,}={0,2})")

    def can_handle(self, value: object) -> bool:
        text = value if isinstance(value, str) else _j(value) if isinstance(value, dict | list) else ""
        return bool(self._b64.search(text))

    def compress(self, value: object) -> CodecResult:
        text = value if isinstance(value, str) else _j(value)
        blobs = []

        def repl(match: re.Match[str]) -> str:
            raw = match.group("blob")
            try:
                decoded = base64.b64decode(raw + "===", validate=False)
                size = len(decoded)
            except Exception:
                size = len(raw)
            ident = f"blob{len(blobs)}"
            blobs.append({"id": ident, "chars": len(raw), "bytes_est": size, "sha16": _sha(raw)})
            return f"<{ident}:base64 chars={len(raw)} sha16={_sha(raw)}>"

        compact = self._b64.sub(repl, text)
        payload = "\n".join([BLOB_REF_MARKER, "blobs=" + _j(blobs), compact])
        return CodecResult(payload, False, {"marker": BLOB_REF_MARKER, "mode": "externalized", "blobs": blobs}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("blob_ref externalizes blobs and is not reversible without sidecar storage")


class OpenApiCodec(Codec):
    name = "openapi"

    def can_handle(self, value: object) -> bool:
        return (
            isinstance(value, dict)
            and ("openapi" in value or "swagger" in value)
            and isinstance(value.get("paths"), dict)
        )

    def compress(self, value: object) -> CodecResult:
        spec: dict[str, Any] = value  # type: ignore[assignment]
        ops = []
        for path, methods in spec.get("paths", {}).items():
            if not isinstance(methods, dict):
                continue
            for method, op in methods.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                op = op if isinstance(op, dict) else {}
                responses = (
                    ",".join(str(k) for k in (op.get("responses") or {}))
                    if isinstance(op.get("responses"), dict)
                    else ""
                )
                ops.append(
                    f"{method.upper()} {path} id={op.get('operationId', '')} tags={','.join(op.get('tags', [])) if isinstance(op.get('tags'), list) else ''} res={responses}"
                )
        schemas = (
            sorted(((spec.get("components") or {}).get("schemas") or {}).keys())
            if isinstance(spec.get("components"), dict)
            else []
        )
        payload = "\n".join(
            [
                OPENAPI_MARKER,
                f"title={((spec.get('info') or {}).get('title', '') if isinstance(spec.get('info'), dict) else '')}",
                "@operations",
                *ops,
                "@schemas",
                ",".join(schemas),
            ]
        )
        return CodecResult(
            payload,
            False,
            {"marker": OPENAPI_MARKER, "mode": "lossy_analytical"},
            ["lossy OpenAPI operation/schema index"],
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("openapi summary is lossy")


class TerraformPlanCodec(Codec):
    name = "terraform_plan"

    def can_handle(self, value: object) -> bool:
        text = value if isinstance(value, str) else _j(value) if isinstance(value, dict) else ""
        return "Terraform will perform" in text or "resource_changes" in text or "Plan:" in text

    def compress(self, value: object) -> CodecResult:
        if isinstance(value, dict) and isinstance(value.get("resource_changes"), list):
            rows = []
            counts: Counter[str] = Counter()
            for rc in value["resource_changes"]:
                if not isinstance(rc, dict):
                    continue
                actions = (
                    "+".join((rc.get("change") or {}).get("actions", [])) if isinstance(rc.get("change"), dict) else "?"
                )
                counts[actions] += 1
                rows.append(f"{actions} {rc.get('address', '')} type={rc.get('type', '')}")
            payload = "\n".join([TERRAFORM_MARKER, "counts=" + _j(dict(counts)), "@changes", *rows])
        else:
            text = str(value)
            important = [line for line in text.splitlines() if re.match(r"\s*[#~+\-]|Plan:", line)]
            payload = "\n".join(
                [TERRAFORM_MARKER, f"sha={_sha(text)} lines={len(text.splitlines())}", "@changes", *important[:200]]
            )
        return CodecResult(
            payload, False, {"marker": TERRAFORM_MARKER, "mode": "lossy_analytical"}, ["lossy Terraform change summary"]
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("terraform_plan summary is lossy")


class K8sYamlCodec(Codec):
    name = "k8s_yaml"

    def can_handle(self, value: object) -> bool:
        text = value if isinstance(value, str) else _j(value) if isinstance(value, dict | list) else ""
        return (
            "apiVersion" in text
            and "kind" in text
            and any(k in text for k in ("metadata", "Deployment", "Service", "Pod", "ConfigMap"))
        )

    def compress(self, value: object) -> CodecResult:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        docs = re.split(r"^---\s*$", text, flags=re.MULTILINE)
        resources = []
        for doc in docs:
            kind = re.search(r"^kind:\s*(\S+)|\"kind\"\s*:\s*\"([^\"]+)\"", doc, re.MULTILINE)
            name = re.search(r"^\s*name:\s*([^\s]+)|\"name\"\s*:\s*\"([^\"]+)\"", doc, re.MULTILINE)
            ns = re.search(r"^\s*namespace:\s*([^\s]+)|\"namespace\"\s*:\s*\"([^\"]+)\"", doc, re.MULTILINE)
            image = re.findall(r"image:\s*([^\s]+)|\"image\"\s*:\s*\"([^\"]+)\"", doc)
            images = [a or b for a, b in image]
            if kind:
                resources.append(
                    f"{kind.group(1) or kind.group(2)} {ns.group(1) if ns and ns.group(1) else (ns.group(2) if ns else 'default')}/{name.group(1) if name and name.group(1) else (name.group(2) if name else '?')} images={','.join(images)}"
                )
        payload = "\n".join([K8S_MARKER, f"resources={len(resources)} sha={_sha(text)}", "@resources", *resources])
        return CodecResult(
            payload, False, {"marker": K8S_MARKER, "mode": "lossy_analytical"}, ["lossy Kubernetes resource summary"]
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("k8s_yaml summary is lossy")


class MarkdownOutlineCodec(Codec):
    name = "markdown_outline"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, str) and value.count("\n#") >= 3

    def compress(self, value: object) -> CodecResult:
        text = str(value)
        headings = [line for line in text.splitlines() if line.startswith("#")]
        code_blocks = text.count("```") // 2
        bullets = sum(1 for line in text.splitlines() if line.lstrip().startswith(("- ", "* ")))
        payload = "\n".join(
            [
                MARKDOWN_MARKER,
                f"lines={len(text.splitlines())} code_blocks={code_blocks} bullets={bullets} sha={_sha(text)}",
                "@outline",
                *headings[:200],
            ]
        )
        return CodecResult(
            payload, False, {"marker": MARKDOWN_MARKER, "mode": "lossy_outline"}, ["lossy Markdown outline"]
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("markdown outline is lossy")


class HtmlVisibleCodec(Codec):
    name = "html_visible"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, str) and bool(re.search(r"<html|<body|<div|<table|<a\s", value, re.I))

    def compress(self, value: object) -> CodecResult:
        text = str(value)
        title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        links = re.findall(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", text, re.I | re.S)
        headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", text, re.I | re.S)

        def clean(s: str) -> str:
            return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()

        payload = "\n".join(
            [
                HTML_MARKER,
                f"title={clean(title.group(1)) if title else ''} links={len(links)} sha={_sha(text)}",
                "@headings",
                *(clean(h) for h in headings[:80]),
                "@links",
                *(f"{clean(label)} -> {href}" for href, label in links[:120]),
            ]
        )
        return CodecResult(
            payload, False, {"marker": HTML_MARKER, "mode": "lossy_visible"}, ["lossy visible HTML outline"]
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("html visible outline is lossy")


class CodeSymbolsCodec(Codec):
    name = "code_symbols"

    def can_handle(self, value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value.splitlines()) >= 30
            and bool(re.search(r"^\s*(def|class|function|const|interface|type|package|func)\s+", value, re.M))
        )

    def compress(self, value: object) -> CodecResult:
        text = str(value)
        symbols = re.findall(r"^\s*(def|class|function|const|interface|type|func)\s+([^(:={\s]+)", text, re.M)
        imports = [line.strip() for line in text.splitlines() if re.match(r"\s*(import|from|package)\b", line)][:80]
        payload = "\n".join(
            [
                CODE_MARKER,
                f"lines={len(text.splitlines())} sha={_sha(text)}",
                "@imports",
                *imports,
                "@symbols",
                *(f"{kind} {name}" for kind, name in symbols[:200]),
            ]
        )
        return CodecResult(
            payload, False, {"marker": CODE_MARKER, "mode": "lossy_symbol_index"}, ["lossy source symbol outline"]
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("code symbol outline is lossy")


class ToolOutputCodec(Codec):
    name = "tool_output"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, str) and bool(
            re.search(r"^\s*\d+\||\[terminal\]|\[read_file\]|^@@|^diff --git", value, re.M)
        )

    def compress(self, value: object) -> CodecResult:
        text = str(value)
        lines = text.splitlines()
        numbered = [line for line in lines if re.match(r"\s*\d+\|", line)]
        diffs = [line for line in lines if line.startswith(("diff --git", "@@", "+", "-"))]
        errors = [line for line in lines if re.search(r"error|failed|traceback|exception", line, re.I)]
        selected = errors[:80] or diffs[:120] or numbered[:120] or lines[:80]
        payload = "\n".join(
            [
                TOOL_MARKER,
                f"lines={len(lines)} numbered={len(numbered)} diff_lines={len(diffs)} errors={len(errors)} sha={_sha(text)}",
                "@selected",
                *selected,
            ]
        )
        return CodecResult(
            payload, False, {"marker": TOOL_MARKER, "mode": "lossy_tool_summary"}, ["lossy tool-output summary"]
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("tool output summary is lossy")


class DedupeCodec(Codec):
    name = "dedupe"

    def can_handle(self, value: object) -> bool:
        if not isinstance(value, str) or "\n" not in value:
            return False
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", value) if len(chunk.strip()) > 40]
        return len(chunks) >= 4 and len({c for c in chunks}) < len(chunks)

    def compress(self, value: object) -> CodecResult:
        text = str(value)
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text)]
        dictionary: dict[str, str] = {}
        out = [DEDUPE_MARKER, "@chunks"]
        for chunk in chunks:
            if not chunk:
                continue
            key = _sha(chunk)
            if key not in dictionary:
                dictionary[key] = chunk
                out.append(f"&{key}={chunk}")
            else:
                out.append(f"*{key}")
        return CodecResult("\n".join(out), True, {"marker": DEDUPE_MARKER, "dictionary": dictionary}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()[2:]
        dictionary = metadata.get("dictionary", {})
        out = []
        for line in lines:
            if line.startswith("*"):
                out.append(dictionary[line[1:]])
            elif line.startswith("&"):
                key, chunk = line[1:].split("=", 1)
                dictionary[key] = chunk
                out.append(chunk)
        return "\n\n".join(out)


class ExtractiveTextCodec(Codec):
    name = "extractive"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, str) and len(value.split()) >= 500

    def compress(self, value: object) -> CodecResult:
        text = str(value)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text.lower())
        stop = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "into", "have", "has"}
        freq = Counter(w for w in words if w not in stop and len(w) > 3)
        scored = sorted(
            paragraphs,
            key=lambda p: sum(freq[w.lower()] for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", p)),
            reverse=True,
        )
        keep = scored[: min(12, max(3, len(scored) // 5))]
        payload = "\n".join(
            [EXTRACTIVE_MARKER, f"paragraphs={len(paragraphs)} words={len(words)} sha={_sha(text)}", "@extracts", *keep]
        )
        return CodecResult(
            payload, False, {"marker": EXTRACTIVE_MARKER, "mode": "lossy_extractive"}, ["lossy extractive text summary"]
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        raise ValueError("extractive summary is lossy")
