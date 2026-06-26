# ruff: noqa: E501
"""Additional exact lossless codecs for structured LLM context.

These codecs are intentionally conservative: candidates are only considered
when they can reconstruct the original value exactly from the payload plus any
explicit externalized metadata carried by the local runtime.
"""

from __future__ import annotations

import base64
import json
import re
import tokenize
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
from io import BytesIO
from typing import Any

from kompressor.codecs.base import Codec, CodecResult

SHAPE_ROWS_MARKER = "<kompressor:shape_rows_v1>"
ATOM_DICT_MARKER = "<kompressor:atom_dict_v1>"
XML_SHAPE_MARKER = "<kompressor:xml_shape_rows_v1>"
TRANSPORT_MARKER = "<kompressor:transport_deflate_v1>"
CHUNK_STORE_MARKER = "<kompressor:chunk_store_v1>"
CODE_TOKENS_MARKER = "<kompressor:code_tokens_v1>"
DOMAIN_REVERSIBLE_MARKER = "<kompressor:domain_table_v1>"


def _j(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _flatten(value: object, path: str = "$") -> list[tuple[str, object]]:
    if isinstance(value, dict):
        if not value:
            return [(path, {})]
        out: list[tuple[str, object]] = []
        for key, child in value.items():
            out.extend(_flatten(child, f"{path}.{key}"))
        return out
    if isinstance(value, list):
        if not value:
            return [(path, [])]
        out = []
        for idx, child in enumerate(value):
            out.extend(_flatten(child, f"{path}[{idx}]"))
        return out
    return [(path, value)]


def _path_tokens(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    for key, idx in re.findall(r"\.([^\.\[]+)|\[(\d+)\]", path[1:]):
        tokens.append(key if key else int(idx))
    return tokens


def _set_path(root: object, path: str, value: object) -> object:
    if path == "$":
        return value
    tokens = _path_tokens(path)
    cur = root
    for pos, token in enumerate(tokens):
        is_last = pos == len(tokens) - 1
        nxt = None if is_last else tokens[pos + 1]
        if isinstance(token, str):
            if not isinstance(cur, dict):
                raise ValueError("invalid dict path")
            if is_last:
                cur[token] = value
            else:
                cur = cur.setdefault(token, [] if isinstance(nxt, int) else {})
        else:
            if not isinstance(cur, list):
                raise ValueError("invalid list path")
            while len(cur) <= token:
                cur.append([] if isinstance(nxt, int) else {})
            if is_last:
                cur[token] = value
            else:
                cur = cur[token]
    return root


def _leaf_paths(row: object) -> list[str]:
    return [p for p, _ in _flatten(row)]


def _apply_column_transforms(columns: list[str], rows: list[list[Any]]) -> tuple[dict[str, Any], list[list[Any]]]:
    transforms: dict[str, Any] = {}
    out_rows = [list(row) for row in rows]
    if not rows:
        return transforms, out_rows
    for col_idx, name in enumerate(columns):
        vals = [row[col_idx] for row in rows]
        if len(vals) >= 3 and all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
            step = vals[1] - vals[0]
            if all(vals[i] == vals[0] + i * step for i in range(len(vals))):
                transforms[name] = {"kind": "int_sequence", "start": vals[0], "step": step}
                for row in out_rows:
                    row[col_idx] = None
                continue
        if len(vals) >= 3 and all(isinstance(v, str) for v in vals):
            strings = [str(v) for v in vals]
            prefix = strings[0]
            for s in strings[1:]:
                while not s.startswith(prefix) and prefix:
                    prefix = prefix[:-1]
            if len(prefix) >= 4:
                suffixes = [s[len(prefix) :] for s in strings]
                transforms[name] = {"kind": "prefix", "prefix": prefix}
                for idx, row in enumerate(out_rows):
                    row[col_idx] = suffixes[idx]
                continue
    return transforms, out_rows


def _restore_column_transforms(columns: list[str], rows: list[list[Any]], transforms: dict[str, Any]) -> list[list[Any]]:
    out = [list(row) for row in rows]
    for col_idx, name in enumerate(columns):
        transform = transforms.get(name)
        if not isinstance(transform, dict):
            continue
        if transform.get("kind") == "int_sequence":
            start = int(transform["start"])
            step = int(transform["step"])
            for idx, row in enumerate(out):
                row[col_idx] = start + idx * step
        elif transform.get("kind") == "prefix":
            prefix = str(transform["prefix"])
            for row in out:
                row[col_idx] = prefix + str(row[col_idx])
    return out


class ShapeRowsCodec(Codec):
    """Generalized exact row codec for homogeneous nested dict/list shapes."""

    name = "shape_rows"

    def _candidate(self, value: object) -> tuple[str, list[str], list[object]] | None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, dict) and len(child) >= 3 and all(isinstance(v, dict | list) for v in child.values()):
                    rows = list(child.values())
                    paths = _leaf_paths(rows[0])
                    if paths and all(_leaf_paths(row) == paths for row in rows):
                        return f"$.{key}", paths, rows
                if isinstance(child, list) and len(child) >= 3 and all(isinstance(v, dict | list) for v in child):
                    paths = _leaf_paths(child[0])
                    if paths and all(_leaf_paths(row) == paths for row in child):
                        return f"$.{key}", paths, list(child)
        if isinstance(value, list) and len(value) >= 3 and all(isinstance(v, dict | list) for v in value):
            paths = _leaf_paths(value[0])
            if paths and all(_leaf_paths(row) == paths for row in value):
                return "$", paths, list(value)
        return None

    def can_handle(self, value: object) -> bool:
        return self._candidate(value) is not None

    def compress(self, value: object) -> CodecResult:
        candidate = self._candidate(value)
        if candidate is None:
            raise TypeError("ShapeRowsCodec requires a homogeneous nested collection")
        root_path, paths, items = candidate
        rows = [[dict(_flatten(item)).get(path) for path in paths] for item in items]
        constants: dict[str, Any] = {}
        variable_paths: list[str] = []
        variable_rows: list[list[Any]] = []
        for col_idx, path in enumerate(paths):
            vals = [row[col_idx] for row in rows]
            if all(v == vals[0] for v in vals):
                constants[path] = vals[0]
            else:
                variable_paths.append(path)
        for row in rows:
            variable_rows.append([row[paths.index(path)] for path in variable_paths])
        transforms, encoded_rows = _apply_column_transforms(variable_paths, variable_rows)
        header: dict[str, Any] = {
            "root_path": root_path,
            "count": len(items),
            "paths": variable_paths,
            "constants": constants,
            "transforms": transforms,
        }
        if isinstance(value, dict) and root_path != "$":
            key = root_path[2:]
            header["extras"] = {k: v for k, v in value.items() if k != key}
            if isinstance(value.get(key), dict):
                header["child_keys"] = list(value[key].keys())
        payload = "\n".join([SHAPE_ROWS_MARKER, _j(header), "@rows", *(_j(row) for row in encoded_rows)])
        return CodecResult(payload, True, {"marker": SHAPE_ROWS_MARKER}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        header = json.loads(lines[1])
        row_start = lines.index("@rows") + 1
        paths: list[str] = header["paths"]
        constants: dict[str, Any] = header.get("constants", {})
        rows = [json.loads(line) for line in lines[row_start:]]
        rows = _restore_column_transforms(paths, rows, header.get("transforms", {}))
        items = []
        for values in rows:
            item: object = [] if paths and paths[0].startswith("$[") else {}
            for path, value in constants.items():
                item = _set_path(item, path, value)
            for path, value in zip(paths, values, strict=False):
                item = _set_path(item, path, value)
            items.append(item)
        root_path = header["root_path"]
        if root_path == "$":
            return items
        if isinstance(header.get("extras"), dict):
            root = dict(header["extras"])
            key = root_path[2:]
            child_keys = header.get("child_keys")
            if isinstance(child_keys, list):
                root[key] = {k: v for k, v in zip(child_keys, items, strict=False)}
            else:
                root[key] = items
            return root
        return items


class AtomDictCodec(Codec):
    """Exact global atom/string dictionary for repeated scalar strings and keys."""

    name = "atom_dict"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, dict | list | str) and len(_as_text(value)) >= 500

    def compress(self, value: object) -> CodecResult:
        counts: Counter[str] = Counter()

        def collect(node: object) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    counts[str(k)] += 1
                    collect(v)
            elif isinstance(node, list):
                for v in node:
                    collect(v)
            elif isinstance(node, str) and len(node) >= 4:
                counts[node] += 1

        collect(value)
        atoms = [s for s, c in counts.most_common(128) if c >= 3 and (c - 1) * len(s) > len(s) + 8]
        if not atoms:
            return CodecResult(_as_text(value), True, {"marker": ATOM_DICT_MARKER}, ["no profitable atoms"])
        ids = {atom: f"@{idx}" for idx, atom in enumerate(atoms)}

        def encode(node: object) -> object:
            if isinstance(node, dict):
                return [[ids.get(str(k), k), encode(v)] for k, v in node.items()]
            if isinstance(node, list):
                return [encode(v) for v in node]
            if isinstance(node, str):
                return {"$a": ids[node]} if node in ids else node
            return node

        header = {"atoms": {v: k for k, v in ids.items()}, "root_type": type(value).__name__}
        payload = "\n".join([ATOM_DICT_MARKER, _j(header), "root=" + _j(encode(value))])
        return CodecResult(payload, True, {"marker": ATOM_DICT_MARKER}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        header = json.loads(lines[1])
        atoms: dict[str, str] = header["atoms"]
        root = json.loads(lines[2][5:])

        def decode(node: object) -> object:
            if isinstance(node, dict) and set(node) == {"$a"}:
                return atoms[node["$a"]]
            if isinstance(node, list):
                if all(isinstance(x, list) and len(x) == 2 for x in node):
                    return {atoms.get(str(k), str(k)): decode(v) for k, v in node}
                return [decode(v) for v in node]
            return node

        return decode(root)


class XmlShapeRowsCodec(Codec):
    """Exact XML structural codec for repeated sibling element shapes."""

    name = "xml_shape_rows"

    def can_handle(self, value: object) -> bool:
        if not isinstance(value, str) or "<" not in value or ">" not in value:
            return False
        try:
            root = ET.fromstring(value)
        except ET.ParseError:
            return False
        children = list(root)
        if len(children) < 3:
            return False
        sig = self._sig(children[0])
        return all(self._sig(c) == sig for c in children)

    def _sig(self, elem: ET.Element) -> object:
        return (elem.tag, tuple(sorted(elem.attrib)), tuple(self._sig(c) for c in elem))

    def _row_paths(self, elem: ET.Element, path: str = "$") -> list[tuple[str, str]]:
        out = [(f"{path}#text", elem.text or "")]
        for key in sorted(elem.attrib):
            out.append((f"{path}@{key}", elem.attrib[key]))
        for idx, child in enumerate(list(elem)):
            out.extend(self._row_paths(child, f"{path}/{idx}:{child.tag}"))
        return out

    def _set_xml_path(self, elem: ET.Element, path: str, value: str) -> None:
        if path.endswith("#text"):
            target = elem
            for part in path[1:-5].split("/"):
                if not part:
                    continue
                idx = int(part.split(":", 1)[0])
                target = list(target)[idx]
            target.text = value
            return
        attr = path.rsplit("@", 1)[1]
        target_path = path.rsplit("@", 1)[0]
        target = elem
        for part in target_path[1:].split("/"):
            if not part:
                continue
            idx = int(part.split(":", 1)[0])
            target = list(target)[idx]
        target.attrib[attr] = value

    def compress(self, value: object) -> CodecResult:
        if not isinstance(value, str):
            raise TypeError("XmlShapeRowsCodec requires XML text")
        root = ET.fromstring(value)
        children = list(root)
        paths = [p for p, _ in self._row_paths(children[0])]
        rows = [[dict(self._row_paths(child)).get(p, "") for p in paths] for child in children]
        constants: dict[str, Any] = {}
        variable_paths = []
        for idx, path in enumerate(paths):
            vals = [row[idx] for row in rows]
            if all(v == vals[0] for v in vals):
                constants[path] = vals[0]
            else:
                variable_paths.append(path)
        variable_rows = [[row[paths.index(path)] for path in variable_paths] for row in rows]
        header = {"root_tag": root.tag, "root_attrib": root.attrib, "root_text": root.text or "", "child_template": ET.tostring(children[0], encoding="unicode"), "paths": variable_paths, "constants": constants, "tail": root.tail or ""}
        payload = "\n".join([XML_SHAPE_MARKER, _j(header), "@rows", *(_j(row) for row in variable_rows)])
        return CodecResult(payload, True, {"marker": XML_SHAPE_MARKER}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        header = json.loads(lines[1])
        rows = [json.loads(line) for line in lines[lines.index("@rows") + 1 :]]
        root = ET.Element(header["root_tag"], header.get("root_attrib", {}))
        root.text = header.get("root_text", "")
        paths: list[str] = header["paths"]
        constants: dict[str, str] = header.get("constants", {})
        for row in rows:
            child = ET.fromstring(header["child_template"])
            for path, value in constants.items():
                self._set_xml_path(child, path, value)
            for path, value in zip(paths, row, strict=False):
                self._set_xml_path(child, path, value)
            root.append(child)
        root.tail = header.get("tail", "")
        return ET.tostring(root, encoding="unicode")


class TransportDeflateCodec(Codec):
    """External/local-decode lossless transport fallback using zlib+base64."""

    name = "transport_deflate"

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def can_handle(self, value: object) -> bool:
        return self.enabled and len(_as_text(value)) >= 600

    def compress(self, value: object) -> CodecResult:
        text = _as_text(value)
        body = base64.b85encode(zlib.compress(text.encode(), 9)).decode("ascii")
        payload = "\n".join([TRANSPORT_MARKER, f"encoding=zlib+b85 chars={len(text)}", body])
        return CodecResult(payload, True, {"marker": TRANSPORT_MARKER, "mode": "local_decode", "original_type": type(value).__name__}, ["requires local runtime decompression before model reasoning"])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        body = payload.split("\n", 2)[2]
        text = zlib.decompress(base64.b85decode(body.encode("ascii"))).decode()
        if metadata.get("original_type") in {"dict", "list"}:
            return json.loads(text)
        return text


class ChunkStoreCodec(Codec):
    """Externalized reversible chunk dictionary for repeated context blocks."""

    name = "chunk_store"

    def can_handle(self, value: object) -> bool:
        text = _as_text(value)
        return len(text) >= 1200 and ("\n\n" in text or text.count("\n") >= 20)

    def compress(self, value: object) -> CodecResult:
        text = _as_text(value)
        sep = "\n\n" if "\n\n" in text else "\n"
        chunks = text.split(sep)
        dictionary: dict[str, str] = {}
        seq: list[str] = []
        for chunk in chunks:
            key = f"c{len(dictionary)}"
            for existing, value_ in dictionary.items():
                if value_ == chunk:
                    key = existing
                    break
            else:
                dictionary[key] = chunk
            seq.append(key)
        if len(dictionary) > len(chunks) * 0.8:
            return CodecResult(text, True, {"marker": CHUNK_STORE_MARKER}, ["too few repeated chunks"])
        payload = "\n".join([CHUNK_STORE_MARKER, "sep=" + _j(sep), "dict=" + _j(dictionary), "seq=" + ",".join(seq)])
        return CodecResult(payload, True, {"marker": CHUNK_STORE_MARKER, "dictionary": dictionary}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        sep = json.loads(lines[1][4:])
        dictionary = json.loads(lines[2][5:])
        seq = lines[3][4:].split(",") if lines[3][4:] else []
        return sep.join(dictionary[key] for key in seq)


class CodeTokensCodec(Codec):
    """Exact Python-source token stream codec with identifier/string dictionaries."""

    name = "code_tokens"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, str) and len(value.splitlines()) >= 20 and bool(re.search(r"^\s*(def|class|import|from)\b", value, re.M))

    def compress(self, value: object) -> CodecResult:
        if not isinstance(value, str):
            raise TypeError("CodeTokensCodec requires source text")
        try:
            toks = list(tokenize.tokenize(BytesIO(value.encode()).readline))
        except tokenize.TokenError:
            return CodecResult(value, True, {"marker": CODE_TOKENS_MARKER}, ["tokenization failed"])
        strings = [t.string for t in toks if t.type not in {tokenize.ENCODING, tokenize.ENDMARKER} and len(t.string) >= 3]
        counts = Counter(strings)
        atoms = [s for s, c in counts.most_common(128) if c >= 2]
        atom_ids = {s: f"${i}" for i, s in enumerate(atoms)}
        rows = [[t.type, atom_ids.get(t.string, t.string), t.start, t.end, t.line] for t in toks if t.type != tokenize.ENCODING]
        header = {"atoms": {v: k for k, v in atom_ids.items()}}
        payload = "\n".join([CODE_TOKENS_MARKER, _j(header), "rows=" + _j(rows)])
        return CodecResult(payload, True, {"marker": CODE_TOKENS_MARKER}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        atoms = json.loads(lines[1])["atoms"]
        rows = json.loads(lines[2][5:])
        toks = []
        for typ, string, start, end, line in rows:
            toks.append(tokenize.TokenInfo(typ, atoms.get(string, string), tuple(start), tuple(end), line))
        restored = tokenize.untokenize(toks)
        return restored.decode() if isinstance(restored, bytes) else restored


class DomainTableCodec(Codec):
    """Exact reversible domain table for common OpenAPI/Terraform/K8s document shapes."""

    name = "domain_table"

    def can_handle(self, value: object) -> bool:
        text = _as_text(value)
        if isinstance(value, dict) and ("openapi" in value or "swagger" in value or "resource_changes" in value):
            return True
        return isinstance(value, str) and any(h in text for h in ("apiVersion:", "kind:", "metadata:", "# ", "<html", "<body")) and len(text) >= 400

    def compress(self, value: object) -> CodecResult:
        # Domain codecs here stay exact by combining a compact analytical index
        # with a deflated source sidecar in the same payload. Model can reason
        # from the index; local decompression restores exact bytes.
        text = _as_text(value)
        facts: list[str] = []
        if isinstance(value, dict) and isinstance(value.get("paths"), dict):
            for path, methods in value.get("paths", {}).items():
                if isinstance(methods, dict):
                    facts.extend(f"{m.upper()} {path}" for m in methods if m.lower() in {"get", "post", "put", "patch", "delete"})
        elif isinstance(value, dict) and isinstance(value.get("resource_changes"), list):
            for rc in value["resource_changes"][:200]:
                if isinstance(rc, dict):
                    facts.append(f"{rc.get('address')} {rc.get('type')} {((rc.get('change') or {}).get('actions') if isinstance(rc.get('change'), dict) else '')}")
        else:
            facts.extend(line for line in text.splitlines() if line.lstrip().startswith(("apiVersion", "kind", "name:", "#", "<title", "<h1", "<h2")))
        sidecar = base64.b85encode(zlib.compress(text.encode(), 9)).decode("ascii")
        payload = "\n".join([DOMAIN_REVERSIBLE_MARKER, "@index", *facts[:240], "@deflate_b85", sidecar])
        return CodecResult(payload, True, {"marker": DOMAIN_REVERSIBLE_MARKER, "mode": "self_contained_deflate", "original_type": type(value).__name__}, ["exact reconstruction uses embedded deflated source"])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        body = payload.split("@deflate_b85\n", 1)[1]
        text = zlib.decompress(base64.b85decode(body.encode("ascii"))).decode()
        if metadata.get("original_type") in {"dict", "list"}:
            return json.loads(text)
        return text
