"""Tests for the corpus download helpers."""
from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from corpus.download import DownloadError, archive_downloads, download_sources


def _make_manifest(tmp_path: Path, source_path: Path) -> Path:
    manifest = tmp_path / "manifest.json"
    data = [
        {
            "id": "local_test_source",
            "title": "పరీక్ష మూలం",
            "layer": "core_rituals_smarta",
            "tradition": "స్మార్త",
            "source_url": "",
            "format": "text",
            "local_path": str(source_path.relative_to(tmp_path)),
        }
    ]
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def test_download_sources_copies_local_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    source_file = source_dir / "ritual.txt"
    content = "శ్రీ మహాగణపతయే నమః"
    source_file.write_text(content, encoding="utf-8")

    manifest = _make_manifest(tmp_path, source_file)

    destination = tmp_path / "downloads"
    downloads = download_sources(manifest, destination)

    assert "local_test_source" in downloads
    downloaded_file = downloads["local_test_source"].path
    assert downloaded_file.exists()
    assert downloaded_file.read_text(encoding="utf-8") == content


def test_download_sources_overwrite(tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    source_file = source_dir / "ritual.txt"
    source_file.write_text("initial", encoding="utf-8")
    manifest = _make_manifest(tmp_path, source_file)
    destination = tmp_path / "downloads"

    download_sources(manifest, destination)

    # Change the source and force overwrite
    source_file.write_text("updated", encoding="utf-8")
    downloads = download_sources(manifest, destination, overwrite=True)

    downloaded_file = downloads["local_test_source"].path
    assert downloaded_file.read_text(encoding="utf-8") == "updated"


def test_archive_downloads(tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    source_file = source_dir / "ritual.txt"
    source_file.write_text("content", encoding="utf-8")
    manifest = _make_manifest(tmp_path, source_file)
    destination = tmp_path / "downloads"
    downloads = download_sources(manifest, destination)

    archive_path = tmp_path / "archives" / "bundle.zip"
    archive_downloads(downloads, archive_path)

    assert archive_path.exists()
    with ZipFile(archive_path, "r") as zf:
        assert set(zf.namelist()) == {downloads["local_test_source"].path.name}
        with zf.open(downloads["local_test_source"].path.name) as handle:
            assert handle.read().decode("utf-8") == "content"


def test_download_sources_missing_local_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.txt"
    manifest = _make_manifest(tmp_path, missing_path)
    destination = tmp_path / "downloads"

    with pytest.raises(DownloadError):
        download_sources(manifest, destination)
