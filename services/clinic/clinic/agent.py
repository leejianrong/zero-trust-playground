"""A scripted stand-in for an AI agent that summarises patient records through MCP.

SIMULATION: in naive mode it obeys any line in a tool result that starts with
"ASSISTANT INSTRUCTION:", which is how a model that follows injected text behaves. It is a model
of that failure, not a measurement of any real model."""
import os
import re

from fastapi import FastAPI, HTTPException, Request

from .common import instrument, trace_var
from .mcp_client import data_of, open_session, text_of

app = instrument(FastAPI(title="agent"), "agent")
OBEY_INJECTED = os.environ.get("AGENT_OBEYS_INJECTED_TEXT", "true") == "true"
INSTRUCTION = re.compile(r"ASSISTANT INSTRUCTION:\s*call (\w+) with ([\w=, ]+)")


def injected_calls(text: str) -> list[tuple[str, dict]]:
    """Tool calls hidden in data, as (tool, arguments)."""
    calls = []
    for tool, args in INSTRUCTION.findall(text):
        pairs = [a.strip().split("=", 1) for a in args.split(",") if "=" in a]
        calls.append((tool, {k: int(v) if v.isdigit() else v for k, v in pairs}))
    return calls


async def summarise(session, obey: bool) -> dict:
    tool_calls = [{"tool": "list_patients", "origin": "task"}]
    first = await session.call_tool("list_patients")
    if first.is_error:
        return {"refused": text_of(first)}
    records = data_of(first)
    followed = []
    for record in records:
        for tool, args in injected_calls(" ".join(str(v) for v in record.values())) if obey else []:
            result = await session.call_tool(tool, args)
            call = {"tool": tool, "args": args, "origin": f"text in record {record['id']}"}
            if result.is_error:
                call["refused"] = text_of(result)  # the agent obeyed; whoever it acted for was not allowed
            followed.append(call)
    tool_calls += followed
    return {"summary": f"{len(records)} patients on file", "tool_calls": tool_calls, "obeyed_injected_text": bool(followed)}


@app.post("/tasks/summarise")
async def run_summarise(request: Request):
    trace = trace_var.get()
    async with open_session("agent", trace) as session:
        done = await summarise(session, OBEY_INJECTED)
    if "refused" in done:  # raised out here: inside the session, the task group would wrap it into a 500
        # Only a 401 or 403 from records-api is a refusal. Anything else is a failure, and says so.
        status = re.search(r"answered (\d{3})", done["refused"])
        raise HTTPException(403 if status and status.group(1) in ("401", "403") else 502, done["refused"])
    return done
