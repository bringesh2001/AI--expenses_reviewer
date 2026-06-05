"""Voyage AI embeddings wrapper with retry and batching.

Voyage AI free tier: 200M tokens free for new accounts.
Sign up at: https://dash.voyageai.com/
Model: voyage-3 (1024-dim, best quality on free tier)
"""
from functools import lru_cache
import voyageai
from tenacity import retry, wait_exponential, stop_after_attempt
from ..config import settings


@lru_cache(maxsize=1)
def _client() -> voyageai.Client:
    return voyageai.Client(api_key=settings.voyage_api_key)


@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return embeddings for a list of texts. Batches up to 128 at a time (Voyage limit)."""
    if not texts:
        return []
    import asyncio
    client = _client()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), 128):
        batch = texts[i : i + 128]
        result = await asyncio.to_thread(
            client.embed,
            batch,
            model=settings.embedding_model,
            input_type="document",
        )
        all_embeddings.extend(result.embeddings)
    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """Embed a single query string (uses query input_type for better retrieval)."""
    import asyncio
    client = _client()
    result = await asyncio.to_thread(
        client.embed,
        [text],
        model=settings.embedding_model,
        input_type="query",
    )
    return result.embeddings[0]
