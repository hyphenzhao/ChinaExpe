import asyncio
import json
from pathlib import Path

import pytest

from scripts.repair_ziwei_archive import damaged, to_text, restored_text, write_recovery
from scripts.build_website_vectors import build, split_body, article_chunks
from app.services.local_knowledge import local_knowledge
from app.services.knowledge_service import KnowledgeService


def record():
    return {"id": 10, "link": "https://www.ziwei.my/si-hua/example/", "modified": "2026-01-01T00:00:00",
            "title": {"rendered": "测试：四化 &amp; 宫位"}, "content": {"protected": False,
                "rendered": "<p>本文是测试用的虚构文字，用来验证中文正文恢复流程。</p>" * 8}}


def entry():
    return {"id": 10, "source": "https://www.ziwei.my/old-url/", "captured": "2026-01-01 12:00:00",
            "file": "knowledge_base/sample/article.txt", "before_sha256": "test"}


def test_extract_preserves_inline_words_and_table_cells():
    value = to_text('<h2>四化</h2><p>廉<strong>贞</strong>化忌 &amp; 六亲</p><script>bad()</script>'
                    '<table><tr><td>命宫</td><td>财帛</td></tr></table><img alt="十二宫图">')
    assert "廉贞化忌 & 六亲" in value and "命宫 财帛" in value
    assert "bad()" not in value and "十二宫图" in value


def test_restore_records_permalink_move_and_parser_excludes_metadata():
    text = restored_text(entry(), record(), "2026-01-02T00:00:00Z")
    title, source, body = local_knowledge._parse_file(Path("example.txt"), text)
    assert title == "测试：四化 & 宫位" and source == record()["link"]
    assert "原存档来源: https://www.ziwei.my/old-url/" in text
    assert "修复时间" not in body and "抓取时间" not in body and "恢复方式" not in body
    assert body.startswith("本文是测试")


@pytest.mark.parametrize("problem", ["id", "protected", "damage", "outside", "empty"])
def test_bad_publisher_response_never_overwrites_original(tmp_path, problem):
    e, r = entry(), record()
    p = tmp_path / e["file"]; p.parent.mkdir(parents=True); p.write_text("原始备份")
    if problem == "id": r["id"] = 99
    if problem == "protected": r["content"]["protected"] = True
    if problem == "damage": r["content"]["rendered"] += "\ufffd"
    if problem == "outside": r["link"] = "https://example.com/article"
    if problem == "empty": r["content"]["rendered"] = "403 Forbidden"
    with pytest.raises(ValueError): write_recovery(tmp_path, tmp_path / "backup", e, r, "now")
    assert p.read_text() == "原始备份"


def test_backup_preserves_both_originals(tmp_path):
    e, r = entry(), record();p = tmp_path / e["file"];p.parent.mkdir(parents=True)
    p.write_text("old damaged text");p.with_suffix('.html').write_text("old html")
    for _ in range(2): write_recovery(tmp_path, tmp_path / "backup", e, r, "now")
    assert (tmp_path / "backup" / e["file"]).read_text() == "old damaged text"
    assert (tmp_path / "backup" / e["file"]).with_suffix('.html').read_text() == "old html"
    assert not damaged(p.read_text()) and 'charset="utf-8"' in p.with_suffix('.html').read_text()


def test_chunks_cover_article_tail_and_reject_broken_text(tmp_path):
    text = "甲" * 1400 + "\n" + "乙" * 1500 + "最后一段"
    chunks = list(split_body(text));assert max(map(len, chunks)) <= 1200
    assert chunks[-1].endswith("最后一段")
    p = tmp_path / "bad.txt";p.write_text("乱码\ufffd")
    with pytest.raises(ValueError): article_chunks([p])


def test_search_rejects_corrupt_legacy_vectors():
    service = KnowledgeService()
    source = record()["link"]
    assert service._is_quality(source, "廉贞化忌与六亲感情")
    assert not service._is_quality(source, "旧档正文\ufffd")
    mojibake = "你好".encode("utf-8").decode("latin-1")
    assert damaged(mojibake)
    assert not service._is_quality(source, mojibake)


def test_vector_failure_keeps_table_and_resume_reuses_checkpoint(tmp_path):
    import lancedb
    dbpath = tmp_path / "db";db = lancedb.connect(str(dbpath))
    db.create_table("ziwei_knowledge", data=[{"content": "old", "vector": [0.1, 0.2]}])
    p=tmp_path/'article.txt';r=record();r['content']['rendered']='<p>' + '测试中文正文。'*500 + '</p>'
    p.write_text(restored_text(entry(), r, "now"))
    class Service:
        def __init__(self): self.calls=0;self.fail=True
        async def embed_many(self, texts):
            self.calls+=1
            return None if self.fail and self.calls==2 else [[0.3,0.4] for _ in texts]
        def refresh(self): pass
    s=Service();kwargs=dict(files=[p],db_path=dbpath,cache_path=tmp_path/'cache.sqlite3',batch=1)
    with pytest.raises(RuntimeError): asyncio.run(build(s, **kwargs))
    assert db.open_table('ziwei_knowledge').to_arrow().to_pylist()[0]['content']=='old'
    s.fail=False;s.calls=0
    result=asyncio.run(build(s,**kwargs))
    assert s.calls==result['rows']-1
    assert db.open_table('ziwei_knowledge').count_rows()==result['rows']
