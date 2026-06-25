# Kompressor Architecture

Kompressor is a client-side pre-flight optimizer for LLM harnesses. It cannot modify any provider's internal tokenizer or billing rules. Instead, it transforms verbose structured context into compact, reversible text formats before a caller submits that context to a model, agent, or chat harness.

Pipeline:

1. Classify input as JSON, XML, repeated text/logs, bytes, or plain text.
2. Try safe codecs and validate reversible decompression locally.
3. Estimate raw versus optimized token and cost footprint.
4. Generate provider-neutral decompression instructions.
5. Package instructions and payload through a harness adapter.
6. Attach optimization to a harness plugin hook when transparent operation is available.
7. Expose the result through the Python API, CLI, and dry-run proxy helpers.

Harness adapters are intentionally thin. The compressed payload is universal; adapters decide where instructions belong:

- Claude: `system` plus user content.
- OpenAI: developer message plus user content.
- Gemini: `system_instruction` plus contents.
- Hermes: task-local parsing rules in a single prompt suitable for `hermes chat -q` or a project workflow.
- Codex: developer instructions plus compressed agent input.
- Generic: plain text instructions and payload.

Plugins provide lifecycle integration for every supported harness. A native plugin can run before user messages, before tool results enter model context, or before an API request is dispatched. Wrapper shims are fallback integrations for one-shot prompts only; they cannot reliably intercept later interactive turns or internal tool outputs.

Security defaults are fail-closed: proxy helpers refuse suspected secrets unless redaction or explicit override is selected, and raw payload logging is not enabled by default.
