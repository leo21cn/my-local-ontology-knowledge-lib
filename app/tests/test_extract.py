from kb.extract import build_induction_prompt, build_prompt, build_signature, parse_extraction, parse_induction

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


INDUCTION_TEXT = "本指引所称金融产品，是指面向投资者发行的理财产品、基金与保险产品。金融机构销售金融产品时应当向投资者充分揭示风险。"


def test_parse_induction_keeps_valid_class():
    parsed = parse_induction(
        '{"classes":[{"local_name":"FinancialProduct","label":"金融产品","definition":"面向投资者的理财产品","aliases":["产品"]}],"object_properties":[]}',
        INDUCTION_TEXT,
    )
    assert parsed["classes"][0]["local_name"] == "FinancialProduct"
    assert parsed["discarded"] == 0


def test_parse_induction_discards_invalid_local_name():
    parsed = parse_induction(
        '{"classes":[{"local_name":"金融产品","label":"金融产品","definition":"x"}],"object_properties":[]}',
        INDUCTION_TEXT,
    )
    assert parsed["classes"] == []
    assert parsed["discarded"] == 1


def test_parse_induction_requires_label_and_definition():
    parsed = parse_induction(
        '{"classes":[{"local_name":"Product","label":"","definition":""}],"object_properties":[]}',
        INDUCTION_TEXT,
    )
    assert parsed["classes"] == []
    assert parsed["discarded"] == 1


def test_parse_induction_property_domain_range_must_reference_classes():
    parsed = parse_induction(
        '{"classes":[{"local_name":"Product","label":"金融产品","definition":"理财产品"}],'
        '"object_properties":[{"local_name":"mentions","label":"涉及","definition":"法规涉及风险","domain":"法规","range":"风险"}]}',
        INDUCTION_TEXT,
    )
    assert parsed["object_properties"] == []
    assert parsed["discarded"] == 1
