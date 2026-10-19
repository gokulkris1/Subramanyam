import asyncio
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from corpus.library import ScriptureLibrary
from server import create_server
from test_library import write_manifest


def test_empty_library_status_and_tool_schemas(tmp_path: Path):
    async def check() -> None:
        server = create_server(tmp_path / "empty.sqlite3")
        tools = await server.list_tools()
        by_name = {tool.name: tool for tool in tools}
        assert len(tools) == 10
        for tool in tools:
            assert tool.inputSchema["type"] == "object"
        assert by_name["search_scriptures"].inputSchema["required"] == ["query"]
        assert "identifier" in by_name["get_ceremony"].inputSchema["required"]
    asyncio.run(check())


def test_real_installed_stdio_protocol(tmp_path: Path):
    database = tmp_path / "library.sqlite3"
    ScriptureLibrary(database).import_manifest(write_manifest(tmp_path))

    async def check() -> None:
        executable = Path(sys.executable).parent / "telugu-mcp-server"
        environment = {**os.environ, "TELUGU_MCP_DATABASE": str(database)}
        parameters = StdioServerParameters(
            command=str(executable), env=environment, cwd=str(tmp_path),
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "Telugu-Subramanyam"
                tools = await session.list_tools()
                assert len(tools.tools) == 10
                status = await session.call_tool("knowledge_status", {})
                assert not status.isError
                assert status.structuredContent is not None
                assert status.structuredContent["imported_sources"] == 1
                assert status.structuredContent["reviewed_sources"] == 1
                assert status.structuredContent["exhaustive"] is False
                result = await session.call_tool("search_scriptures", {"query": "పరీక్ష"})
                assert not result.isError
                assert result.structuredContent is not None
                passage = result.structuredContent["results"][0]
                fetched = await session.call_tool("get_passage", {"passage_id": passage["passage_id"]})
                assert fetched.structuredContent == passage
                for name in ("ganapati_nityapuja", "sudarshana_homa", "upanayanam", "varalakshmi_vratam"):
                    draft = await session.call_tool(name, {})
                    assert not draft.isError
                    assert draft.structuredContent is not None
                    assert draft.structuredContent["status"] == "unreviewed_draft"
                for name, arguments in [
                    ("get_ceremony", {"identifier": "unknown"}),
                    ("search_scriptures", {"query": " "}),
                    ("search_scriptures", {"query": "పరీక్ష", "limit": 51}),
                    ("get_passage", {"passage_id": "missing"}),
                ]:
                    error = await session.call_tool(name, arguments)
                    assert error.isError
                prompts = await session.list_prompts()
                assert {prompt.name for prompt in prompts.prompts} == {"telugu_pooja_agent", "telugu_scripture_study"}
                prompt = await session.get_prompt("telugu_pooja_agent", {"ritual": "గణపతి పూజ"})
                content = prompt.messages[0].content
                assert content.type == "text"
                assert "గణపతి పూజ" in content.text
                assert "Never invent mantras" in content.text
                resources = await session.list_resources()
                assert str(resources.resources[0].uri) == "subramanyam://guidance-policy"
                policy = await session.read_resource("subramanyam://guidance-policy")
                assert policy.contents[0].mimeType == "text/plain"
    asyncio.run(asyncio.wait_for(check(), timeout=30))
