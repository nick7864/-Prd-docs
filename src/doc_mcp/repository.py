"""Pure-Python document repository logic.

Separated from server.py for unit testability — MCP protocol overhead is in
server.py, all file/embedding logic lives here so tests can call directly.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any

import frontmatter

# Repository root = Project/ (parent of src/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRDS_DIR = REPO_ROOT / "data" / "prds"
ARCH_DIR = REPO_ROOT / "data" / "architecture"
ADR_DIR = ARCH_DIR / "adr"

# Embedding cache location (D2.6 — index persistence)
INDEX_PATH = REPO_ROOT / "openspec" / ".vector-search.db.json"

# Google embedding model — text-embedding-004 is the current GA model.
EMBED_MODEL = "text-embedding-004"


def list_prds() -> list[dict[str, Any]]:
    """Scan ``data/prds/*.md`` and return per-PRD metadata.

    Returns an empty list (not an error) when the directory is missing or empty,
    per spec requirement "list_prds tool SHALL return available PRD metadata".
    """
    if not PRDS_DIR.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(PRDS_DIR.glob("*.md")):
        try:
            post = frontmatter.load(path)
        except Exception:
            # Skip malformed file rather than crashing the whole listing.
            continue
        results.append(
            {
                "id": str(post.metadata.get("id", path.stem)),
                "title": str(post.metadata.get("title", "")),
                "status": str(post.metadata.get("status", "")),
                "updated_at": str(post.metadata.get("updated_at", "")),
            }
        )
    return results


def get_prd(prd_id: str) -> dict[str, Any]:
    """Return full PRD content by identifier.

    Tries ``<prd_id>.md`` first (filename match), then scans frontmatter ``id``
    field. Returns ``{"error": "PRD not found: <id>"}`` on miss — never raises,
    per spec requirement "get_prd tool SHALL return full PRD content by identifier".
    """
    direct = PRDS_DIR / f"{prd_id}.md"
    post = None
    if direct.exists():
        post = frontmatter.load(direct)
    else:
        # Fallback: scan by frontmatter id (file may be named with a suffix).
        for path in PRDS_DIR.glob("*.md"):
            try:
                candidate = frontmatter.load(path)
            except Exception:
                continue
            if str(candidate.metadata.get("id")) == prd_id:
                post = candidate
                break
    if post is None:
        return {"error": f"PRD not found: {prd_id}"}
    return {
        "id": str(post.metadata.get("id")),
        "title": str(post.metadata.get("title")),
        "content": post.content,
        "metadata": {k: str(v) for k, v in post.metadata.items()},
    }


def get_architecture_context() -> dict[str, Any]:
    """Return architecture doc + up to 3 most recent ADRs.

    Per spec: returns ``{"architecture_doc": str, "adrs": [...]}``. Empty ADR
    directory yields ``adrs: []`` with ``architecture_doc`` still populated.
    """
    architecture_doc = ""
    arch_path = ARCH_DIR / "architecture.md"
    if arch_path.exists():
        post = frontmatter.load(arch_path)
        architecture_doc = post.content

    adrs: list[dict[str, Any]] = []
    if ADR_DIR.exists():
        adr_paths = sorted(ADR_DIR.glob("*.md"))
        # Parse once each; sort by frontmatter date desc, take 3, re-sort by id asc.
        parsed: list[frontmatter.Post] = []
        for path in adr_paths:
            try:
                parsed.append(frontmatter.load(path))
            except Exception:
                continue
        parsed.sort(key=lambda p: str(p.metadata.get("date", "")), reverse=True)
        recent = parsed[:3]
        recent.sort(key=lambda p: str(p.metadata.get("id", "")))
        for post in recent:
            adrs.append(
                {
                    "id": str(post.metadata.get("id")),
                    "title": str(post.metadata.get("title")),
                    "status": str(post.metadata.get("status")),
                    "content": post.content,
                }
            )

    return {"architecture_doc": architecture_doc, "adrs": adrs}


def get_similar_prds(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Semantic search over historical PRDs.

    Uses Gemini embeddings when ``GOOGLE_API_KEY``/``GEMINI_API_KEY`` is set;
    falls back to keyword-overlap scoring otherwise so the pipeline still works
    in offline / no-key states. Per spec: returns up to ``top_k`` results sorted
    by descending ``similarity_score``.
    """
    all_prds = list_prds()
    if not all_prds:
        return []
    if top_k <= 0:
        return []

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _keyword_ranking(query, all_prds, top_k)
    try:
        return _embedding_ranking(query, all_prds, top_k, api_key)
    except Exception as exc:
        # Graceful degradation: never crash the pipeline over a missing embed call.
        print(
            f"[repository] embedding search failed ({exc!r}); falling back to keyword ranking",
            file=sys.stderr,
        )
        return _keyword_ranking(query, all_prds, top_k)


# ---------------------------------------------------------------------------
# Ranking strategies
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "be", "shall", "will", "this", "that", "it", "as", "by",
    "we", "our", "i", "you", "your",
}


def _tokenize(text: str) -> set[str]:
    tokens = []
    for raw in text.lower().split():
        cleaned = "".join(c for c in raw if c.isalnum())
        if cleaned and cleaned not in _STOPWORDS and len(cleaned) > 2:
            tokens.append(cleaned)
    return set(tokens)


def _keyword_ranking(
    query: str, prds_meta: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    query_terms = _tokenize(query)
    if not query_terms:
        return [dict(meta) for meta in prds_meta[:top_k]]

    scored: list[dict[str, Any]] = []
    for meta in prds_meta:
        full = get_prd(str(meta["id"]))
        if "error" in full:
            continue
        content_terms = _tokenize(str(full.get("content", "")) + " " + str(full.get("title", "")))
        overlap = len(query_terms & content_terms)
        score = overlap / len(query_terms)
        scored.append({**meta, "similarity_score": round(score, 4)})

    scored.sort(key=lambda r: r["similarity_score"], reverse=True)
    return scored[:top_k]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embedding_ranking(
    query: str,
    prds_meta: list[dict[str, Any]],
    top_k: int,
    api_key: str,
) -> list[dict[str, Any]]:
    from google import genai  # local import: keeps no-key path lightweight

    client = genai.Client(api_key=api_key)
    cache = _load_cache()

    # Build document texts; check cache for each PRD by content hash.
    docs: list[dict[str, Any]] = []
    uncached_texts: list[str] = []
    uncached_indices: list[int] = []

    for i, meta in enumerate(prds_meta):
        full = get_prd(str(meta["id"]))
        text = str(full.get("content", "")) + "\n" + str(full.get("title", ""))
        chash = _content_hash(text)
        cache_key = f"{meta['id']}:{chash}"

        cached_entry = cache.get("embeddings", {}).get(cache_key)
        if cached_entry and "embedding" in cached_entry:
            docs.append({
                "id": meta["id"],
                "title": meta["title"],
                "text": text,
                "embedding": cached_entry["embedding"],
            })
        else:
            docs.append({
                "id": meta["id"],
                "title": meta["title"],
                "text": text,
                "embedding": None,
            })
            uncached_texts.append(text)
            uncached_indices.append(i)

    # Batch-embed only the uncached docs (incremental update per spec D2.6).
    if uncached_texts:
        docs_resp = client.models.embed_content(
            model=EMBED_MODEL, contents=uncached_texts
        )
        for idx, emb in zip(uncached_indices, docs_resp.embeddings, strict=True):
            vec = list(emb.values)
            docs[idx]["embedding"] = vec
            chash = _content_hash(docs[idx]["text"])
            cache_key = f"{docs[idx]['id']}:{chash}"
            cache.setdefault("embeddings", {})[cache_key] = {
                "id": docs[idx]["id"],
                "title": docs[idx]["title"],
                "embedding": vec,
            }
        _save_cache(cache)

    # Embed query (always fresh — queries are not cached).
    query_resp = client.models.embed_content(model=EMBED_MODEL, contents=query)
    query_vec = list(query_resp.embeddings[0].values)

    scored: list[dict[str, Any]] = []
    for doc in docs:
        score = _cosine(query_vec, doc["embedding"])
        scored.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "similarity_score": round(score, 4),
            }
        )
    scored.sort(key=lambda r: r["similarity_score"], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# Embedding cache (D2.6 — persist vector search index across restarts)
# ---------------------------------------------------------------------------


def _content_hash(text: str) -> str:
    """SHA-256 hash of text content, truncated for cache-key readability."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_cache() -> dict[str, Any]:
    """Load the persisted embedding cache from ``INDEX_PATH``.

    Returns ``{"version": 1, "embeddings": {}}`` when the file is missing or
    corrupted — never raises, so cold start is always safe.
    """
    import json
    if INDEX_PATH.exists():
        try:
            data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "embeddings" in data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "embeddings": {}}


def _save_cache(cache: dict[str, Any]) -> None:
    """Persist the embedding cache to ``INDEX_PATH`` (creates parent dir)."""
    import json
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(cache, ensure_ascii=False), encoding="utf-8"
    )
