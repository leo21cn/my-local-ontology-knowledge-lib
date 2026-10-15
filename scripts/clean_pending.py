from kb.config import get_settings
from kb.neo4j_store import get_driver

d = get_driver(get_settings())
with d.session() as s:
    result = s.run(
        "MATCH (p:PendingItem {corpus_id: $id}) WHERE p.payload CONTAINS 'structure_rebuild_missing_vector' DETACH DELETE p RETURN count(p) AS n",
        id="c87917f13144",
    ).single()
    print("cleaned bogus pending:", result["n"])
d.close()
