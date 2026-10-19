import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from corpus.ingest import ManifestLoadError
from corpus.library import ScriptureLibrary


def write_manifest(tmp_path: Path, **overrides: object) -> Path:
    (tmp_path / "source.txt").write_text(
        "పరీక్ష పాఠం\nతెలుగు వివరణ\nAccent: a\u0301 \u0951 \u0952\n", encoding="utf-8"
    )
    entry = {
        "id": "test_source",
        "title": "Synthetic test text, not scripture",
        "layer": "test",
        "tradition": "test",
        "format": "text",
        "local_path": "source.txt",
        "language": "te",
        "edition": "Test edition 1",
        "rights_basis": "permission",
        "rights_note": "Original synthetic test data",
        "review_status": "reviewed",
        "reviewer": "Test curator (not religious certification)",
        "chunk_size": 20,
        **overrides,
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([entry], ensure_ascii=False), encoding="utf-8")
    return manifest


def test_persistent_import_exact_text_and_citations(tmp_path: Path):
    manifest = write_manifest(tmp_path)
    database = tmp_path / "library.sqlite3"
    imported = ScriptureLibrary(database).import_manifest(manifest)
    library = ScriptureLibrary(database)
    assert imported["sources_imported"] == 1
    results = library.search("పరీక్ష")["results"]
    assert len(results) == 1
    result = results[0]
    assert library.passage(result["passage_id"]) == result
    text = (tmp_path / "source.txt").read_text(encoding="utf-8")
    citation = result["citation"]
    assert result["text"] == text[citation["start_char"]:citation["end_char"]]
    assert citation["start_line"] == citation["end_line"] == 1
    assert citation["source"]["edition"] == "Test edition 1"
    assert citation["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert "local_path" not in citation["source"]
    accents = library.search("Accent:")["results"][0]["text"]
    assert "a\u0301 \u0951 \u0952" in accents
    assert library.search("á")["results"][0]["text"] == accents


def test_review_and_metadata_filters(tmp_path: Path):
    manifest = write_manifest(tmp_path, review_status="unreviewed", reviewer="")
    library = ScriptureLibrary(tmp_path / "library.sqlite3")
    library.import_manifest(manifest)
    assert library.search("పరీక్ష")["status"] == "no_matching_passages"
    assert library.search("పరీక్ష", reviewed_only=False)["results"]
    assert not library.search("పరీక్ష", reviewed_only=False, language="en")["results"]
    assert not library.search("పరీక్ష", reviewed_only=False, tradition="other")["results"]
    assert not library.search("పరీక్ష", reviewed_only=False, source_id="unknown")["results"]


def test_reimport_replaces_passages_and_invalidates_changed_ids(tmp_path: Path):
    manifest = write_manifest(tmp_path)
    library = ScriptureLibrary(tmp_path / "library.sqlite3")
    original = library.import_manifest(manifest)
    passage_id = library.search("పరీక్ష")["results"][0]["passage_id"]
    assert library.import_manifest(manifest) == original
    assert library.sources()[0]["passage_count"] == original["passages_imported"]
    (tmp_path / "source.txt").write_text("replacement text", encoding="utf-8")
    library.import_manifest(manifest)
    assert not library.search("పరీక్ష")["results"]
    with pytest.raises(ValueError, match="outdated"):
        library.passage(passage_id)


@pytest.mark.parametrize("overrides", [
    {"rights_basis": ""},
    {"rights_note": ""},
    {"edition": ""},
    {"review_status": "certified"},
    {"reviewer": ""},
    {"format": "pdf"},
    {"local_path": None},
    {"id": "../escape"},
    {"chunk_size": 0},
])
def test_import_rejects_missing_provenance(tmp_path: Path, overrides: dict[str, object]):
    manifest = write_manifest(tmp_path, **overrides)
    library = ScriptureLibrary(tmp_path / "library.sqlite3")
    with pytest.raises(ManifestLoadError):
        library.import_manifest(manifest)
    assert library.sources() == []


def test_atomic_import_preserves_previous_library_on_failure(tmp_path: Path):
    manifest = write_manifest(tmp_path)
    library = ScriptureLibrary(tmp_path / "library.sqlite3")
    library.import_manifest(manifest)
    original = library.sources()
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    entries[0]["edition"] = "Changed edition"
    entries.append({**entries[0], "id": "missing", "local_path": "absent.txt"})
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        library.import_manifest(manifest)
    assert library.sources() == original


def test_search_validation_literal_terms_and_pagination(tmp_path: Path):
    manifest = write_manifest(tmp_path, chunk_size=6)
    (tmp_path / "source.txt").write_text("alpha\nalpha\nపరీక్ష\n", encoding="utf-8")
    library = ScriptureLibrary(tmp_path / "library.sqlite3")
    library.import_manifest(manifest)
    page = library.search("alpha", limit=1)
    assert len(page["results"]) == 1
    assert page["next_offset"] == 1
    assert library.search("alpha", limit=1, offset=1)["results"] != page["results"]
    assert not library.search("' OR 1=1 --")["results"]
    assert not library.search("పరీక్ష absent")["results"]
    for query, limit, offset in [("", 10, 0), ("a", 0, 0), ("a", 51, 0), ("a", 10, -1)]:
        with pytest.raises(ValueError):
            library.search(query, limit=limit, offset=offset)


def test_long_line_chunks_reconstruct_original_text(tmp_path: Path):
    manifest = write_manifest(tmp_path, chunk_size=5)
    text = "abcdefghijklmnop\n\n\nsecond line\n"
    (tmp_path / "source.txt").write_text(text, encoding="utf-8")
    library = ScriptureLibrary(tmp_path / "library.sqlite3")
    library.import_manifest(manifest)
    with sqlite3.connect(library.database) as connection:
        rows = connection.execute(
            "SELECT passage_id FROM passages ORDER BY ordinal"
        ).fetchall()
    passages = [library.passage(row[0]) for row in rows]
    assert "".join(passage["text"] for passage in passages) == text
    for passage in passages:
        citation = passage["citation"]
        assert len(passage["text"]) <= 5
        assert citation["start_line"] == text[:citation["start_char"]].count("\n") + 1
        assert citation["end_line"] == text[:citation["end_char"] - 1].count("\n") + 1
    assert passages[0]["previous_passage_id"] is None
    assert passages[-1]["next_passage_id"] is None
    for current, following in zip(passages, passages[1:]):
        assert current["next_passage_id"] == following["passage_id"]
        assert following["previous_passage_id"] == current["passage_id"]


def test_import_preserves_crlf_and_raw_utf8_hash(tmp_path: Path):
    manifest = write_manifest(tmp_path, chunk_size=100)
    raw = "పరీక్ష\r\n\r\nతెలుగు\r\n".encode("utf-8")
    (tmp_path / "source.txt").write_bytes(raw)
    library = ScriptureLibrary(tmp_path / "library.sqlite3")
    library.import_manifest(manifest)
    passage = library.search("పరీక్ష")["results"][0]
    assert passage["text"].encode("utf-8") == raw
    assert passage["citation"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert passage["citation"]["start_line"] == 1
    assert passage["citation"]["end_line"] == 3


def test_import_rejects_duplicates_and_invalid_json(tmp_path: Path):
    manifest = write_manifest(tmp_path)
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    manifest.write_text(json.dumps(entries * 2), encoding="utf-8")
    library = ScriptureLibrary(tmp_path / "library.sqlite3")
    with pytest.raises(ManifestLoadError, match="duplicate"):
        library.import_manifest(manifest)
    manifest.write_text("{", encoding="utf-8")
    with pytest.raises(ManifestLoadError, match="Invalid JSON"):
        library.import_manifest(manifest)
    assert library.sources() == []
