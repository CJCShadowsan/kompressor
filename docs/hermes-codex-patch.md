# Hermes Codex Compatibility Patch

Kompressor does not mutate Hermes during `pip install`. The Hermes Codex app-server
runtime may bypass Hermes `llm_request` middleware on some versions, which means a
native Kompressor plugin cannot rewrite the final model request on that path.

Kompressor ships an explicit, reversible compatibility patch for that case.

## Commands

Check status:

```bash
kompressor hermes patch status
kompressor hermes patch status --json
```

Apply the patch:

```bash
kompressor hermes patch apply
```

Remove a Kompressor-managed patch:

```bash
kompressor hermes patch uninstall
```

Print the native proof recipe:

```bash
kompressor hermes patch prove
```

Use a non-default Hermes checkout:

```bash
kompressor hermes patch status --hermes-agent-dir /path/to/hermes-agent
```

## Safety Properties

- No install-time source mutation.
- The user must explicitly run `kompressor hermes patch apply`.
- The patch applies only when `agent/codex_runtime.py` contains the expected
  Hermes Codex runtime anchor.
- A timestamped backup is written under:

```text
~/.kompressor/patches/hermes/
```

- The patch is marker-bounded:

```python
# BEGIN KOMPRESSOR HERMES CODEX MIDDLEWARE BRIDGE
...
# END KOMPRESSOR HERMES CODEX MIDDLEWARE BRIDGE
```

- `python -m py_compile` runs after apply/uninstall.
- If Hermes already includes an equivalent upstream bridge, status reports that
  the patch is not needed and apply is a no-op.

## What the Patch Does

The patch bridges Hermes `llm_request` middleware into the Codex app-server path
before `agent._codex_session.run_turn(user_input=user_message)`. It leaves the
persisted Hermes transcript alone and rewrites only the effective user input sent
to the model runtime.

That lets the native Kompressor Hermes plugin prove this path:

```text
raw Hermes user message
-> Hermes llm_request middleware
-> Kompressor compresses structured context
-> Codex runtime receives compressed task-local Hermes bundle
-> model answers correctly
```

## Removal

Once Hermes upstream includes the middleware bridge, run:

```bash
kompressor hermes patch status
kompressor hermes patch uninstall
```

If status says `Hermes already contains a Codex llm_request middleware bridge`,
no Kompressor-managed patch is needed.
