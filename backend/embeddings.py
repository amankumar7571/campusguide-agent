"""Embeddings.

Gemini embeddings (google-genai, `gemini-embedding-001`) ONLY when
GEMINI_API_KEY is set. Otherwise a local TF-IDF embedder (scikit-learn)
fit on the corpus — deterministic, no key, no network. The retrieval
layer treats both the same way (cosine similarity over vectors), so the
fallback is a genuine dense-search substitute at this corpus scale,
clearly labelled wherever it is used.
"""
import hashlib
import json
import time

import numpy as np

from .config import GEMINI_API_KEY

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
except ImportError:  # pragma: no cover
    TfidfVectorizer = None

# One embed_content call per chunk blew the Gemini free tier (100
# requests/min) at cold start: 107 chunks = 107 calls. Batching keeps a
# full-corpus embed to a handful of requests.
GEMINI_BATCH_SIZE = 25
_GEMINI_429_BACKOFF_SECONDS = (2, 4, 8, 16)
# The free-tier quota counts embedded *contents*, ~100/min: pacing the
# corpus build to ~75 contents/min (20s between 25-text batches) keeps a
# cold start under the limit. Only applies between batches of one embed()
# call; single-query embeds are unaffected.
GEMINI_BATCH_PAUSE_SECONDS = 20


class LocalTfidfEmbedder:
    """TF-IDF fallback embedder. Fit once on the corpus, then transform."""

    name = "tfidf-local"

    def __init__(self):
        self.vectorizer = None

    def fit(self, texts):
        if TfidfVectorizer is None:
            raise RuntimeError("scikit-learn is required for the local embedder")
        self.vectorizer = TfidfVectorizer(max_features=5000,
                                          ngram_range=(1, 2),
                                          stop_words="english")
        self.vectorizer.fit(texts)
        return self

    def embed(self, texts):
        if self.vectorizer is None:
            self.fit(texts)
        mat = self.vectorizer.transform(texts).toarray().astype(float)
        return [row / (np.linalg.norm(row) or 1.0) for row in mat]

    def embed_query(self, text):
        return self.embed([text])[0]


class GeminiEmbedder:
    """Gemini embeddings via the google-genai SDK. Key required.

    embed() sends texts in batches of GEMINI_BATCH_SIZE per API call
    (embed_content accepts a list) instead of one call per text, so a
    107-chunk corpus costs ~5 requests, not 107. Each batch retries on
    429 RESOURCE_EXHAUSTED with exponential backoff.
    """

    name = "gemini-embedding-001"

    def __init__(self, api_key: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)

    def _embed_batch(self, batch):
        last_exc = None
        for delay in (0,) + _GEMINI_429_BACKOFF_SECONDS:
            if delay:
                time.sleep(delay)
            try:
                res = self.client.models.embed_content(
                    model="gemini-embedding-001", contents=list(batch))
                return [np.array(e.values, dtype=float)
                        for e in res.embeddings]
            except Exception as exc:  # noqa: BLE001 - retry only on 429
                last_exc = exc
                if "429" not in str(exc) and getattr(exc, "code", None) != 429:
                    raise
        raise last_exc

    def embed(self, texts):
        texts = list(texts)
        out = []
        for i in range(0, len(texts), GEMINI_BATCH_SIZE):
            batch = texts[i:i + GEMINI_BATCH_SIZE]
            for vec in self._embed_batch(batch):
                out.append(vec / (np.linalg.norm(vec) or 1.0))
            if i + GEMINI_BATCH_SIZE < len(texts):
                time.sleep(GEMINI_BATCH_PAUSE_SECONDS)
        return out

    def embed_query(self, text):
        return self.embed([text])[0]


def get_embedder():
    """Gemini when a key is configured, else the documented local fallback."""
    if GEMINI_API_KEY:
        try:
            return GeminiEmbedder(GEMINI_API_KEY)
        except Exception:
            pass  # fall through to local on any Gemini init failure
    return LocalTfidfEmbedder()


def embedder_name():
    return "gemini-embedding-001" if GEMINI_API_KEY else "tfidf-local"
