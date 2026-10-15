from kb.chunker import chunk_markdown, chunk_sha256, extract_frontmatter


def test_headings_split_with_path():
    body = "# A\n甲甲\n\n## B\n乙乙\n\n# C\n丙丙"
    drafts = chunk_markdown(body, max_chars=700)
    assert [(d.heading_path, d.text) for d in drafts] == [
        (["A"], "甲甲"),
        (["A", "B"], "乙乙"),
        (["C"], "丙丙"),
    ]


def test_long_section_splits_with_overlap():
    body = "一" * 1500
    drafts = chunk_markdown(body, max_chars=700, overlap=60)
    assert len(drafts) == 3
    assert drafts[1].text.startswith(drafts[0].text[-60:])


def test_empty_heading_section_skipped():
    body = "# A\n\n## B\n正文"
    drafts = chunk_markdown(body, max_chars=700)
    assert [d.text for d in drafts] == ["正文"]


def test_frontmatter_tags_extracted():
    text = "---\ntags: [甲, 乙]\n---\n# T\n正文"
    meta, body = extract_frontmatter(text)
    assert meta["tags"] == ["甲", "乙"]
    assert body.startswith("# T")


def test_chunk_sha_stable():
    assert chunk_sha256("同一段文本") == chunk_sha256("同一段文本")
    assert chunk_sha256("同一段文本") != chunk_sha256("另一段文本")
