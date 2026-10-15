from kb.extract import build_prompt, build_signature, parse_extraction

SIGNATURE = {
    "classes": [{"iri": "http://kb.local/o/t#Project", "label": "项目", "aliases": [], "definition": "交付单元"}],
    "object_properties": [{"iri": "http://kb.local/o/t#belongsTo", "label": "属于", "domain": "http://kb.local/o/t#Person", "range": "http://kb.local/o/t#Project"}],
}

TEXT = "星河项目由张三负责，张三属于星河项目。"


def test_parse_extraction_keeps_valid_entities():
    parsed = parse_extraction(
        '{"entities":[{"term":"星河项目","class_iri":"http://kb.local/o/t#Project"}],"relations":[]}',
        TEXT,
        SIGNATURE,
    )
    assert parsed["entities"] == [{"term": "星河项目", "class_iri": "http://kb.local/o/t#Project"}]


def test_parse_extraction_discards_hallucinated_term():
    parsed = parse_extraction(
        '{"entities":[{"term":"不存在的项目","class_iri":"http://kb.local/o/t#Project"}],"relations":[]}',
        TEXT,
        SIGNATURE,
    )
    assert parsed["entities"] == []
    assert parsed["discarded"] == 1


def test_parse_extraction_discards_unknown_iri():
    parsed = parse_extraction(
        '{"entities":[{"term":"星河项目","class_iri":"http://kb.local/o/t#Nope"}],"relations":[]}',
        TEXT,
        SIGNATURE,
    )
    assert parsed["entities"] == []
    assert parsed["discarded"] == 1


def test_build_prompt_contains_signature_and_text():
    prompt = build_prompt(SIGNATURE, TEXT)
    assert "http://kb.local/o/t#Project" in prompt
    assert TEXT in prompt
