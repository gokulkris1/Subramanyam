"""Utilities for downloading and packaging ritual source documents."""
from __future__ import annotations

import argparse
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional
from urllib.parse import urlparse, unquote
from urllib.request import urlopen

from .ingest import ManifestLoadError, SourceManifestEntry, load_manifest

__all__ = [
    "DownloadError",
    "download_sources",
    "archive_downloads",
    "build_default_parser",
    "main",
]


class DownloadError(RuntimeError):
    """Raised when a ritual source could not be downloaded."""


@dataclass(frozen=True)
class DownloadedSource:
    """Metadata for a downloaded source document."""

    entry: SourceManifestEntry
    path: Path


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _derive_extension(entry: SourceManifestEntry) -> str:
    if entry.local_path:
        suffix = Path(entry.local_path).suffix
        if suffix:
            return suffix
    if entry.source_url:
        parsed = urlparse(entry.source_url)
        suffix = Path(unquote(parsed.path)).suffix
        if suffix:
            return suffix
    return f".{entry.format}" if entry.format and not entry.format.startswith(".") else entry.format


def _destination_for(entry: SourceManifestEntry, destination: Path) -> Path:
    extension = _derive_extension(entry)
    filename = entry.id
    if extension and not extension.startswith("."):
        filename = f"{filename}.{extension}"
    elif extension:
        filename = f"{filename}{extension}"
    return destination / filename


def _copy_local(entry: SourceManifestEntry, destination: Path, manifest_path: Path) -> Path:
    resolved = entry.resolve_path(manifest_path.parent)
    if resolved is None:
        raise DownloadError(f"Entry {entry.id} does not specify a local_path")
    if not resolved.exists():
        raise DownloadError(f"Local source not found for entry {entry.id}: {resolved}")
    shutil.copy2(resolved, destination)
    return destination


def _download_remote(entry: SourceManifestEntry, destination: Path) -> Path:
    if not entry.source_url:
        raise DownloadError(f"Entry {entry.id} does not define a source_url")
    parsed = urlparse(entry.source_url)
    if parsed.scheme == "file":
        resolved = Path(unquote(parsed.path))
        if not resolved.is_absolute():
            resolved = Path.cwd() / resolved
        if not resolved.exists():
            raise DownloadError(f"File URL not found for entry {entry.id}: {resolved}")
        shutil.copy2(resolved, destination)
        return destination
    try:
        with urlopen(entry.source_url) as response, destination.open("wb") as target:
            shutil.copyfileobj(response, target)
    except Exception as exc:  # pragma: no cover - network failures difficult to simulate
        raise DownloadError(f"Failed to download {entry.source_url}: {exc}") from exc
    return destination


def download_sources(
    manifest_path: str | Path,
    destination: str | Path,
    *,
    overwrite: bool = False,
) -> Dict[str, DownloadedSource]:
    """Download or copy each source described in the manifest into ``destination``.

    Returns a mapping of manifest entry identifiers to ``DownloadedSource`` records.
    """

    manifest_entries = load_manifest(manifest_path)
    manifest_file = Path(manifest_path)
    destination_path = Path(destination)
    _ensure_directory(destination_path)
    downloads: Dict[str, DownloadedSource] = {}
    for entry in manifest_entries:
        target_path = _destination_for(entry, destination_path)
        if target_path.exists() and not overwrite:
            downloads[entry.id] = DownloadedSource(entry=entry, path=target_path)
            continue
        if entry.local_path:
            completed_path = _copy_local(entry, target_path, manifest_file)
        else:
            completed_path = _download_remote(entry, target_path)
        downloads[entry.id] = DownloadedSource(entry=entry, path=completed_path)
    return downloads


def archive_downloads(downloads: Mapping[str, DownloadedSource], archive_path: str | Path) -> Path:
    """Create a zip archive containing the downloaded source files."""

    archive = Path(archive_path)
    _ensure_directory(archive.parent)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in downloads.values():
            arcname = item.path.name
            zf.write(item.path, arcname)
    return archive


def build_default_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser for the downloader."""

    parser = argparse.ArgumentParser(description="Download ritual sources into a local archive")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/source_manifest.json"),
        help="Path to the JSON manifest describing ritual sources.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("downloads"),
        help="Directory where downloaded sources should be stored.",
    )
    parser.add_argument(
        "--zip-output",
        type=Path,
        default=None,
        help="Optional path to a zip archive that will be created from the downloads.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite any existing files in the destination directory.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for ``python -m corpus.download``."""

    parser = build_default_parser()
    args = parser.parse_args(argv)
    try:
        downloads = download_sources(args.manifest, args.dest, overwrite=args.overwrite)
    except (ManifestLoadError, DownloadError) as exc:
        parser.error(str(exc))
    if args.zip_output is not None:
        archive_downloads(downloads, args.zip_output)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(main())
