#!/usr/bin/env python3
"""Read-only Parameters crawl. Does not type values.

    uv run python scripts/inventory_section.py Body
"""
from __future__ import annotations

import json
import sys

from mcp_vroid.driver import inventory as INV
from mcp_vroid.driver import window as W


def main(argv: list[str] | None = None) -> int:
    section = (argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else "Body"
    W.focus()
    W.assert_vroid_focused()
    result = INV.inventory_section(section)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
