# Benchmark Methodology

Kompressor publishes estimated savings only when benchmark artifacts are generated from repository fixtures or user-supplied corpora.

Metrics:

- baseline characters
- optimized characters
- baseline estimated tokens
- optimized estimated tokens
- percent saved
- estimator label
- selected strategy
- reversibility

The default estimator is `char_proxy`, which is deterministic but not an exact provider billing measurement. Provider-specific estimators, such as Anthropic count-token integration, must label provider, model, and date. README claims must stay below measured benchmark evidence.
