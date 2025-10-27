"""Utilities to load Telugu ceremony guidance for the MCP server."""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class Ceremony:
    """Rich metadata for a single Telugu ritual guidance record."""

    identifier: str
    pooja_name: str
    tradition: str
    lineage_reference: str
    script: str
    purpose: str
    muhurta_guidance: str
    sankalpa_format: str
    mantras: List[Dict[str, str]]
    procedure_steps: List[Dict[str, object]]
    region_specific_notes: str
    aftercare: str
    scriptural_sources: List[str]
    knowledge_base_refs: List[str]

    def as_payload(self) -> Dict[str, object]:
        """Return a payload that matches the mandated MCP JSON structure."""

        return {
            "pooja_name": self.pooja_name,
            "tradition": self.tradition,
            "lineage_reference": self.lineage_reference,
            "script": self.script,
            "purpose": self.purpose,
            "muhurta_guidance": self.muhurta_guidance,
            "sankalpa_format": self.sankalpa_format,
            "mantras": list(self.mantras),
            "procedure_steps": list(self.procedure_steps),
            "region_specific_notes": self.region_specific_notes,
            "aftercare": self.aftercare,
            "scriptural_sources": list(self.scriptural_sources),
            "knowledge_base_refs": list(self.knowledge_base_refs),
        }


class CeremonyRepository:
    """In-memory repository of ceremonies loaded from JSONL metadata."""

    def __init__(self, ceremonies: Dict[str, Ceremony]):
        self._ceremonies = dict(ceremonies)

    def identifiers(self) -> Iterable[str]:
        """Return available ceremony identifiers."""

        return self._ceremonies.keys()

    def get(self, identifier: str) -> Ceremony:
        """Fetch a ceremony by identifier.

        Raises:
            KeyError: if the identifier is not present in the repository.
        """

        try:
            return self._ceremonies[identifier]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise KeyError(f"Unknown ceremony: {identifier}") from exc


def _load_json_resource() -> List[Dict[str, object]]:
    """Load ceremony metadata from the embedded JSONL corpus."""

    records: List[Dict[str, object]] = []
    path = resources.files(__package__).joinpath("telugu_rituals.jsonl")
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def load_default_repository() -> CeremonyRepository:
    """Load ceremonies from the default JSONL metadata into a repository."""

    ceremonies = {}
    for entry in _load_json_resource():
        identifier = entry["id"]
        mantras = [
            {
                "section": mantra["section"],
                "text": mantra["text"],
                "meaning": mantra["meaning"],
            }
            for mantra in entry["mantras"]
        ]
        commentary = entry.get("commentary", "").strip()
        if commentary:
            region_notes = f"{entry['region_specific_notes']} {commentary}"
        else:
            region_notes = entry["region_specific_notes"]
        knowledge_refs = [ref for ref in entry.get("knowledge_base_refs", []) if ref]
        ceremony = Ceremony(
            identifier=identifier,
            pooja_name=entry["pooja_name"],
            tradition=entry["tradition"],
            lineage_reference=entry["lineage_reference"],
            script=entry["script"],
            purpose=entry["purpose"],
            muhurta_guidance=entry["muhurta_guidance"],
            sankalpa_format=entry["sankalpa_format"],
            mantras=mantras,
            procedure_steps=list(entry["procedure_steps"]),
            region_specific_notes=region_notes,
            aftercare=entry["aftercare"],
            scriptural_sources=list(entry["scriptural_sources"]),
            knowledge_base_refs=knowledge_refs,
        )
        ceremonies[identifier] = ceremony
    return CeremonyRepository(ceremonies)
