"""Utilities for ingesting Telugu ritual source corpora."""

from .download import (
    DownloadError,
    archive_downloads,
    build_default_parser,
    download_sources,
)
from .ingest import (
    CorpusRecord,
    ManifestLoadError,
    SourceManifestEntry,
    build_corpus_record,
    ingest_manifest,
    load_manifest,
    parse_structured_sections,
)

__all__ = [
    "CorpusRecord",
    "ManifestLoadError",
    "SourceManifestEntry",
    "build_corpus_record",
    "download_sources",
    "archive_downloads",
    "build_default_parser",
    "DownloadError",
    "ingest_manifest",
    "load_manifest",
    "parse_structured_sections",
]
