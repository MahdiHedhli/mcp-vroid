"""session_env is a no-op on macOS and still fills Wayland vars on Linux."""
from __future__ import annotations

import sys

from mcp_vroid.session_env import ensure_session_env


def test_ensure_session_env_darwin_is_empty():
    if sys.platform != "darwin":
        return
    assert ensure_session_env() == {}
