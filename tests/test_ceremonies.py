import json
from pathlib import Path

import pytest

from ceremonies import load_default_repository
from corpus import load_manifest
from server import _format_ceremony, _serialise_ceremony, build_tool_descriptions


TELUGU_RANGE = range(0x0C00, 0x0C80)
MANIFEST_PATH = Path("data/source_manifest.json")


@pytest.mark.parametrize(
    "identifier,expected_name",
    [
        ("ganapati_nityapuja", "శ్రీ మహాగణపతి నిత్యపూజ"),
        ("sudarshana_homa", "శ్రీ సుదర్శన నారసింహ హోమం"),
        ("upanayanam", "ఉపనయన సంస్కారం"),
        ("varalakshmi_vratam", "శ్రీ వారలక్ష్మీ వ్రతం"),
    ],
)
def test_repository_returns_telugu_names(identifier, expected_name):
    repository = load_default_repository()
    ceremony = repository.get(identifier)
    assert ceremony.pooja_name == expected_name
    assert ceremony.tradition and ord(ceremony.tradition[0]) in TELUGU_RANGE


def test_serialise_returns_full_json_payload():
    payload = _serialise_ceremony("upanayanam")
    assert set(payload.keys()) == {
        "pooja_name",
        "tradition",
        "lineage_reference",
        "script",
        "purpose",
        "muhurta_guidance",
        "sankalpa_format",
        "mantras",
        "procedure_steps",
        "region_specific_notes",
        "aftercare",
        "scriptural_sources",
        "knowledge_base_refs",
    }
    assert payload["script"] == "తెలుగు"
    assert all(ord(mantra["section"][0]) in TELUGU_RANGE for mantra in payload["mantras"])
    assert all("English:" in mantra["meaning"] for mantra in payload["mantras"])
    assert payload["knowledge_base_refs"]


def test_format_ceremony_emits_valid_json():
    payload = _serialise_ceremony("ganapati_nityapuja")
    message = _format_ceremony(payload)
    structured = json.loads(message)
    assert structured["pooja_name"].startswith("శ్రీ మహాగణపతి")
    assert structured["procedure_steps"][0]["name"] == "ఆచమన-శుద్ధి"
    assert structured["region_specific_notes"].startswith("తెలంగాణలో")
    assert structured["knowledge_base_refs"]


def test_tool_descriptions_are_localised():
    tools = build_tool_descriptions()
    names = {tool["name"] for tool in tools}
    assert {"ganapati_nityapuja", "sudarshana_homa", "upanayanam", "varalakshmi_vratam"} == names
    for tool in tools:
        assert tool["description"].endswith("తెలుగు మార్గదర్శనం")
        assert ord(tool["description"][0]) in TELUGU_RANGE


def test_knowledge_refs_exist_in_manifest():
    manifest_ids = {entry.id for entry in load_manifest(MANIFEST_PATH)}
    payload = _serialise_ceremony("sudarshana_homa")
    assert set(payload["knowledge_base_refs"]).issubset(manifest_ids)
