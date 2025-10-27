"""Manifest-driven ingestion utilities for Telugu ritual corpora."""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional
from urllib import request

__all__ = [
    "CorpusRecord",
    "ManifestLoadError",
    "SourceManifestEntry",
    "build_corpus_record",
    "ingest_manifest",
    "load_manifest",
    "parse_structured_sections",
]


class ManifestLoadError(RuntimeError):
    """Raised when a manifest or source document cannot be processed."""


@dataclass(frozen=True)
class SourceManifestEntry:
    """Metadata describing a single ritual source that should be ingested."""

    id: str
    title: str
    layer: str
    tradition: str
    source_url: str
    format: str
    chunk_size: int = 1800
    region: Optional[List[str]] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    local_path: Optional[str] = None

    def resolve_path(self, base_path: Path | None = None) -> Path | None:
        """Return a resolved local path for this entry, if one was provided."""

        if self.local_path is None:
            return None
        candidate = Path(self.local_path)
        if not candidate.is_absolute() and base_path is not None:
            candidate = (base_path / candidate).resolve()
        return candidate


@dataclass(frozen=True)
class CorpusRecord:
    """Structured corpus record derived from a manifest entry."""

    source_id: str
    title: str
    layer: str
    tradition: str
    sections: Mapping[str, str]
    chunks: List[Dict[str, str]]
    source_url: str
    tags: List[str]
    region: List[str]
    notes: str

    def to_json(self) -> Dict[str, object]:
        """Serialise the corpus record into a JSON-compatible dictionary."""

        return {
            "source_id": self.source_id,
            "title": self.title,
            "layer": self.layer,
            "tradition": self.tradition,
            "sections": dict(self.sections),
            "chunks": list(self.chunks),
            "source_url": self.source_url,
            "tags": list(self.tags),
            "region": list(self.region),
            "notes": self.notes,
        }


_SECTION_ALIASES: Dict[str, str] = {
    "ritual": "ritual_name",
    "ritual name": "ritual_name",
    "puja": "ritual_name",
    "puja name": "ritual_name",
    "పూజ పేరు": "ritual_name",
    "కార్య పేరు": "ritual_name",
    "సంకల్ప": "sankalpa",
    "సంకల్పం": "sankalpa",
    "sankalpa": "sankalpa",
    "పద్ధతి": "paddhati",
    "పద్దతి": "paddhati",
    "విధానం": "paddhati",
    "క్రమం": "paddhati",
    "paddhati": "paddhati",
    "procedure": "paddhati",
    "mantra": "mantras",
    "mantras": "mantras",
    "మంత్రాలు": "mantras",
    "ధ్యానం": "mantras",
    "commentary": "commentary",
    "వ్యాఖ్య": "commentary",
    "వ్యాఖ్యానం": "commentary",
}

_HEADING_RE = re.compile(r"^(?P<prefix>[#*]+)?\s*(?P<heading>[^:#*]+?)\s*(?:[#*]+)?\s*:?\s*$")
_REQUIRED_KEYS = {"ritual_name", "sankalpa", "paddhati", "mantras", "commentary"}


def load_manifest(path: str | Path) -> List[SourceManifestEntry]:
    """Load a manifest of ritual sources from a JSON file."""

    manifest_path = Path(path)
    if not manifest_path.exists():
        raise ManifestLoadError(f"Manifest file not found: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ManifestLoadError(f"Invalid JSON in manifest: {manifest_path}") from exc
    if not isinstance(data, list):
        raise ManifestLoadError("Manifest root must be a JSON array of entries")
    entries: List[SourceManifestEntry] = []
    for raw in data:
        if not isinstance(raw, dict):
            raise ManifestLoadError("Each manifest entry must be an object")
        try:
            entry = SourceManifestEntry(
                id=raw["id"],
                title=raw["title"],
                layer=raw["layer"],
                tradition=raw["tradition"],
                source_url=raw.get("source_url", ""),
                format=raw.get("format", "text"),
                chunk_size=int(raw.get("chunk_size", 1800)),
                region=list(raw.get("region", [])),
                notes=str(raw.get("notes", "")),
                tags=list(raw.get("tags", [])),
                local_path=raw.get("local_path"),
            )
        except KeyError as exc:  # pragma: no cover - defensive
            raise ManifestLoadError(f"Manifest entry missing field: {exc}") from exc
        entries.append(entry)
    return entries


def _match_heading(line: str) -> Optional[str]:
    """Return a heading string if the line looks like a section header."""

    stripped = line.strip()
    if not stripped:
        return None
    match = _HEADING_RE.match(stripped)
    if match:
        return match.group("heading").strip()
    # Support "Heading: text" inline format
    colon_index = stripped.find(":")
    if colon_index > 0:
        candidate = stripped[:colon_index].strip()
        if candidate.lower() in _SECTION_ALIASES:
            return candidate
    return None


def _normalise_heading(raw_heading: str) -> Optional[str]:
    key = raw_heading.strip().lower()
    return _SECTION_ALIASES.get(key)


def parse_structured_sections(text: str) -> Dict[str, str]:
    """Parse a ritual document into structured sections.

    The function recognises Telugu or English headings and returns a mapping
    with the canonical keys ``ritual_name``, ``sankalpa``, ``paddhati``,
    ``mantras``, and ``commentary``.
    """

    sections: Dict[str, List[str]] = {}
    current_key: Optional[str] = None
    buffer: List[str] = []
    for line in text.splitlines():
        heading = _match_heading(line)
        if heading:
            canonical = _normalise_heading(heading)
            if canonical:
                if current_key is not None:
                    sections[current_key] = [*sections.get(current_key, []), "\n".join(buffer).strip()]
                current_key = canonical
                buffer = []
                continue
        buffer.append(line)
    if current_key is not None:
        sections[current_key] = [*sections.get(current_key, []), "\n".join(buffer).strip()]

    flattened: Dict[str, str] = {}
    for key, values in sections.items():
        text_fragments = [fragment for fragment in values if fragment]
        flattened[key] = "\n\n".join(text_fragments).strip()

    missing = {key for key in _REQUIRED_KEYS if not flattened.get(key)}
    if missing:
        raise ManifestLoadError(f"Missing required sections: {', '.join(sorted(missing))}")
    return flattened


def _chunk_sections(sections: Mapping[str, str], chunk_size: int) -> Iterator[Dict[str, str]]:
    if chunk_size <= 0:
        raise ManifestLoadError("chunk_size must be positive")
    for name, text in sections.items():
        if not text:
            continue
        paragraph_buffer: List[str] = []
        current_length = 0
        for paragraph in text.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if current_length + len(paragraph) + (2 if paragraph_buffer else 0) > chunk_size and paragraph_buffer:
                yield {"section": name, "text": "\n\n".join(paragraph_buffer)}
                paragraph_buffer = [paragraph]
                current_length = len(paragraph)
            else:
                paragraph_buffer.append(paragraph)
                current_length += len(paragraph) + (2 if paragraph_buffer[:-1] else 0)
        if paragraph_buffer:
            yield {"section": name, "text": "\n\n".join(paragraph_buffer)}


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ManifestLoadError(
            "pdfminer.six is required to ingest PDF sources; install pdfminer.six"
        ) from exc
    buffer = io.BytesIO(raw_bytes)
    text = extract_text(buffer)
    return text


def _read_entry_text(entry: SourceManifestEntry, base_path: Path | None, fetcher) -> str:
    local_path = entry.resolve_path(base_path)
    if local_path and local_path.exists():
        if entry.format.lower() == "pdf":
            return _extract_pdf_text(local_path.read_bytes())
        return local_path.read_text(encoding="utf-8")
    if fetcher is not None:
        return fetcher(entry)
    if not entry.source_url:
        raise ManifestLoadError(f"Entry {entry.id} has no source_url or local_path")
    with request.urlopen(entry.source_url) as response:  # pragma: no cover - network
        raw = response.read()
    if entry.format.lower() == "pdf":
        return _extract_pdf_text(raw)
    return raw.decode("utf-8", errors="ignore")


def build_corpus_record(entry: SourceManifestEntry, text: str) -> CorpusRecord:
    sections = parse_structured_sections(text)
    chunks = list(_chunk_sections(sections, entry.chunk_size))
    return CorpusRecord(
        source_id=entry.id,
        title=entry.title,
        layer=entry.layer,
        tradition=entry.tradition,
        sections=sections,
        chunks=chunks,
        source_url=entry.source_url,
        tags=list(entry.tags or []),
        region=list(entry.region or []),
        notes=entry.notes or "",
    )


def ingest_manifest(
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    fetcher=None,
) -> List[CorpusRecord]:
    """Ingest every entry in ``manifest_path`` and serialise them to ``output_path``."""

    entries = load_manifest(manifest_path)
    base_path = Path(manifest_path).parent
    records: List[CorpusRecord] = []
    for entry in entries:
        text = _read_entry_text(entry, base_path, fetcher)
        record = build_corpus_record(entry, text)
        records.append(record)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_json(), ensure_ascii=False))
            handle.write("\n")
    return records
