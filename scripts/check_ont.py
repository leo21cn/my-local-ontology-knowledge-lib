from kb.config import get_settings
from kb.neo4j_store import get_driver

d = get_driver(get_settings())
with d.session() as s:
    rows = s.run(
        "MATCH (n:OntClass {corpus_id: $id}) RETURN n.iri AS iri, n.label_zh AS label, n.arrays AS arrays",
        id="c01bc5ea859a",
    ).data()
for r in rows:
    label = r["label"]
    expect = "\u9879\u76ee"
    import json

    arrays = json.loads(r["arrays"] or "{}")
    aliases = arrays.get("aliases", [])
    alias_ok = aliases and aliases[0] == "\u9a8c\u6536\u9879\u76ee\u7ec4"
    print(r["iri"].split("#")[-1], "label_cp", [hex(ord(ch)) for ch in label], "alias_cp", [hex(ord(ch)) for ch in (aliases[0] if aliases else "")], "label_ok=", label == expect, "alias_ok=", alias_ok)
d.close()
