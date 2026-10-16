import os

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

ALLOWED_CHARACTERISTICS = {"transitive", "symmetric", "functional", "inverse_functional"}

CHARACTERISTIC_PREDICATES = {
    "transitive": OWL.TransitiveProperty,
    "symmetric": OWL.SymmetricProperty,
    "functional": OWL.FunctionalProperty,
    "inverse_functional": OWL.InverseFunctionalProperty,
}


def validate_rl(entry: dict) -> list[str]:
    violations: list[str] = []
    if not entry.get("iri", "").startswith("http"):
        violations.append("iri 必须为完整 IRI")
    if not entry.get("label_zh"):
        violations.append("label_zh 必填")
    if not entry.get("definition"):
        violations.append("definition 必填")
    for characteristic in entry.get("characteristics", []):
        if characteristic not in ALLOWED_CHARACTERISTICS:
            violations.append(f"属性特征超出 OWL 2 RL 白名单: {characteristic}")
    for key in ("min_cardinality", "max_cardinality"):
        value = entry.get(key)
        if value is not None and value not in (0, 1):
            violations.append(f"{key} 只允许 0 或 1")
    return violations


def subclass_closure(classes: list[dict]) -> dict[str, set[str]]:
    parents = {c["iri"]: set(c.get("parent_iris", [])) for c in classes}
    closure: dict[str, set[str]] = {}
    for iri in parents:
        seen = {iri}
        stack = list(parents[iri])
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(parents.get(current, set()))
        closure[iri] = seen
    return closure


def _add_common(graph: Graph, iri: str, kind, entry: dict) -> URIRef:
    subject = URIRef(iri)
    graph.add((subject, RDF.type, kind))
    graph.add((subject, RDFS.label, Literal(entry.get("label_zh", ""), lang="zh")))
    graph.add((subject, RDFS.comment, Literal(entry.get("definition", ""))))
    return subject


def export_ttl(ontology: dict, path: str) -> None:
    graph = Graph()
    graph.bind("kb", Namespace(ontology["base_iri"]))
    for entry in ontology.get("classes", []):
        subject = _add_common(graph, entry["iri"], OWL.Class, entry)
        for parent in entry.get("parent_iris", []):
            graph.add((subject, RDFS.subClassOf, URIRef(parent)))
        for other in entry.get("disjoint_with", []):
            graph.add((subject, OWL.disjointWith, URIRef(other)))
        if entry.get("equivalent_to"):
            graph.add((subject, OWL.equivalentClass, URIRef(entry["equivalent_to"])))
    for entry in ontology.get("object_properties", []):
        subject = _add_common(graph, entry["iri"], OWL.ObjectProperty, entry)
        if entry.get("domain_iri"):
            graph.add((subject, RDFS.domain, URIRef(entry["domain_iri"])))
        if entry.get("range_iri"):
            graph.add((subject, RDFS.range, URIRef(entry["range_iri"])))
        for characteristic in entry.get("characteristics", []):
            graph.add((subject, RDF.type, CHARACTERISTIC_PREDICATES[characteristic]))
    for entry in ontology.get("datatype_properties", []):
        subject = _add_common(graph, entry["iri"], OWL.DatatypeProperty, entry)
        if entry.get("domain_iri"):
            graph.add((subject, RDFS.domain, URIRef(entry["domain_iri"])))
        if entry.get("xsd_range"):
            graph.add((subject, RDFS.range, URIRef(entry["xsd_range"])))
    tmp = f"{path}.tmp"
    graph.serialize(destination=tmp, format="turtle")
    os.replace(tmp, path)


VIOLATION_QUERY = """
MATCH (a:Entity)-[r:REL]->(b:Entity)
WHERE r.type_iri = $iri AND r.state = 'confirmed'
RETURN a.eid AS a, a.class_iri AS ac, b.eid AS b, b.class_iri AS bc
"""


def _label_of(graph: Graph, subject: URIRef) -> str:
    for obj in graph.objects(subject, RDFS.label):
        text = str(obj)
        if text:
            if isinstance(obj, Literal) and obj.language == "zh":
                return text
    for obj in graph.objects(subject, RDFS.label):
        if str(obj):
            return str(obj)
    return ""


def _comment_of(graph: Graph, subject: URIRef) -> str:
    for obj in graph.objects(subject, RDFS.comment):
        if str(obj):
            return str(obj)
    return ""


def parse_ttl(text: str) -> dict:
    graph = Graph()
    try:
        graph.parse(data=text, format="turtle")
    except Exception as exc:
        raise ValueError(f"TTL 解析失败: {exc}") from exc

    classes: list[dict] = []
    object_properties: list[dict] = []
    datatype_properties: list[dict] = []
    skipped: list[dict] = []

    def http_iri(subject) -> str | None:
        if not isinstance(subject, URIRef):
            return None
        value = str(subject)
        return value if value.startswith("http") else None

    for subject in graph.subjects(RDF.type, OWL.Class):
        iri = http_iri(subject)
        if not iri:
            skipped.append({"iri": str(subject), "reason": "非 http IRI"})
            continue
        entry = {
            "iri": iri,
            "label_zh": _label_of(graph, subject),
            "definition": _comment_of(graph, subject),
            "parent_iris": [str(o) for o in graph.objects(subject, RDFS.subClassOf)],
            "disjoint_with": [str(o) for o in graph.objects(subject, OWL.disjointWith)],
            "aliases": [],
        }
        equivalent = [str(o) for o in graph.objects(subject, OWL.equivalentClass)]
        if equivalent:
            entry["equivalent_to"] = equivalent[0]
        classes.append(entry)

    for subject in graph.subjects(RDF.type, OWL.ObjectProperty):
        iri = http_iri(subject)
        if not iri:
            skipped.append({"iri": str(subject), "reason": "非 http IRI"})
            continue
        entry = {
            "iri": iri,
            "label_zh": _label_of(graph, subject),
            "definition": _comment_of(graph, subject),
            "domain_iri": next((str(o) for o in graph.objects(subject, RDFS.domain)), ""),
            "range_iri": next((str(o) for o in graph.objects(subject, RDFS.range)), ""),
            "characteristics": [],
        }
        for characteristic, predicate in CHARACTERISTIC_PREDICATES.items():
            if (subject, RDF.type, predicate) in graph:
                entry["characteristics"].append(characteristic)
        object_properties.append(entry)

    for subject in graph.subjects(RDF.type, OWL.DatatypeProperty):
        iri = http_iri(subject)
        if not iri:
            skipped.append({"iri": str(subject), "reason": "非 http IRI"})
            continue
        entry = {
            "iri": iri,
            "label_zh": _label_of(graph, subject),
            "definition": _comment_of(graph, subject),
            "domain_iri": next((str(o) for o in graph.objects(subject, RDFS.domain)), ""),
            "xsd_range": next((str(o) for o in graph.objects(subject, RDFS.range)), ""),
        }
        datatype_properties.append(entry)

    return {
        "classes": classes,
        "object_properties": object_properties,
        "datatype_properties": datatype_properties,
        "skipped": skipped,
    }


def find_violations(driver, obj_prop: dict, classes: list[dict]) -> list[dict]:
    closure = subclass_closure(classes)
    domain = obj_prop.get("domain_iri")
    range_iri = obj_prop.get("range_iri")
    violations: list[dict] = []
    with driver.session() as session:
        rows = session.run(VIOLATION_QUERY, iri=obj_prop["iri"]).data()
    for row in rows:
        subject_closure = closure.get(row["ac"], {row["ac"]})
        object_closure = closure.get(row["bc"], {row["bc"]})
        if domain and domain not in subject_closure:
            violations.append(
                {"relation_type_iri": obj_prop["iri"], "from": row["a"], "to": row["b"], "reason": "domain"}
            )
        if range_iri and range_iri not in object_closure:
            violations.append(
                {"relation_type_iri": obj_prop["iri"], "from": row["a"], "to": row["b"], "reason": "range"}
            )
    return violations


def check_relation_valid(classes: list[dict], obj_prop: dict,
                         from_class_iri: str, to_class_iri: str) -> list[str]:
    closure = subclass_closure(classes)
    domain = obj_prop.get("domain_iri")
    range_iri = obj_prop.get("range_iri")
    reasons: list[str] = []
    if domain and domain not in closure.get(from_class_iri, {from_class_iri}):
        reasons.append("domain")
    if range_iri and range_iri not in closure.get(to_class_iri, {to_class_iri}):
        reasons.append("range")
    return reasons
