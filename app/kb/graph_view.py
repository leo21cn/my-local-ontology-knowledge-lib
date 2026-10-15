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
