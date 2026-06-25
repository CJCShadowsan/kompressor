# Release Checklist

Before tagging `v0.1.0`:

```bash
python -m pytest --cov=kompressor
python -m ruff check .
python -m ruff format --check .
python -m build
python -m venv /tmp/kompressor-smoke
/tmp/kompressor-smoke/bin/python -m pip install dist/*.whl
/tmp/kompressor-smoke/bin/kompressor --help
kompressor bench tests/fixtures --format markdown --output docs/benchmarks.md
```

Record whether live Anthropic count-token verification was run. If `ANTHROPIC_API_KEY` is absent, state that live token counting was not run.
