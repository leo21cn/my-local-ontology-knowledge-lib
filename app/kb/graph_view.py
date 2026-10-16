GRAPH_QUERY_TEMPLATE = """
MATCH path = (center:Entity {{eid: $eid}})-[:REL*1..{depth}]-(other:Entity)
RETURN [n IN nodes(path) | {{eid: n.eid, label: n.label, class_iri: n.class_iri,
                            anchors: size([(n)-[:ANCHOR_OF]->(:Anchor) | 1])}}] AS nodes,
       [r IN relationships(path) | {{type_iri: r.type_iri, state: r.state,
                                    from: startNode(r).eid, to: endNode(r).eid}}] AS edges
"""


def clamp_depth(depth: int) -> int:
    return min(max(depth, 1), 2)


def read_graph_data(driver, entity_id: str, depth: int = 2) -> dict:
    rows = driver.session().run(
        GRAPH_QUERY_TEMPLATE.format(depth=clamp_depth(depth)), eid=entity_id
    ).data()
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for row in rows:
        for node in row["nodes"]:
            nodes[node["eid"]] = node
        edges.extend(row["edges"])
    return {"nodes": list(nodes.values()), "edges": edges}


def read_full_graph(driver, corpus_id: str, limit: int = 500) -> dict:
    with driver.session() as session:
        total = session.run(
            "MATCH (e:Entity {corpus_id: $cid}) RETURN count(e) AS n", cid=corpus_id
        ).single()["n"]
        node_rows = session.run(
            """
            MATCH (e:Entity {corpus_id: $cid})
            RETURN e.eid AS eid, e.label AS label, e.class_iri AS class_iri,
                   size([(e)-[:ANCHOR_OF]->(:Anchor) | 1]) AS anchors
            ORDER BY e.label SKIP 0 LIMIT $limit
            """,
            cid=corpus_id, limit=limit,
        ).data()
    nodes = {row["eid"]: {
        "eid": row["eid"], "label": row["label"], "class_iri": row["class_iri"],
        "anchors": row["anchors"],
    } for row in node_rows}
    eids = list(nodes.keys())
    edges: list[dict] = []
    if eids:
        with driver.session() as session:
            edges = session.run(
                """
                MATCH (a:Entity)-[r:REL]->(b:Entity)
                WHERE a.eid IN $eids AND b.eid IN $eids
                RETURN r.type_iri AS type_iri, r.state AS state,
                       startNode(r).eid AS from, endNode(r).eid AS to
                """,
                eids=eids,
            ).data()
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "total": total,
        "truncated": total > len(nodes),
    }
