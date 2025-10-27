"""Executable entry points for the Telugu Hindu ceremonies MCP server."""
"""Executable entry point for the Telugu Hindu ceremonies MCP server."""
from __future__ import annotations

import asyncio
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple
from typing import Any, Dict, List

from ceremonies import load_default_repository

try:  # pragma: no cover - exercised only when real MCP runtime is installed
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
except Exception:  # pragma: no cover - defensive import
    Server = None  # type: ignore[assignment]
    stdio_server = None  # type: ignore[assignment]
    CallToolResult = None  # type: ignore[assignment]
    ListToolsResult = None  # type: ignore[assignment]
    TextContent = None  # type: ignore[assignment]
    Tool = None  # type: ignore[assignment]


AGENT_MANIFEST: Dict[str, Any] = {
    "name": "Telugu-Subramanyam-MCP",
    "version": "1.0.0",
    "description": "Telugu ritual MCP server supporting stdio and HTTPS transports.",
    "capabilities": {
        "listTools": True,
        "callTool": True,
        "sse": True,
        "http": True,
        "stdio": True,
    },
    "transport": {
        "type": "https",
        "basePath": "/",
        "endpoints": {
            "manifest": "/manifest.json",
            "listTools": "/ceremonies",
            "callTool": "/tools/{identifier}",
            "sse": "/ceremonies/{identifier}/stream",
        },
    },
    "contact": {
        "email": "support@telugu-subramanyam.local",
        "documentation": "https://github.com/your-org/Subramanyam",
    },
}


def _serialise_ceremony(identifier: str) -> Dict[str, Any]:
    """Return a serialised payload for the requested ceremony."""

    repository = load_default_repository()
    ceremony = repository.get(identifier)
    return ceremony.as_payload()


def build_tool_descriptions() -> List[Dict[str, str]]:
    """Return metadata describing each available ceremony tool."""

    repository = load_default_repository()
    descriptions = []
    for identifier in repository.identifiers():
        ceremony = repository.get(identifier)
        descriptions.append(
            {
                "name": identifier,
                "description": f"{ceremony.pooja_name} కోసం వివరమైన తెలుగు మార్గదర్శనం",
            }
        )
    return descriptions


async def _run_async() -> None:
    """Start the MCP server using stdio transport."""

    if Server is None or stdio_server is None:
        raise RuntimeError(
            "The 'mcp' package is required to run the server. Install the project dependencies."
        )

    repository = load_default_repository()
    server = Server("telugu-ceremony-guide")

    @server.list_tools()
    async def _list_tools() -> ListToolsResult:  # pragma: no cover - requires MCP runtime
        tools = [
            Tool(
                name=identifier,
                description=f"{repository.get(identifier).pooja_name} కోసం వివరమైన తెలుగు మార్గదర్శనం",
            )
            for identifier in repository.identifiers()
        ]
        return ListToolsResult(tools=tools)

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any] | None = None) -> CallToolResult:  # pragma: no cover
        ceremony = repository.get(name)
        content = TextContent(
            type="text",
            text=_format_ceremony(ceremony.as_payload()),
        )
        return CallToolResult(content=[content])

    async with stdio_server(server):
        await server.wait_closed()


def _format_ceremony(payload: Dict[str, Any]) -> str:
    """Format the ceremony guidance as a Telugu message."""

    return json.dumps(payload, ensure_ascii=False, indent=2)


class _CeremonyRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler exposing MCP-inspired endpoints."""

    server_version = "TeluguMCPHTTP/1.0"

    def _set_common_headers(self, status: HTTPStatus, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

    def _handle_not_found(self) -> None:
        payload = {"error": "Ceremony not found"}
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._set_common_headers(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8")
        self.wfile.write(encoded)

    def _json_response(self, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._set_common_headers(HTTPStatus.OK, "application/json; charset=utf-8")
        self.wfile.write(encoded)

    def _stream_response(self, identifier: str) -> None:
        try:
            payload = _serialise_ceremony(identifier)
        except KeyError:
            self._handle_not_found()
            return

        self._set_common_headers(HTTPStatus.OK, "text/event-stream; charset=utf-8")
        events = [{"event": "metadata", "data": {"identifier": identifier}}]
        events.extend(
            {"event": section.get("section", "content"), "data": section}
            for section in payload.get("mantras", [])
        )
        events.append({"event": "payload", "data": payload})

        for entry in events:
            event_line = f"event: {entry['event']}\n".encode("utf-8")
            data_line = f"data: {json.dumps(entry['data'], ensure_ascii=False)}\n\n".encode("utf-8")
            self.wfile.write(event_line)
            self.wfile.write(data_line)
            self.wfile.flush()

    def _parts(self) -> Tuple[str, ...]:
        path = self.path.split("?")[0]
        parts = tuple(filter(None, path.split("/")))
        return parts

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parts = self._parts()
        if not parts:
            self._handle_not_found()
            return

        if parts == ("healthz",):
            self._json_response({"status": "ok"})
            return

        if parts == ("manifest.json",):
            self._json_response(AGENT_MANIFEST)
            return

        if parts[0] == "ceremonies":
            if len(parts) == 1:
                self._json_response({"tools": build_tool_descriptions()})
                return
            if len(parts) == 2:
                identifier = parts[1]
                try:
                    payload = _serialise_ceremony(identifier)
                except KeyError:
                    self._handle_not_found()
                    return
                self._json_response(payload)
                return
            if len(parts) == 3 and parts[2] == "stream":
                self._stream_response(parts[1])
                return

        self._handle_not_found()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parts = self._parts()
        if len(parts) == 2 and parts[0] == "tools":
            identifier = parts[1]
            try:
                payload = _serialise_ceremony(identifier)
            except KeyError:
                self._handle_not_found()
                return
            self._json_response({"content": payload})
            return

        self._handle_not_found()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - match BaseHTTPRequestHandler
        """Suppress default logging to keep test output clean."""

        return


def create_http_server(host: str = "0.0.0.0", port: int = 8000) -> ThreadingHTTPServer:
    """Create a ThreadingHTTPServer configured with ceremony endpoints."""

    return ThreadingHTTPServer((host, port), _CeremonyRequestHandler)


def run_http(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Launch the standard library HTTP server."""

    env_host = os.getenv("MCP_HTTP_HOST")
    env_port = os.getenv("MCP_HTTP_PORT")
    if env_host:
        host = env_host
    if env_port:
        try:
            port = int(env_port)
        except ValueError as exc:  # pragma: no cover - defensive
            raise RuntimeError("MCP_HTTP_PORT must be an integer") from exc

    server = create_http_server(host=host, port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual termination
        pass
    finally:
        server.server_close()


def run() -> None:
    """Synchronous wrapper that launches the asyncio MCP server."""

    asyncio.run(_run_async())


if __name__ == "__main__":  # pragma: no cover - manual invocation
    run()
