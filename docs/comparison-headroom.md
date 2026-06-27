# Kompressor Gateway vs Headroom

Kompressor Gateway intentionally borrows Headroom's useful product shape: a local proxy, wrappers, retrieval, and stats. The implementation remains Kompressor-native:

- codecs remain deterministic/provider-neutral
- default mode is strict and reversible
- externalized content is retrieved by digest
- local-decode compression is explicit
- lossy summaries are opt-in
- proof and benchmark artifacts label what they do and do not prove

Headroom is a broader context operating layer. Kompressor Gateway is a stricter compression gateway with auditable policy boundaries.

Recommended positioning:

> Kompressor Gateway gives Kompressor Headroom-like deployment ergonomics while preserving Kompressor's explicit reversibility classes and benchmark discipline. It is not a provider tokenizer replacement and does not claim provider billing savings without provider usage metadata.
