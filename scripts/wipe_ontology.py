import sys

from kb.config import get_settings
from kb.neo4j_store import get_driver, get_ontology, new_ont_version
from kb.ontology import export_ttl

if len(sys.argv) < 2:
    print("用法: python wipe_ontology.py <corpus_id>")
    sys.exit(1)

settings = get_settings()
cid = sys.argv[1]
drv = get_driver(settings)
with drv.session() as s:
    result = s.run(
        "MATCH (n) WHERE (n:OntClass OR n:OntObjProp OR n:OntDataProp) "
        "AND n.corpus_id = $cid DETACH DELETE n",
        cid=cid,
    ).consume()
print(f"corpus={cid} deleted ontology nodes:", result.counters.nodes_deleted)
seq = new_ont_version(drv, cid)
export_ttl(get_ontology(drv, cid), settings.kb_ontology_export_dir + "/" + cid + ".ttl")
print("new version:", seq)
drv.close()
