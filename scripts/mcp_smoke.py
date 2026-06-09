from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]


def env_with_src() -> dict[str, str]:
    env = dict(os.environ)
    src = str(ROOT / "src")
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not current else src + os.pathsep + current
    return env


async def run(query: str, top_k: int, show_json: bool) -> None:
    params = StdioServerParameters(
        command=str(ROOT / ".venv" / "bin" / "python"),
        args=["-m", "kb.api.mcp_server"],
        env=env_with_src(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_by_name = {tool.name: tool for tool in tools.tools}
            tool = tool_by_name.get("kb_search")
            if tool is None:
                raise RuntimeError("kb_search not found in MCP tools")
            description = (tool.description or "").strip()
            if not description:
                raise RuntimeError("kb_search has no MCP tool description")
            print(f"tool: {tool.name}")
            print(f"description: {description.splitlines()[0]}")

            result = await session.call_tool("kb_search", {"query": query, "top_k": top_k})
            text = "\n".join(getattr(item, "text", "") for item in result.content).strip()
            payload = json.loads(text)
            if not payload.get("ok"):
                raise RuntimeError(payload)
            results = payload.get("results") or []
            top_doc = results[0]["doc_id"] if results else "NONE"
            print(f"query: {query}")
            print(f"top_doc: {top_doc}")
            if show_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test kb_search through the MCP stdio protocol.")
    parser.add_argument("query", nargs="?", default="春天")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--show-json", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.query, args.top_k, args.show_json))


if __name__ == "__main__":
    main()
