"""Integration tests for the built-in HTTP server transport."""

from __future__ import annotations

import contextlib
import json
import threading
import time
from http.client import HTTPConnection
from typing import Dict

import pytest

from server import AGENT_MANIFEST, build_tool_descriptions, create_http_server


@contextlib.contextmanager
def running_server():
    """Run the HTTP server in a background thread for testing."""

    server = create_http_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # ensure the server socket is ready
        time.sleep(0.1)
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _request_json(server, method: str, path: str) -> Dict[str, object]:
    host, port = server.server_address
    connection = HTTPConnection(host, port, timeout=5)
    connection.request(method, path)
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    connection.close()
    if response.status != 200:
        pytest.fail(f"Request {method} {path} returned {response.status}: {body}")
    return json.loads(body)


def test_health_endpoint_reports_ok() -> None:
    with running_server() as server:
        payload = _request_json(server, "GET", "/healthz")
        assert payload == {"status": "ok"}


def test_manifest_endpoint_matches_embedded_manifest() -> None:
    with running_server() as server:
        payload = _request_json(server, "GET", "/manifest.json")
        assert payload == AGENT_MANIFEST


def test_list_ceremonies_matches_tool_descriptions() -> None:
    with running_server() as server:
        payload = _request_json(server, "GET", "/ceremonies")
        assert payload == {"tools": build_tool_descriptions()}


def test_get_ceremony_returns_payload() -> None:
    with running_server() as server:
        payload = _request_json(server, "GET", "/ceremonies/upanayanam")
        assert payload["pooja_name"] == "ఉపనయన సంస్కారం"


def test_call_tool_returns_wrapped_payload() -> None:
    with running_server() as server:
        payload = _request_json(server, "POST", "/tools/varalakshmi_vratam")
        assert payload["content"]["pooja_name"] == "శ్రీ వారలక్ష్మీ వ్రతం"


def test_stream_ceremony_emits_payload_event() -> None:
    with running_server() as server:
        host, port = server.server_address
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/ceremonies/sudarshana_homa/stream")
        response = connection.getresponse()
        assert response.status == 200
        body = response.read().decode("utf-8")
        connection.close()

        # SSE payload should end with the full ceremony payload
        events = [entry for entry in body.split("\n\n") if entry.strip()]
        payload_line = next(line for line in events if line.startswith("event: payload"))
        data_line = next(
            line for line in payload_line.splitlines() if line.startswith("data:")
        )
        payload = json.loads(data_line.split("data:", 1)[1].strip())
        assert payload["pooja_name"] == "శ్రీ సుదర్శన నారసింహ హోమం"
