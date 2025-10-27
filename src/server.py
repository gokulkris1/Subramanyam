"""Executable entry point for the Telugu Hindu ceremonies MCP server."""
from __future__ import annotations

import asyncio
import json
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


def run() -> None:
    """Synchronous wrapper that launches the asyncio MCP server."""

    asyncio.run(_run_async())


if __name__ == "__main__":  # pragma: no cover - manual invocation
    run()
