# Kompressor Context Gateway

Kompressor Gateway is a local OpenAI/Anthropic-compatible request gateway. It keeps Kompressor's codec engine provider-neutral while adding Headroom-like deployment ergonomics: proxying, retrieval-backed originals, stats, wrappers, and proof scripts.

## Strict defaults

Default mode is `strict`:

- prompt-readable reversible compression is allowed
- externalized references require retrieval support
- local-decode transport compression is disabled unless explicitly selected
- lossy analytical codecs are disabled unless explicitly selected
- stats do not store raw payload text

## Serve

```bash
kompressor gateway serve \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream https://api.openai.com \
  --mode strict \
  --store-dir ~/.kompressor/store
```

Supported proxy paths:

- `POST /v1/messages`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/kompressor/retrieve/<sha256>`
- `GET /v1/kompressor/stats`
- `GET /healthz`

## Rewrite proof

```bash
python scripts/gateway_proof.py --out artifacts/proof/gateway-offline.json
```

This proves offline that raw input enters the gateway, the fake upstream receives rewritten compact context, and exact original text is retrievable by digest.

## Benchmark

```bash
python scripts/gateway_benchmark.py --out artifacts/bench/gateway
```

Benchmark metrics are character-count estimates unless explicitly backed by provider usage metadata.
