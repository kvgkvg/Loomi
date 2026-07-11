"""Task -> ranked related assets. Public entrypoint: recommend()."""
import logging

from db.client import get_pg_connection, get_vector_collection
from recommend.scoring import compute

logger = logging.getLogger(__name__)

_OVERFETCH = 20


def recommend(task_description: str, top_k: int = 5) -> list[dict]:
    """See spec: returns list of asset dicts sorted desc by score. Never raises.

    Embeddings are Chroma-managed: we pass the raw query text and Chroma embeds
    it with the same default model used to index assets, so cosine is comparable.
    """
    try:
        if not task_description or not task_description.strip():
            return []

        col = get_vector_collection()
        if col.count() == 0:
            return []

        hits = col.query(query_texts=[task_description], n_results=_OVERFETCH)
        ids = hits["ids"][0]
        dists = hits["distances"][0]
        if not ids:
            return []

        conn = get_pg_connection()
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"""
            SELECT a.id AS asset_id, a.title AS title, a.usage_count AS usage_count,
                   u.name AS owner_name, r.problem AS problem,
                   r.confidence AS confidence
            FROM assets a
            LEFT JOIN users u ON u.id = a.owner_id
            LEFT JOIN asset_versions v ON v.id = a.current_version_id
            LEFT JOIN rationale r ON r.version_id = v.id
            WHERE a.id IN ({placeholders})
            """,
            ids,
        ).fetchall()
        meta = {row["asset_id"]: row for row in rows}

        results = []
        for aid, dist in zip(ids, dists):
            row = meta.get(aid)
            if row is None:
                continue
            cosine = max(0.0, 1.0 - float(dist))
            score = compute(
                cosine,
                row["confidence"] or "auto",
                row["usage_count"] or 0,
            )
            results.append(
                {
                    "asset_id": aid,
                    "title": row["title"],
                    "problem": (row["problem"] or "")[:200],
                    "score": round(score, 4),
                    "usage_count": row["usage_count"] or 0,
                    "owner_name": row["owner_name"] or "",
                }
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]
    except Exception:
        logger.exception("recommend() failed for task_description=%r", task_description)
        return []
