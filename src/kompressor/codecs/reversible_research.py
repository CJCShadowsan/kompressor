# ruff: noqa: E501
"""Research-inspired reversible prompt compression codecs.

The codecs in this module are intentionally self-contained: every compressed
payload carries enough information for exact reconstruction, except where the
strategy is explicitly hash/sidecar backed and the sidecar bytes are carried in
metadata for local reversal.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from typing import Any

from kompressor.codecs.base import Codec, CodecResult

META_TOKENS_MARKER = "<kompressor:meta_tokens_v1>"
TOKEN_LZ_MARKER = "<kompressor:token_lz_v1>"
SEPARATOR_SEGMENTS_MARKER = "<kompressor:separator_segments_v1>"
GRAMMAR_MARKER = "<kompressor:grammar_v1>"
PATH_DICT_ROWS_MARKER = "<kompressor:path_dict_rows_v1>"
TREE_DICT_MARKER = "<kompressor:tree_dict_v1>"
SESSION_DELTA_MARKER = "<kompressor:session_delta_v1>"
SIDECAR_REF_MARKER = "<kompressor:sidecar_ref_v1>"


def _j(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _tokens(text: str) -> list[str]:
    return re.findall(r"\s+|[A-Za-z0-9_./:@=-]+|[^\w\s]", text, flags=re.UNICODE)


def _token_cost(text: str) -> int:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _phrase_payload(marker: str, text: str, *, min_count: int = 3, max_entries: int = 96) -> CodecResult:
    toks = _tokens(text)
    if len(toks) < 80:
        return CodecResult(text, True, {"marker": marker}, ["too few tokens for phrase compression"])
    candidates: list[tuple[int, tuple[str, ...], int]] = []
    for n in range(12, 2, -1):
        counts = Counter(tuple(toks[i : i + n]) for i in range(0, len(toks) - n + 1))
        for phrase, count in counts.items():
            if count < min_count:
                continue
            phrase_text = "".join(phrase)
            if len(phrase_text) < 12:
                continue
            # Score by local tokenizer cost when available rather than raw
            # characters.  This keeps the codec provider-neutral while making
            # token_lz/meta-token selection sensitive to BPE boundaries.
            marker_cost = _token_cost(f"§{len(candidates)}§")
            score = (count - 1) * _token_cost(phrase_text) - (_token_cost(phrase_text) + count * marker_cost)
            if score > 20:
                candidates.append((score, phrase, count))
    candidates.sort(reverse=True, key=lambda item: item[0])
    dictionary: list[str] = []
    selected: list[tuple[str, ...]] = []
    used_texts: set[str] = set()
    for _score, phrase, _count in candidates:
        phrase_text = "".join(phrase)
        if phrase_text in used_texts:
            continue
        if any(phrase_text in existing or existing in phrase_text for existing in used_texts):
            continue
        used_texts.add(phrase_text)
        dictionary.append(phrase_text)
        selected.append(phrase)
        if len(dictionary) >= max_entries:
            break
    if not dictionary:
        return CodecResult(text, True, {"marker": marker}, ["no profitable repeated phrases"])

    out: list[str] = []
    i = 0
    by_first: dict[str, list[tuple[int, tuple[str, ...]]]] = {}
    for idx, phrase in enumerate(selected):
        by_first.setdefault(phrase[0], []).append((idx, phrase))
    for choices in by_first.values():
        choices.sort(key=lambda item: len(item[1]), reverse=True)
    while i < len(toks):
        matched = False
        for idx, phrase in by_first.get(toks[i], []):
            n = len(phrase)
            if tuple(toks[i : i + n]) == phrase:
                out.append(f"§{idx}§")
                i += n
                matched = True
                break
        if not matched:
            out.append(toks[i])
            i += 1
    body = "".join(out)
    payload = "\n".join([marker, "dict=" + _j(dictionary), "@body", body])
    return CodecResult(payload, True, {"marker": marker}, [])


def _phrase_decompress(payload: str) -> str:
    head, dict_line, marker, body = payload.split("\n", 3)
    dictionary = json.loads(dict_line[5:])

    def repl(match: re.Match[str]) -> str:
        return dictionary[int(match.group(1))]

    return re.sub(r"§(\d+)§", repl, body)


class MetaTokensCodec(Codec):
    """LZ-style reusable textual meta-token dictionary."""

    name = "meta_tokens"

    def can_handle(self, value: object) -> bool:
        text = _as_text(value)
        return len(text) >= 700

    def compress(self, value: object) -> CodecResult:
        return _phrase_payload(META_TOKENS_MARKER, _as_text(value), min_count=3, max_entries=128)

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        return _phrase_decompress(payload)


class TokenLzCodec(Codec):
    """Tokenizer-aware phrase packing approximation using textual token spans."""

    name = "token_lz"

    def can_handle(self, value: object) -> bool:
        text = _as_text(value)
        return len(_tokens(text)) >= 120

    def compress(self, value: object) -> CodecResult:
        result = _phrase_payload(TOKEN_LZ_MARKER, _as_text(value), min_count=2, max_entries=64)
        result.metadata["tokenizer"] = "textual-token-proxy"
        return result

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        return _phrase_decompress(payload)


class SeparatorSegmentsCodec(Codec):
    """Exact dictionary for repeated separator-delimited segments."""

    name = "separator_segments"

    def can_handle(self, value: object) -> bool:
        text = _as_text(value)
        return len(text) >= 500 and ("\n\n" in text or "---\n" in text or text.count("\n") >= 20)

    def compress(self, value: object) -> CodecResult:
        text = _as_text(value)
        sep = "\n\n" if "\n\n" in text else "---\n" if "---\n" in text else "\n"
        parts = text.split(sep)
        dictionary: list[str] = []
        ids: dict[str, int] = {}
        seq: list[int] = []
        for part in parts:
            if part not in ids:
                ids[part] = len(dictionary)
                dictionary.append(part)
            seq.append(ids[part])
        if len(dictionary) > len(parts) * 0.8:
            return CodecResult(
                text, True, {"marker": SEPARATOR_SEGMENTS_MARKER}, ["too few repeated separator segments"]
            )
        payload = "\n".join(
            [SEPARATOR_SEGMENTS_MARKER, "sep=" + _j(sep), "dict=" + _j(dictionary), "seq=" + ",".join(map(str, seq))]
        )
        return CodecResult(payload, True, {"marker": SEPARATOR_SEGMENTS_MARKER}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        sep = json.loads(lines[1][4:])
        dictionary = json.loads(lines[2][5:])
        seq = [int(x) for x in lines[3][4:].split(",") if x]
        return sep.join(dictionary[i] for i in seq)


class GrammarCodec(Codec):
    """Small Re-Pair-style reversible grammar over textual tokens."""

    name = "grammar"

    def can_handle(self, value: object) -> bool:
        return len(_tokens(_as_text(value))) >= 150

    def compress(self, value: object) -> CodecResult:
        symbols = _tokens(_as_text(value))
        rules: list[tuple[str, str]] = []
        for _ in range(96):
            pairs = Counter(zip(symbols, symbols[1:], strict=False))
            if not pairs:
                break
            pair, count = max(
                pairs.items(),
                key=lambda item: (item[1] - 1) * (_token_cost(item[0][0]) + _token_cost(item[0][1])),
            )
            gain = (count - 1) * (_token_cost(pair[0]) + _token_cost(pair[1]))
            if count < 3 or gain <= _token_cost(_j(pair)) + 2:
                break
            new = f"¤{len(rules)}¤"
            rules.append(pair)
            rewritten: list[str] = []
            i = 0
            while i < len(symbols):
                if i + 1 < len(symbols) and (symbols[i], symbols[i + 1]) == pair:
                    rewritten.append(new)
                    i += 2
                else:
                    rewritten.append(symbols[i])
                    i += 1
            symbols = rewritten
        if not rules:
            return CodecResult(_as_text(value), True, {"marker": GRAMMAR_MARKER}, ["no repeated grammar pairs"])
        payload = "\n".join([GRAMMAR_MARKER, "rules=" + _j(rules), "body=" + _j(symbols)])
        return CodecResult(payload, True, {"marker": GRAMMAR_MARKER}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        rules = json.loads(lines[1][6:])
        symbols = json.loads(lines[2][5:])
        expanded = list(symbols)
        for idx in range(len(rules) - 1, -1, -1):
            marker = f"¤{idx}¤"
            a, b = rules[idx]
            nxt: list[str] = []
            for sym in expanded:
                if sym == marker:
                    nxt.extend([a, b])
                else:
                    nxt.append(sym)
            expanded = nxt
        return "".join(expanded)


def _flatten(value: object, path: str = "$") -> list[tuple[str, object]]:
    if isinstance(value, dict):
        out: list[tuple[str, object]] = []
        for key, child in value.items():
            out.extend(_flatten(child, f"{path}.{key}"))
        return out
    if isinstance(value, list):
        out = []
        for idx, child in enumerate(value):
            out.extend(_flatten(child, f"{path}[{idx}]"))
        return out
    return [(path, value)]


def _set_path(root: object, path: str, value: object) -> object:
    if path == "$":
        return value
    tokens = re.findall(r"\.([^\.\[]+)|\[(\d+)\]", path[1:])
    cur = root
    for pos, (key, idx) in enumerate(tokens):
        is_last = pos == len(tokens) - 1
        nxt_is_list = (not is_last) and bool(tokens[pos + 1][1])
        if key:
            if not isinstance(cur, dict):
                raise ValueError("invalid dict path")
            if is_last:
                cur[key] = value
            else:
                cur = cur.setdefault(key, [] if nxt_is_list else {})
        else:
            i = int(idx)
            if not isinstance(cur, list):
                raise ValueError("invalid list path")
            while len(cur) <= i:
                cur.append([] if nxt_is_list else {})
            if is_last:
                cur[i] = value
            else:
                cur = cur[i]
    return root


class PathDictRowsCodec(Codec):
    """Reversible JSON path dictionary plus leaf rows."""

    name = "path_dict_rows"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, dict | list) and len(_flatten(value)) >= 20

    def compress(self, value: object) -> CodecResult:
        if isinstance(value, dict) and isinstance(value.get("items"), list) and value["items"]:
            items = value["items"]
            rel_paths = [p for p, _ in _flatten(items[0])]
            rows = []
            for item in items:
                leaves = dict(_flatten(item))
                rows.append([leaves.get(p) for p in rel_paths])
            extras = {k: v for k, v in value.items() if k != "items"}
            payload = "\n".join(
                [
                    PATH_DICT_ROWS_MARKER,
                    "mode=items",
                    "extras=" + _j(extras),
                    "paths=" + _j(rel_paths),
                    "rows=" + _j(rows),
                ]
            )
            return CodecResult(payload, True, {"marker": PATH_DICT_ROWS_MARKER, "mode": "items"}, [])
        leaves = _flatten(value)
        paths = [p for p, _ in leaves]
        rows = [[idx, v] for idx, (_p, v) in enumerate(leaves)]
        payload = "\n".join(
            [
                PATH_DICT_ROWS_MARKER,
                "root=" + ("list" if isinstance(value, list) else "dict"),
                "paths=" + _j(paths),
                "rows=" + _j(rows),
            ]
        )
        return CodecResult(
            payload, True, {"marker": PATH_DICT_ROWS_MARKER, "root": "list" if isinstance(value, list) else "dict"}, []
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        if len(lines) > 1 and lines[1] == "mode=items":
            extras = json.loads(lines[2][7:])
            paths = json.loads(lines[3][6:])
            rows = json.loads(lines[4][5:])
            items = []
            for values in rows:
                item: object = {}
                for path, value in zip(paths, values, strict=False):
                    item = _set_path(item, path, value)
                items.append(item)
            out = dict(extras)
            out["items"] = items
            return out
        root: object = [] if lines[1] == "root=list" else {}
        paths = json.loads(lines[2][6:])
        rows = json.loads(lines[3][5:])
        for idx, value in rows:
            root = _set_path(root, paths[idx], value)
        return root


class TreeDictCodec(Codec):
    """Reversible repeated-subtree dictionary for JSON-like values."""

    name = "tree_dict"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, dict | list) and len(_j(value)) >= 700

    def compress(self, value: object) -> CodecResult:
        counts: Counter[str] = Counter()

        def collect(node: object) -> None:
            if isinstance(node, dict | list):
                txt = _j(node)
                if len(txt) > 40:
                    counts[txt] += 1
                children = node.values() if isinstance(node, dict) else node
                for child in children:
                    collect(child)

        collect(value)
        selected = [txt for txt, count in counts.most_common(64) if count >= 2]
        if not selected:
            return CodecResult(_j(value), True, {"marker": TREE_DICT_MARKER}, ["no repeated subtrees"])
        ids = {txt: f"T{idx}" for idx, txt in enumerate(selected)}
        dictionary = {ids[txt]: json.loads(txt) for txt in selected}

        def encode(node: object) -> object:
            txt = _j(node) if isinstance(node, dict | list) else None
            if txt in ids:
                return {"$ref": ids[txt]}
            if isinstance(node, dict):
                return {k: encode(v) for k, v in node.items()}
            if isinstance(node, list):
                return [encode(v) for v in node]
            return node

        payload = "\n".join([TREE_DICT_MARKER, "dict=" + _j(dictionary), "root=" + _j(encode(value))])
        return CodecResult(payload, True, {"marker": TREE_DICT_MARKER}, [])

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.splitlines()
        dictionary = json.loads(lines[1][5:])
        root = json.loads(lines[2][5:])

        def expand(node: object) -> object:
            if isinstance(node, dict) and set(node) == {"$ref"}:
                return expand(dictionary[node["$ref"]])
            if isinstance(node, dict):
                return {k: expand(v) for k, v in node.items()}
            if isinstance(node, list):
                return [expand(v) for v in node]
            return node

        return expand(root)


class SessionDeltaCodec(Codec):
    """Reversible base-context plus unified-diff delta codec."""

    name = "session_delta"

    def can_handle(self, value: object) -> bool:
        return isinstance(value, dict) and "base" in value and "current" in value

    def compress(self, value: object) -> CodecResult:
        assert isinstance(value, dict)
        base = _as_text(value["base"])
        current = _as_text(value["current"])
        import hashlib

        diff = list(
            difflib.unified_diff(
                base.splitlines(keepends=True), current.splitlines(keepends=True), fromfile="base", tofile="current"
            )
        )
        digest = hashlib.sha256(base.encode()).hexdigest()
        payload = "\n".join(
            [SESSION_DELTA_MARKER, f"base_sha256={digest} base_chars={len(base)}", "@diff", "".join(diff)]
        )
        return CodecResult(
            payload,
            True,
            {"marker": SESSION_DELTA_MARKER, "base": base, "base_sha256": digest},
            ["requires local base metadata for reversal"],
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        lines = payload.split("\n", 3)
        base = metadata.get("base")
        if not isinstance(base, str):
            raise ValueError("session_delta requires base metadata")
        diff = lines[3].splitlines(keepends=True) if len(lines) > 3 else []
        # Minimal unified-diff apply for diffs generated above.
        old = base.splitlines(keepends=True)
        out: list[str] = []
        old_idx = 0
        for line in diff:
            if line.startswith(("---", "+++")):
                continue
            if line.startswith("@@"):
                m = re.search(r"-(\d+)", line)
                start = int(m.group(1)) - 1 if m else old_idx
                out.extend(old[old_idx:start])
                old_idx = start
            elif line.startswith(" "):
                out.append(old[old_idx])
                old_idx += 1
            elif line.startswith("-"):
                old_idx += 1
            elif line.startswith("+"):
                out.append(line[1:])
        out.extend(old[old_idx:])
        return "".join(out)


class SidecarRefCodec(Codec):
    """Hash-backed externalized reversible payload with local metadata sidecar."""

    name = "sidecar_ref"

    def can_handle(self, value: object) -> bool:
        text = _as_text(value)
        return len(text) >= 3000

    def compress(self, value: object) -> CodecResult:
        text = _as_text(value)
        digest = __import__("hashlib").sha256(text.encode()).hexdigest()
        preview = text[:400].replace("\n", "\\n")
        payload = "\n".join([SIDECAR_REF_MARKER, f"sha256={digest} chars={len(text)}", "preview=" + preview])
        return CodecResult(
            payload,
            True,
            {"marker": SIDECAR_REF_MARKER, "sidecar": text, "sha256": digest},
            ["requires local sidecar metadata for reversal"],
        )

    def decompress(self, payload: str, metadata: dict[str, Any]) -> object:
        text = metadata.get("sidecar")
        if not isinstance(text, str):
            raise ValueError("sidecar_ref requires sidecar metadata")
        return text
