"""End-to-end optional MCP integration: install the mcp extra to run this test."""

import asyncio
import json
from pathlib import Path
import sys
import zipfile
from xml.etree import ElementTree as ET

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_edit_export_and_restart(tmp_path, caplog):
    async def exercise():
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "bamboo", "mcp", "--workspace", str(tmp_path)],
        )

        async def call(client, name, **args):
            result = await client.call_tool(name, args)
            assert not result.isError, result.content
            return result.structuredContent

        async with stdio_client(server) as io, ClientSession(*io) as client:
            await client.initialize()
            assert {t.name for t in (await client.list_tools()).tools} == {
                "list_styles",
                "create_document",
                "list_documents",
                "read_document",
                "edit_document",
                "check_document",
                "export_document",
            }
            assert (
                "manuscript-notes" in (await call(client, "list_styles"))["page_styles"]
            )
            doc = await call(
                client,
                "create_document",
                page_style="manuscript-notes",
                book={"title": "读书记", "blocks": [{"text": "正文。"}]},
            )
            key = {"document_id": doc["document_id"]}
            pos = {"block_id": doc["block_ids"][0], "offset": 2}
            edit = {
                "type": "insert_text",
                "text": "续",
                "selection": {"anchor": pos, "focus": pos},
            }
            revised = await call(
                client, "edit_document", **key, expected_revision=0, commands=[edit]
            )
            assert revised["revision"] == 1
            for rev, cmds in [(0, [edit]), (1, [edit, {"type": "invalid"}])]:
                bad = await client.call_tool(
                    "edit_document", dict(**key, expected_revision=rev, commands=cmds)
                )
                assert bad.isError
            assert (await call(client, "check_document", **key))["pages"] == 1
            batch = await call(client, "export_document", **key)
            paths = {k: Path(v) for k, v in batch["files"].items()}
            assert all(
                p.is_relative_to(tmp_path / "exports") and p.is_file()
                for p in paths.values()
            )
            assert paths["pdf"].read_bytes().startswith(b"%PDF")
            assert "<svg" in paths["html"].read_text()
            with zipfile.ZipFile(paths["docx"]) as z:
                xml = ET.fromstring(z.read("word/document.xml"))
                w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                assert xml.find(".//" + w + "textDirection").get(w + "val") == "tbRl"
                assert "正文续" in "".join(t.text or "" for t in xml.iter(w + "t"))
            source = json.loads(paths["source"].read_text())
            assert source["blocks"][0]["inlines"][0]["text"] == "正文续。"
            assert source["profile"]["punctuation_color"] == "#d71920"
            second = await call(client, "export_document", **key, formats=["html"])
            assert Path(second["files"]["html"]).parent != paths["html"].parent
            assert "pdf" not in second["files"]
            missing = await client.call_tool(
                "read_document", {"document_id": "missing"}
            )
            assert missing.isError
        async with stdio_client(server) as io, ClientSession(*io) as client:
            await client.initialize()
            assert (await call(client, "list_documents"))["documents"] == [
                {**key, "title": "读书记", "revision": 1}
            ]
            saved = await call(client, "read_document", **key)
            assert saved["book"] == source and saved["revision"] == 1

    asyncio.run(exercise())
    assert "Failed to parse JSONRPC" not in caplog.text
