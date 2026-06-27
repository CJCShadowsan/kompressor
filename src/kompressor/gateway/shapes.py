"""Request-shape detection and text target adapters for gateway rewriting."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from kompressor.gateway.models import ContentSource, RequestFormat


@dataclass(frozen=True)
class TextTarget:
    path: str
    source: ContentSource
    text: str


def detect_request_format(request: dict[str, Any]) -> RequestFormat:
    if "messages" in request and ("system" in request or "anthropic-version" in request):
        return "anthropic"
    if "messages" in request or "input" in request:
        return "openai"
    return "unknown"


def _source_for_role(role: object) -> ContentSource | None:
    if role == "user":
        return "user_text"
    if role == "tool":
        return "tool_result"
    if role == "developer":
        return "developer_text"
    return None


def _iter_openai_content(content: Any, prefix: str, source: ContentSource) -> Iterable[TextTarget]:
    if isinstance(content, str):
        yield TextTarget(prefix, source, content)
    elif isinstance(content, list):
        for idx, block in enumerate(content):
            if (
                isinstance(block, dict)
                and block.get("type") in {"text", "input_text"}
                and isinstance(block.get("text"), str)
            ):
                yield TextTarget(f"{prefix}[{idx}].text", source, block["text"])


def _iter_anthropic_content(content: Any, prefix: str, source: ContentSource) -> Iterable[TextTarget]:
    if isinstance(content, str):
        yield TextTarget(prefix, source, content)
    elif isinstance(content, list):
        for idx, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                yield TextTarget(f"{prefix}[{idx}].text", source, block["text"])
            elif block.get("type") == "tool_result":
                tool_content = block.get("content")
                if isinstance(tool_content, str):
                    yield TextTarget(f"{prefix}[{idx}].content", "tool_result", tool_content)
                elif isinstance(tool_content, list):
                    for item_idx, item in enumerate(tool_content):
                        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                            yield TextTarget(f"{prefix}[{idx}].content[{item_idx}].text", "tool_result", item["text"])


def iter_text_targets(request: dict[str, Any], request_format: RequestFormat) -> Iterable[TextTarget]:
    messages = request.get("messages")
    if isinstance(messages, list):
        for msg_idx, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            source = _source_for_role(role)
            if source is None:
                continue
            content = message.get("content")
            prefix = f"messages[{msg_idx}].content"
            if request_format == "anthropic":
                yield from _iter_anthropic_content(content, prefix, source)
            else:
                yield from _iter_openai_content(content, prefix, source)
    responses_input = request.get("input")
    if isinstance(responses_input, list):
        for idx, item in enumerate(responses_input):
            if isinstance(item, dict):
                source = _source_for_role(item.get("role")) or "user_text"
                yield from _iter_openai_content(item.get("content"), f"input[{idx}].content", source)
            elif isinstance(item, str):
                yield TextTarget(f"input[{idx}]", "user_text", item)
    elif isinstance(responses_input, str):
        yield TextTarget("input", "user_text", responses_input)


def _parse_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    i = 0
    while i < len(path):
        if path[i] == ".":
            i += 1
            continue
        if path[i] == "[":
            end = path.index("]", i)
            tokens.append(int(path[i + 1 : end]))
            i = end + 1
            continue
        j = i
        while j < len(path) and path[j] not in ".[":
            j += 1
        tokens.append(path[i:j])
        i = j
    return tokens


def replace_text_target(request: dict[str, Any], target: TextTarget, text: str) -> dict[str, Any]:
    next_request = deepcopy(request)
    cursor: Any = next_request
    tokens = _parse_path(target.path)
    for token in tokens[:-1]:
        cursor = cursor[token]
    cursor[tokens[-1]] = text
    return next_request


def _instruction_text(base: str) -> str:
    return "KOMPRESSOR_GATEWAY_INSTRUCTIONS\n" + base.strip()


def inject_instructions(
    request: dict[str, Any],
    request_format: RequestFormat,
    text: str,
    *,
    anchor: str = "end",
) -> tuple[dict[str, Any], bool]:
    if not text.strip():
        return request, False
    marker = "KOMPRESSOR_GATEWAY_INSTRUCTIONS"
    serialized = str(request)
    if marker in serialized:
        return request, False
    next_request = deepcopy(request)
    instruction = _instruction_text(text)
    if request_format == "anthropic":
        system = next_request.get("system")
        if system is None:
            next_request["system"] = instruction
        elif isinstance(system, str):
            next_request["system"] = f"{system}\n\n{instruction}" if anchor == "end" else f"{instruction}\n\n{system}"
        elif isinstance(system, list):
            block = {"type": "text", "text": instruction}
            next_request["system"] = [*system, block] if anchor == "end" else [block, *system]
        else:
            next_request["system"] = f"{system}\n\n{instruction}"
        return next_request, True
    if "input" in next_request and "messages" not in next_request:
        existing_input = next_request.get("input")
        instruction_item = {"role": "system", "content": instruction}
        if isinstance(existing_input, list):
            next_request["input"] = [instruction_item, *existing_input]
        elif isinstance(existing_input, str):
            next_request["input"] = f"{instruction}\n\n{existing_input}"
        else:
            next_request["input"] = [instruction_item]
        return next_request, True
    messages = list(next_request.get("messages") or [])
    block = {"role": "system", "content": instruction}
    if anchor == "beginning":
        messages.insert(0, block)
    else:
        inserted = False
        for idx, message in enumerate(messages):
            if (
                isinstance(message, dict)
                and message.get("role") == "system"
                and isinstance(message.get("content"), str)
            ):
                message = dict(message)
                message["content"] = f"{message['content']}\n\n{instruction}"
                messages[idx] = message
                inserted = True
                break
        if not inserted:
            messages.insert(0, block)
    next_request["messages"] = messages
    return next_request, True
