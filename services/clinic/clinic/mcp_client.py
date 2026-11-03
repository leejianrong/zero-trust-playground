"""Open an MCP session over streamable HTTP with caller and trace headers attached."""
import contextlib
import json
import os

import httpx2
from mcp.client import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = os.environ.get("MCP_URL", "http://records-mcp.clinic.svc:8080/mcp")


@contextlib.asynccontextmanager
async def open_session(caller: str, trace: str | None = None, url: str = MCP_URL):
    headers = {"x-caller": caller, **({"x-trace-id": trace} if trace else {})}
    async with httpx2.AsyncClient(headers=headers, timeout=10) as http, \
            streamable_http_client(url, http_client=http) as (read, write, *_), \
            ClientSession(read, write) as session:
        await session.initialize()
        yield session


def text_of(result) -> str:
    return "".join(getattr(part, "text", "") for part in result.content)


def data_of(result):
    """The tool's return value. A tool that returns a list sends one text block per item, so prefer
    the structured result and fall back to parsing a single text block."""
    structured = result.structured_content
    if structured is not None:
        return structured.get("result", structured)
    return json.loads(text_of(result))
