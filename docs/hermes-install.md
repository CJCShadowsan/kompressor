# Installing Kompressor into Hermes

Kompressor ships a native Hermes plugin and an explicit compatibility patch for
Hermes Codex runtimes that need an `llm_request` middleware bridge.

## Recommended install

Use an isolated CLI install:

```bash
pipx install kompressor
kompressor hermes install --prove
```

For a source checkout:

```bash
git clone https://github.com/CJCShadowsan/kompressor.git
cd kompressor
python -m pip install -e .
kompressor hermes install --prove
```

## What the installer does

`kompressor hermes install --prove` is explicit and idempotent. It:

1. Locates Hermes and the active Hermes home (`$HERMES_HOME` or `~/.hermes`).
2. Copies the packaged plugin to `~/.hermes/plugins/kompressor`.
3. Writes `config.json` so the Hermes plugin can import this Kompressor install.
4. Enables the plugin with `hermes plugins enable kompressor`.
5. Applies the reversible Codex middleware bridge if this Hermes checkout needs it.
6. Runs a new one-shot Hermes proof session and checks for a compression proof event.

It does not mutate Hermes during `pip install`; the user must explicitly run the
installer command.

## Useful commands

```bash
kompressor hermes status
kompressor hermes install --prove
kompressor hermes prove
kompressor hermes uninstall
```

Use a custom Hermes home or source checkout:

```bash
kompressor hermes install \
  --hermes-home ~/.hermes \
  --hermes-agent-dir ~/.hermes/hermes-agent \
  --prove
```

Remove the plugin:

```bash
kompressor hermes uninstall
```

Remove the plugin and a Kompressor-managed Codex bridge patch:

```bash
kompressor hermes uninstall --remove-patch
```

## Expected proof output

A successful proof reports `ok: yes` and a JSON proof event similar to:

```json
{
  "strategy": "json_table",
  "original_chars": 6980,
  "compressed_chars": 4355,
  "saved_chars": 2625
}
```

That proves a fresh Hermes session received raw structured input, the native
Kompressor plugin rewrote it before provider dispatch, and the model answered
from the compressed context.
