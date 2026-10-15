import re
from pathlib import Path

from qdrant_client import QdrantClient

from kb.config import Settings
from kb.embed import embed_texts
from kb.neo4j_store import get_corpus, get_driver, get_ontology
from kb.ontology import subclass_closure
from kb.qdrant_store import chunk_id, fetch_points, search_points

EXPAND_QUERY = """
UNWIND $pairs AS pair
MATCH (a:Anchor {rel_path: pair.rel_path, seq: pair.seq})<-[:ANCHOR_OF]-(e:Entity)
WITH collect(DISTINCT e) AS seeds
UNWIND seeds AS seed
MATCH (seed)-[r:REL {state: 'confirmed'}]-(other:Entity)
MATCH (other)-[:ANCHOR_OF]->(oa:Anchor)
RETURN DISTINCT oa.rel_path AS rel_path, oa.seq AS seq, oa.sha256 AS sha256
"""

CLASS_MATCH_QUERY = """
UNWIND $pairs AS pair
MATCH (a:Anchor {rel_path: pair.rel_path, seq: pair.seq})<-[:ANCHOR_OF]-(e:Entity {corpus_id: $corpus_id})-[:INSTANCE_OF]->(c:OntClass)
WHERE c.iri IN $iris
RETURN DISTINCT pair.rel_path AS rel_path, pair.seq AS seq
"""


def rrf_fuse(ranked_lists: list[list[str]], k: int = 60,
             weights: list[float] | None = None) -> dict[str, float]:
    weights = weights or [1.0] * len(ranked_lists)
    scores: dict[str, float] = {}
    for ranked, weight in zip(ranked_lists, weights):
        for rank, item in enumerate(ranked):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank + 1)
    return scores


def class_matched_pairs(driver, corpus_id: str, payloads: list[dict],
                        iris: set[str]) -> set[tuple[str, int]]:
    pairs = [
        {"rel_path": p["asset_rel_path"], "seq": p["seq"]}
        for p in payloads
        if p.get("asset_rel_path") is not None
    ]
    if not pairs or not iris:
        return set()
    with driver.session() as session:
        rows = session.run(
            CLASS_MATCH_QUERY, corpus_id=corpus_id, pairs=pairs, iris=list(iris)
        ).data()
    return {(row["rel_path"], row["seq"]) for row in rows}


def read_context(corpus_root: str, payload: dict, max_chars: int = 2000) -> str | None:
    path = Path(corpus_root) / payload["asset_rel_path"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    heading_path = payload.get("heading_path") or []
    if not heading_path:
        return text[:max_chars]
    title = heading_path[-1]
    match = re.search(rf"^(#{{1,6}})\s+{re.escape(title)}\s*$", text, re.MULTILINE)
    if not match:
        return text[:max_chars]
    level = len(match.group(1))
    remainder = text[match.end():]
    nxt = re.search(rf"^#{{1,{level}}}\s+", remainder, re.MULTILINE)
    section = remainder[:nxt.start()] if nxt else remainder
    return section.strip()[:max_chars] or None


def expand_one_hop(driver, payloads: list[dict]) -> list[str]:
    pairs = [
        {"rel_path": p["asset_rel_path"], "seq": p["seq"]}
        for p in payloads
        if p.get("asset_rel_path") is not None
    ]
    if not pairs:
        return []
    with driver.session() as session:
        rows = session.run(EXPAND_QUERY, pairs=pairs).data()
    ids = []
    for row in rows:
        if row["sha256"]:
            ids.append(chunk_id(row["rel_path"], row["sha256"]))
    return ids


async def run_search(settings: Settings, corpus_id: str, query: str,
                     filters: dict | None = None, top_k: int = 10) -> list[dict]:
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    driver = get_driver(settings)
    try:
        corpus = get_corpus(driver, corpus_id)
        if corpus is None or corpus.get("archived"):
            return []
        vectors, _ = await embed_texts(settings, [query])
        hits = search_points(client, corpus_id, vectors[0], filters or {}, top_k=top_k)
        class_iri = (filters or {}).get("class_iri")
        if class_iri:
            ontology = get_ontology(driver, corpus_id)
            iris = subclass_closure(ontology["classes"]).get(class_iri, {class_iri})
            matched = class_matched_pairs(
                driver, corpus_id, [hit.payload for hit in hits], iris
            )
            hits = [
                hit
                for hit in hits
                if (hit.payload["asset_rel_path"], hit.payload["seq"]) in matched
            ]
        vector_ranked = [hit.id for hit in hits]
        by_id = {hit.id: hit for hit in hits}
        graph_ranked: list[str] = []
        if corpus.get("graph_expand_enabled", True):
            graph_ranked = expand_one_hop(driver, [hit.payload for hit in hits])
            missing = [pid for pid in graph_ranked if pid not in by_id]
            for point in fetch_points(client, corpus_id, missing):
                by_id[point.id] = point
        graph_weight = float(corpus.get("graph_weight", 1.0))
        fused = rrf_fuse([vector_ranked, graph_ranked], k=60, weights=[1.0, graph_weight])
        ordered = [pid for pid, _ in sorted(fused.items(), key=lambda kv: -kv[1])][:top_k]
        vector_rank = {pid: rank + 1 for rank, pid in enumerate(vector_ranked)}
        results = []
        for fused_rank, pid in enumerate(ordered, start=1):
            point = by_id.get(pid)
            if point is None:
                continue
            payload = point.payload
            context = read_context(settings.kb_corpus_root, payload)
            if context is None:
                continue
            results.append(
                {
                    "chunk_id": pid,
                    "content": payload.get("text", "")[:300],
                    "context": context,
                    "anchor": {
                        "rel_path": payload["asset_rel_path"],
                        "seq": payload["seq"],
                        "sha256": payload["chunk_sha256"],
                    },
                    "score": round(fused[pid], 6),
                    "vector_rank": vector_rank.get(pid),
                    "fused_rank": fused_rank,
                    "heading_path": payload.get("heading_path", []),
                    "asset_rel_path": payload["asset_rel_path"],
                }
            )
        return results
    finally:
        driver.close()
        client.close()
