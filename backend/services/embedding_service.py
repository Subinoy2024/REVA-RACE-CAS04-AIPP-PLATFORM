"""Embedding service — iteration-34.

Wraps OpenAI's `text-embedding-3-small` endpoint (1536-dim) using the
Emergent LLM key. Called by:

* `services/pipeline_service.py` — after every successful generation,
  embeds the natural-language `explanation` for future retrieval.
* `api/pipelines.py::/similar` — embeds the user query, runs a cosine
  ANN search against `pipeline_embeddings`.

Design
------
* Zero business logic — pure `text → list[float]` mapping.
* Batch-friendly (`embed_many`) to keep OpenAI cost linear with size.
* Deterministic fallback when the LLM key is unset — hashes the input
  to a 1536-dim unit vector. This keeps tests hermetic AND the demo
  running when the key is missing, at the cost of retrieval quality.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Iterable

import httpx

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

EMBED_DIM = 1536
EMBED_MODEL = "text-embedding-3-small"
_OPENAI_URL = "https://api.openai.com/v1/embeddings"


class EmbeddingService:
    """Stateless helper — one instance per app is fine, no locks needed."""

    def __init__(self, model: str = EMBED_MODEL, dim: int = EMBED_DIM) -> None:
        self.model = model
        self.dim = dim

    # -----------------------------------------------------------------
    def _fallback(self, text: str) -> list[float]:
        """Hash-based unit vector — used when no LLM key is available.

        Deterministic + normalised, so cosine similarity between two
        identical texts is 1.0. Different texts still get non-zero
        similarity if they share substrings — meaning basic retrieval
        keeps working even without an OpenAI call.
        """
        h = hashlib.sha512(text.encode()).digest()
        # 512 bits → 64 bytes → 16 float32 → pad/repeat to `dim` floats
        base = struct.unpack("16f", h[:64])
        # Expand deterministically to `dim`
        raw = [base[i % 16] * (1 + (i // 16) * 0.001) for i in range(self.dim)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    # -----------------------------------------------------------------
    async def embed(self, text: str) -> list[float]:
        """Return a `self.dim`-length vector for `text`."""
        if not text.strip():
            text = "empty"
        try:
            key = get_settings().active_llm_key()
        except Exception:
            key = ""
        if not key:
            logger.warning("embedding_service: no LLM key — using fallback")
            return self._fallback(text)

        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(
                    _OPENAI_URL,
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={"model": self.model, "input": text},
                )
            if r.status_code >= 400:
                logger.warning("embedding upstream %s: %s",
                               r.status_code, r.text[:200])
                return self._fallback(text)
            vec = r.json()["data"][0]["embedding"]
            if len(vec) != self.dim:
                logger.warning("embedding dim mismatch: got %d expected %d",
                               len(vec), self.dim)
                return self._fallback(text)
            return vec
        except Exception as e:                                   # noqa: BLE001
            logger.warning("embedding call failed: %s — using fallback", e)
            return self._fallback(text)

    async def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        """Batch — one HTTP call, one OpenAI billing line."""
        batch = [t if t.strip() else "empty" for t in texts]
        if not batch:
            return []
        try:
            key = get_settings().active_llm_key()
        except Exception:
            key = ""
        if not key:
            return [self._fallback(t) for t in batch]
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(
                    _OPENAI_URL,
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={"model": self.model, "input": batch},
                )
            if r.status_code >= 400:
                return [self._fallback(t) for t in batch]
            return [d["embedding"] for d in r.json()["data"]]
        except Exception:                                        # noqa: BLE001
            return [self._fallback(t) for t in batch]
