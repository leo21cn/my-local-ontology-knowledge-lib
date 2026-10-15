from pathlib import Path

from rdflib import Graph

from kb.ontology import check_relation_valid, export_ttl, find_violations, subclass_closure, validate_rl

CLASS_A = {
    "iri": "http://kb.local/o/c1#Project",
    "label_zh": "项目",
    "definition": "一个交付单元",
    "parent_iris": [],
    "disjoint_with": [],
}


def test_validate_rl_passes_on_complete_entry():
    assert validate_rl(CLASS_A) == []


def test_validate_rl_rejects_relative_iri():
    entry = dict(CLASS_A, iri="Project")
    assert any("IRI" in v for v in validate_rl(entry))


def test_validate_rl_requires_label_and_definition():
    entry = dict(CLASS_A, label_zh="", definition="")
    violations = validate_rl(entry)
    assert any("label_zh" in v for v in violations)
    assert any("definition" in v for v in violations)


def test_validate_rl_rejects_non_whitelisted_characteristic():
    entry = dict(CLASS_A, characteristics=["inverseOf"])
    assert any("白名单" in v for v in validate_rl(entry))


def test_validate_rl_rejects_cardinality_above_one():
    entry = dict(CLASS_A, max_cardinality=3)
    assert any("max_cardinality" in v for v in validate_rl(entry))


def test_export_ttl_is_parseable(tmp_path: Path):
    ontology = {
        "base_iri": "http://kb.local/o/c1#",
        "classes": [CLASS_A],
        "object_properties": [
            {
                "iri": "http://kb.local/o/c1#belongsTo",
                "label_zh": "属于",
                "definition": "从属关系",
                "domain_iri": "http://kb.local/o/c1#Person",
                "range_iri": "http://kb.local/o/c1#Project",
                "characteristics": ["transitive"],
            }
        ],
        "datatype_properties": [
            {
                "iri": "http://kb.local/o/c1#note",
                "label_zh": "备注",
                "definition": "自由文本",
                "domain_iri": "http://kb.local/o/c1#Project",
                "xsd_range": "http://www.w3.org/2001/XMLSchema#string",
            }
        ],
    }
    out = tmp_path / "c1.ttl"
    export_ttl(ontology, str(out))
    graph = Graph()
    graph.parse(str(out), format="turtle")
    assert len(graph) > 8


def test_export_ttl_atomic_replace_leaves_no_tmp(tmp_path: Path):
    out = tmp_path / "c1.ttl"
    export_ttl({"base_iri": "http://kb.local/o/c1#", "classes": [CLASS_A],
                "object_properties": [], "datatype_properties": []}, str(out))
    assert not (tmp_path / "c1.ttl.tmp").exists()


def test_subclass_closure_is_transitive():
    classes = [
        {"iri": "A", "parent_iris": []},
        {"iri": "B", "parent_iris": ["A"]},
        {"iri": "C", "parent_iris": ["B"]},
    ]
    closure = subclass_closure(classes)
    assert closure["C"] == {"C", "B", "A"}


def test_find_violations_flags_out_of_range():
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def data(self):
            return self.rows

    class FakeSession:
        def run(self, query, **kwargs):
            return FakeResult([{"a": "e1", "ac": "Person", "b": "e2", "bc": "Person"}])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeDriver:
        def session(self):
            return FakeSession()

    obj_prop = {
        "iri": "belongsTo",
        "domain_iri": "Person",
        "range_iri": "Project",
    }
    classes = [
        {"iri": "Person", "parent_iris": []},
        {"iri": "Project", "parent_iris": []},
    ]
    violations = find_violations(FakeDriver(), obj_prop, classes)
    assert len(violations) == 1
    assert violations[0]["reason"] == "range"


def test_check_relation_valid_domain_and_range():
    classes = [
        {"iri": "Person", "parent_iris": []},
        {"iri": "Project", "parent_iris": []},
    ]
    obj_prop = {"iri": "belongsTo", "domain_iri": "Person", "range_iri": "Project"}
    assert check_relation_valid(classes, obj_prop, "Project", "Project") == ["domain"]
    assert check_relation_valid(classes, obj_prop, "Person", "Person") == ["range"]
    assert check_relation_valid(classes, obj_prop, "Person", "Project") == []
