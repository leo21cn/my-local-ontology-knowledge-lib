import asyncio
from pathlib import Path

from kb.config import get_settings
from kb.embed import embed_texts
from kb.sync import qdrant_client
from kb.qdrant_store import fetch_points, search_points
from kb.neo4j_store import get_corpus, get_driver
from kb.search import expand_one_hop, read_context, rrf_fuse


async def main():
    s = get_settings()
    corpus_id = "c01bc5ea859a"
    client = qdrant_client(s)
    driver = get_driver(s)
    corpus = get_corpus(driver, corpus_id)
    context_root = str(Path(s.kb_corpus_root) / corpus["subdir"])
    vectors, _ = await embed_texts(s, ["验收项目组"])
    hits = search_points(client, corpus_id, vectors[0], {}, 3)
    vector_ranked = [hit.id for hit in hits]
    by_id = {hit.id: hit for hit in hits}
    graph_ranked = expand_one_hop(driver, [hit.payload for hit in hits])
    missing = [pid for pid in graph_ranked if pid not in by_id]
    fetched = fetch_points(client, corpus_id, missing)
    print("missing:", missing)
    print("fetched ids:", [p.id for p in fetched])
    for point in fetched:
        by_id[point.id] = point
    fused = rrf_fuse([vector_ranked, graph_ranked], k=60, weights=[1.0, 1.0])
    ordered = [pid for pid, _ in sorted(fused.items(), key=lambda kv: -kv[1])][:3]
    print("ordered:", ordered)
    for pid in ordered:
        point = by_id.get(pid)
        print("  pid", pid[:8], "in by_id:", point is not None)
        if point is not None:
            ctx = read_context(context_root, point.payload)
            print("    ctx_len:", len(ctx) if ctx else None, "rel:", point.payload.get("asset_rel_path"))
    driver.close()
    client.close()


asyncio.run(main())
