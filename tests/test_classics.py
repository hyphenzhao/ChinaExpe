"""Classics reading tools: listing, regex search with line numbers, line reads."""
import pytest

from app.services import classics_service as cs

SAMPLE = """# 示例典籍

## 论用神

八字用神，专求月令。
善而顺用之，则财喜食神以相生。

## 论格局

格局有成有败。
"""


@pytest.fixture()
def room(tmp_path, monkeypatch):
    book = tmp_path / "classics" / "03-子平" / "示例书.md"
    book.parent.mkdir(parents=True)
    book.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(cs, "CLASSICS", tmp_path / "classics")
    monkeypatch.setattr(cs, "KNOWLEDGE", tmp_path / "knowledge")
    monkeypatch.setattr(cs, "ALLOWED_ROOTS", (cs.CLASSICS, cs.KNOWLEDGE))
    cs._lines.cache_clear()
    return book


def test_list_books(room):
    books = cs.list_books()
    assert [b["path"] for b in books] == ["data/classics/03-子平/示例书.md"]
    assert books[0]["category"] == "03-子平"
    assert "示例书" in cs.list_books_text()


def test_search_reports_line_and_section(room):
    hits = cs.search("用神")
    assert hits, "应当命中"
    first = hits[0]
    assert first["path"] == "data/classics/03-子平/示例书.md"
    assert first["line"] == 3 and first["section"] == "论用神"
    assert "论用神" in cs.search_text("用神")


def test_search_accepts_regex_and_book_filter(room):
    assert cs.search("食神.{0,4}相生", book="示例")
    assert cs.search("不存在的词") == []
    assert "没有匹配" in cs.search_text("不存在的词")


def test_read_lines_is_numbered_and_clamped(room):
    text = cs.read_lines("data/classics/03-子平/示例书.md", 1, 5)
     # both the repo-relative path and a path relative to the room resolve
    assert "第 1-5 行" in text and "     3  " in text
    assert cs.read_lines("03-子平/示例书.md", 3, 3).strip().endswith("论用神")


def test_path_escape_is_refused(room):
    with pytest.raises(FileNotFoundError):
        cs.read_lines("../../../etc/passwd")
    with pytest.raises(FileNotFoundError):
        cs.read_lines("data/people/zhf.json")
