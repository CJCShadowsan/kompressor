# CI Integration

The GitHub Actions example runs `kompressor bench tests/fixtures` and uploads benchmark output as an artifact. It is optional and intended as a template for diagnostic bundles, not a required workflow.

Secrets should be redacted before compression. CI should not run live Anthropic calls unless credentials and policy explicitly allow it.
