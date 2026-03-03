"""Hybrid retrieval engine combining vector and BM25 search.

Implements Reciprocal Rank Fusion (RRF) to merge results from
semantic vector search and keyword-based BM25 search.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from rank_bm25 import BM25Okapi

from hivecore.memory.types import MemorySearchResult

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Combines vector similarity search with BM25 keyword search.

    Uses Reciprocal Rank Fusion (RRF) to produce a unified ranking
    from two different retrieval signals:
    - Vector search: captures semantic meaning
    - BM25: captures exact keyword matches

    The balance between the two is controlled by vector_weight and bm25_weight.
    """

    def __init__(
        self,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        rrf_k: int = 60,
    ) -> None:
        """Initialize the hybrid retriever.

        Args:
            vector_weight: Weight for vector search results (0-1).
            bm25_weight: Weight for BM25 results (0-1).
            rrf_k: RRF constant (higher = more uniform weighting).
        """
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k

    def merge_results(
        self,
        vector_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Merge vector and BM25 results using Reciprocal Rank Fusion.

        Args:
            vector_results: Results from vector search (sorted by score desc).
            bm25_results: Results from BM25 search (sorted by score desc).
            top_k: Number of final results.

        Returns:
            Merged results sorted by combined RRF score.
        """
        scores: dict[str, float] = {}
        entries: dict[str, dict[str, Any]] = {}

        # Score vector results
        for rank, result in enumerate(vector_results):
            entry_id = result["id"]
            rrf_score = self.vector_weight / (self.rrf_k + rank + 1)
            scores[entry_id] = scores.get(entry_id, 0) + rrf_score
            entries[entry_id] = result

        # Score BM25 results
        for rank, result in enumerate(bm25_results):
            entry_id = result["id"]
            rrf_score = self.bm25_weight / (self.rrf_k + rank + 1)
            scores[entry_id] = scores.get(entry_id, 0) + rrf_score
            if entry_id not in entries:
                entries[entry_id] = result

        # Sort by combined score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        results = []
        for entry_id in sorted_ids[:top_k]:
            entry = entries[entry_id]
            entry["score"] = scores[entry_id]
            entry["retrieval_source"] = "hybrid"
            results.append(entry)

        return results


class BM25Index:
    """In-memory BM25 index for keyword search over memory entries.

    Builds and maintains a BM25 index from memory contents
    for fast keyword-based retrieval.
    """

    def __init__(self) -> None:
        self._documents: list[dict[str, Any]] = []
        self._tokenized: list[list[str]] = []
        self._bm25: Optional[BM25Okapi] = None

    def build(self, documents: list[dict[str, Any]]) -> None:
        """Build the BM25 index from a list of documents.

        Args:
            documents: List of dicts with 'id' and 'content' keys.
        """
        self._documents = documents
        self._tokenized = [_tokenize(doc["content"]) for doc in documents]

        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)
        else:
            self._bm25 = None

        logger.debug("BM25 index built with %d documents", len(documents))

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Search the BM25 index.

        Args:
            query: Search query.
            top_k: Number of results.

        Returns:
            List of result dicts with scores.
        """
        if self._bm25 is None or not self._documents:
            return []

        query_tokens = _tokenize(query)
        scores = self._bm25.get_scores(query_tokens)

        # Get top-k indices
        scored_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        results = []
        for idx in scored_indices:
            if scores[idx] > 0:
                doc = self._documents[idx].copy()
                doc["score"] = float(scores[idx])
                results.append(doc)

        return results

    def add_document(self, document: dict[str, Any]) -> None:
        """Add a single document to the index (rebuilds index).

        For frequent additions, batch with build() instead.

        Args:
            document: Dict with 'id' and 'content' keys.
        """
        self._documents.append(document)
        self._tokenized.append(_tokenize(document["content"]))
        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)

    @property
    def size(self) -> int:
        """Number of documents in the index."""
        return len(self._documents)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer with lowercasing and basic cleanup."""
    import re
    # Remove punctuation, lowercase, split on whitespace
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return [token for token in text.split() if len(token) > 1]
