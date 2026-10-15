from pathlib import Path

from kb.search import class_matched_pairs, read_context, rrf_fuse


def test_rrf_fuse_prefers_item_in_both_lists():
    scores = rrf_fuse([["a", "b", "c"], ["b", "d"]])
    assert max(scores, key=scores.get) == "b"
    assert scores["a"] > scores["c"]


def test_rrf_fuse_single_list_preserves_order():
    scores = rrf_fuse([["x", "y"]])
    assert scores["x"] > scores["y"]


def test_rrf_fuse_applies_list_weights():
    scores = rrf_fuse([["a"], ["a"]], weights=[1.0, 2.0])
    assert round(scores["a"], 6) == round(3.0 / 61, 6)


def test_class_matched_pairs_returns_matching_pairs():
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def data(self):
            return self.rows

    class FakeSession:
        def run(self, query, **kwargs):
            return FakeResult([{"rel_path": "a.md", "seq": 0}])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeDriver:
        def session(self):
            return FakeSession()

    payloads = [{"asset_rel_path": "a.md", "seq": 0}]
    assert class_matched_pairs(FakeDriver(), "c1", payloads, {"Person", "Agent"}) == {("a.md", 0)}


def test_read_context_returns_heading_section(tmp_path: Path):
    note = tmp_path / "a.md"
    note.write_text("# 甲\n第一段\n\n## 乙\n第二段\n\n# 丙\n第三段", encoding="utf-8")
    payload = {"asset_rel_path": "a.md", "heading_path": ["甲", "乙"], "seq": 1}
    context = read_context(str(tmp_path), payload)
    assert context == "第二段"


def test_read_context_missing_file_returns_none(tmp_path: Path):
    assert read_context(str(tmp_path), {"asset_rel_path": "nope.md", "heading_path": []}) is None


def test_read_context_without_heading_returns_head(tmp_path: Path):
    note = tmp_path / "b.md"
    note.write_text("纯文本正文", encoding="utf-8")
    assert read_context(str(tmp_path), {"asset_rel_path": "b.md", "heading_path": []}) == "纯文本正文"
