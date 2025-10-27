import json
from pathlib import Path

import pytest

from corpus import (
    ManifestLoadError,
    build_corpus_record,
    ingest_manifest,
    load_manifest,
    parse_structured_sections,
)


FIXTURE_DIR = Path(__file__).parent / "data"


def test_parse_structured_sections_handles_telugu_headings():
    text = (
        "## Ritual Name\nశ్రీ మహాగణపతి నిత్యపూజ\n"
        "## Sankalpa\nఓం తత్ సత్\n"
        "## Paddhati\n1. చేయాలి\n"
        "## Mantras\nఓం గం\n"
        "## Commentary\nవివరణ"
    )
    sections = parse_structured_sections(text)
    assert sections["ritual_name"] == "శ్రీ మహాగణపతి నిత్యపూజ"
    assert sections["sankalpa"].startswith("ఓం")
    assert "చేయాలి" in sections["paddhati"]


def test_parse_structured_sections_requires_all_parts():
    text = "## Ritual Name\nఉదాహరణ"
    with pytest.raises(ManifestLoadError):
        parse_structured_sections(text)


def test_ingest_manifest_writes_jsonl(tmp_path: Path):
    manifest_path = FIXTURE_DIR / "sample_manifest.json"
    output_path = tmp_path / "corpus.jsonl"
    records = ingest_manifest(manifest_path, output_path)
    assert output_path.exists()
    data = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert data[0]["source_id"] == "test_ganapati_source"
    assert data[0]["sections"]["ritual_name"].startswith("శ్రీ")
    assert len(data[0]["chunks"]) >= 1
    assert records[0].notes


def test_build_corpus_record_from_loaded_entry():
    entries = load_manifest(FIXTURE_DIR / "sample_manifest.json")
    entry = entries[0]
    text = (FIXTURE_DIR / "sample_source.txt").read_text(encoding="utf-8")
    record = build_corpus_record(entry, text)
    assert record.source_id == "test_ganapati_source"
    assert any(chunk["section"] == "mantras" for chunk in record.chunks)


def test_manifest_entry_resolves_relative_path():
    entries = load_manifest(FIXTURE_DIR / "sample_manifest.json")
    entry = entries[0]
    resolved = entry.resolve_path(FIXTURE_DIR)
    assert resolved == FIXTURE_DIR / "sample_source.txt"
