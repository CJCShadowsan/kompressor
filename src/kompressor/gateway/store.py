"""Content-addressed original payload store for gateway retrieval."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kompressor.gateway.models import ContentSource, StoredOriginal


def default_store_dir() -> Path:
    return Path(os.environ.get("KOMPRESSOR_STORE_DIR", Path.home() / ".kompressor" / "store")).expanduser()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


class OriginalStore:
    """A small hash-addressed text store with sidecar metadata."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).expanduser() if root is not None else default_store_dir()
        self.blob_root = self.root / "blobs" / "sha256"
        self.index_root = self.root / "index"

    def _blob_path(self, digest: str) -> Path:
        return self.blob_root / digest[:2] / f"{digest}.txt"

    def _meta_path(self, digest: str) -> Path:
        return self.index_root / f"{digest}.json"

    def put_text(
        self,
        text: str,
        *,
        source: ContentSource,
        content_type: str = "text/plain",
        metadata: dict[str, Any] | None = None,
    ) -> StoredOriginal:
        digest = _sha256(text)
        blob = self._blob_path(digest)
        meta = self._meta_path(digest)
        blob.parent.mkdir(parents=True, exist_ok=True)
        meta.parent.mkdir(parents=True, exist_ok=True)
        if not blob.exists():
            tmp = blob.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(blob)
        stored = StoredOriginal(
            digest=digest,
            chars=len(text),
            content_type=content_type,
            source=source,
            created_at=datetime.now(UTC).isoformat(),
            preview=text[:120].replace("\n", "\\n"),
            metadata=metadata or {},
        )
        tmp_meta = meta.with_suffix(".tmp")
        tmp_meta.write_text(json.dumps(stored.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_meta.replace(meta)
        return stored

    def has(self, digest: str) -> bool:
        return self._blob_path(digest).exists()

    def get_text(self, digest: str) -> str:
        path = self._blob_path(digest)
        if not path.exists():
            raise KeyError(f"unknown stored original digest: {digest}")
        return path.read_text(encoding="utf-8")

    def get_metadata(self, digest: str) -> StoredOriginal:
        path = self._meta_path(digest)
        if not path.exists():
            raise KeyError(f"unknown stored original metadata: {digest}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StoredOriginal(**payload)
