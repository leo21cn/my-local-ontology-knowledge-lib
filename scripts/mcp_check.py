import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TOKEN = open(".env", encoding="utf-8").read().split("KB_AUTH_TOKEN=")[1].splitlines()[0]


async def main():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with streamablehttp_client(
        "http://127.0.0.1:8101/mcp/", headers=headers
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "kb_search",
                {"query": "ACCEPT-0042-UNIQUE", "corpus_id": "c01bc5ea859a", "top_k": 3},
            )
            records = []
            for content in result.content:
                text = content.text or ""
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list):
                    records.extend(parsed)
                elif isinstance(parsed, dict):
                    records.append(parsed)
            first = records[0] if records else None
            print(
                json.dumps(
                    {
                        "count": len(records),
                        "first_rel": first["asset_rel_path"] if first else None,
                        "anchor_sha": first["anchor"]["sha256"][:8] if first else None,
                        "score": first["score"] if first else None,
                    },
                    ensure_ascii=True,
                )
            )


asyncio.run(main())
