# Claude Code and claudish integration

Kompressor supports Claude-family workflows in three layers:

1. Claude harness packaging: `kompressor compress --harness claude` and `kompressor plugin preflight claude` build Claude/Anthropic-style compact context with parsing instructions.
2. Claude Code / claudish shims: `kompressor claude-code ... --mode shim` owns the one-shot prompt/stdin path so the original large context is replaced by Kompressor output before `claude` or `claudish` is invoked.
3. Anthropic request proxy: `kompressor claude-code proxy` rewrites Claude Code `/v1/messages` requests before provider dispatch. This is the recommended path for Hermes-like token savings in Claude Code because it removes the original large text from the outgoing provider request.

## Install shims

```bash
kompressor claude-code install --target both --mode shim --prove
```

This writes managed scripts by default:

- `~/.local/bin/kompressor-claude`
- `~/.local/bin/kompressor-claudish`

The scripts are thin wrappers over:

```bash
kompressor claude-code run --target claude ...
kompressor claude-code run --target claudish ...
```

Check status:

```bash
kompressor claude-code status
```

Remove them:

```bash
kompressor claude-code uninstall
```

## Anthropic request proxy

Install proxy wrappers:

```bash
kompressor claude-code install --target both --mode proxy --port 8765
```

This writes managed scripts:

- `~/.local/bin/kompressor-claude-proxy`
- `~/.local/bin/kompressor-claudish-proxy`

Run the proxy directly:

```bash
kompressor claude-code proxy --port 8765 --upstream https://api.anthropic.com
ANTHROPIC_BASE_URL=http://127.0.0.1:8765 claude -p "Summarize this project"
```

Or use the wrapper, which starts the proxy, exports `ANTHROPIC_BASE_URL`, runs Claude Code, then stops the proxy:

```bash
kompressor-claude-proxy -p "Summarize this project"
```

Proxy rewrite behavior:

- compresses large string user messages
- compresses large `{"type":"text"}` user content blocks
- compresses large `tool_result.content` string and text blocks
- appends Kompressor parsing instructions to Anthropic `system`
- preserves assistant `tool_use` blocks, images, documents, tool schemas, and non-text blocks
- skips already-compressed Kompressor payloads

## Run with claudish

```bash
kompressor claude-code run path/to/large-context.json \
  --target claudish \
  --model ollama@qwen2.5:3b \
  --task "Find auth failures"
```

Equivalent installed shim form:

```bash
kompressor-claudish path/to/large-context.json \
  --model ollama@qwen2.5:3b \
  --task "Find auth failures"
```

## Run with Claude Code

```bash
kompressor claude-code run path/to/large-context.json \
  --target claude \
  --task "Find auth failures"
```

Equivalent installed shim form:

```bash
kompressor-claude path/to/large-context.json \
  --task "Find auth failures"
```

For safety, Kompressor passes `--tools ""` to `claude -p` by default. Use `--allow-tools` when you intentionally want Claude Code tools enabled.

## Proof

Structural proof, no provider credentials required:

```bash
kompressor claude-code prove
```

Live proof through claudish:

```bash
kompressor claude-code prove \
  --target claudish \
  --model ollama@qwen2.5:3b \
  --live
```

The live proof builds a known fixture, compresses it with the Claude plugin path, asks the model to decode a value from the compact context, and checks the answer against the oracle.

## Native Claude Code hook investigation

Claude Code exposes a plugin system with commands such as:

```bash
claude plugin validate <path>
claude plugin install <plugin>
claude plugin list
```

Locally observed installed plugins define hook manifests like:

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "node ..."}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "node ..."}]}],
    "PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "node ..."}]}],
    "PostToolUse": [{"matcher": "Read|Write|Edit|Bash", "hooks": [{"type": "command", "command": "node ..."}]}],
    "PreCompact": [{"hooks": [{"type": "command", "command": "node ..."}]}]
  }
}
```

Useful hook events found:

- `UserPromptSubmit`
- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PreCompact`

Current conclusion: the hook API is useful for observation, guardrails, logging, context injection, and tool lifecycle workflows, but this repository does not yet have evidence that `UserPromptSubmit` can replace the submitted prompt before Claude Code builds the provider request.

Prompt replacement matters because Kompressor saves tokens only if the original large payload is not also sent. A hook that appends compressed context while Claude Code still sends the original prompt would not provide Hermes-equivalent savings.

Therefore the recommended Claude Code integration mode is now `proxy` for Anthropic-compatible Claude Code sessions:

```text
Claude Code /v1/messages request
  -> Kompressor Anthropic proxy
  -> rewritten compressed user/tool-result text + system parsing instructions
  -> real Anthropic upstream
```

The `shim` mode remains supported for one-shot file/stdin workflows, especially claudish/local model runs:

```text
context file + task
  -> Kompressor Claude plugin preflight
  -> compressed prompt
  -> claude/claudish stdin
```

Future native integration work should first prove one of these contracts:

1. `UserPromptSubmit` can replace the user prompt before model dispatch; or
2. Claude Code exposes request middleware equivalent to Hermes `llm_request`; or
3. Claude Code can be routed through a provider proxy where request messages can be rewritten before dispatch.

Until one of those is proven, native plugins should be treated as complementary telemetry/guardrail integration rather than a Hermes-equivalent token-saving path.
