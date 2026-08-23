#!/usr/bin/env python3
"""Start the server over stdio, list its tools, and call the read-only ones.

Never touches VRoid: it calls vroid_status (no input, no OCR) and, only if
`--screenshot` is passed AND a VRoid window exists, one passive capture. No
clicks, no keys.

    uv run python scripts/smoke_test.py [--screenshot]
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters, stdio_client

REPO = Path(__file__).resolve().parent.parent


async def main(screenshot: bool) -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_vroid"],
        cwd=str(REPO),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"initialized: {init.server_info.name} {init.server_info.version}")

            tools = (await session.list_tools()).tools
            print(f"\n{len(tools)} tools:")
            for t in tools:
                first = (t.description or "").strip().splitlines()[0]
                print(f"  - {t.name}: {first}")

            print("\nvroid_status:")
            res = await session.call_tool("vroid_status", {})
            for block in res.content:
                if getattr(block, "text", None):
                    print(block.text)
            if res.is_error:
                print("!! vroid_status returned an error")
                return 1

            present = bool((res.structured_content or {})
                           .get("window", {}).get("present"))
            if screenshot and present:
                print("\nvroid_screenshot (passive, no input):")
                shot = await session.call_tool("vroid_screenshot",
                                               {"tag": "smoke"})
                for block in shot.content:
                    kind = getattr(block, "type", "?")
                    if kind == "image":
                        print(f"  image: {len(block.data)} b64 chars, "
                              f"{block.mime_type}")
                    elif getattr(block, "text", None):
                        print("  " + block.text.replace("\n", "\n  "))
                if shot.is_error:
                    return 1
            elif screenshot:
                print("\nno VRoid window - skipping the screenshot check")
    print("\nsmoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(anyio.run(main, "--screenshot" in sys.argv))
