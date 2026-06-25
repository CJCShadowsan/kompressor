# Developer CLI Integration

Use `kompressor analyze` to inspect savings before sending logs or configs to an LLM harness.

Example:

```bash
kompressor analyze tests/fixtures/logs.json
kompressor compress tests/fixtures/logs.json --harness generic --output /tmp/context.txt
kompressor compress tests/fixtures/logs.json --harness hermes --output /tmp/hermes-context.txt
kompressor plugin list
kompressor plugin preflight codex tests/fixtures/logs.json --task "Review failures" --output /tmp/codex-context.txt
```

The git-hook example in `examples/git-hook/pre-claude-context` writes to `/tmp` by default and does not mutate repository files. The filename is retained for backward compatibility; the command can target any supported harness.
