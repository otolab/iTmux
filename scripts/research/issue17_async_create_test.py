#!/usr/bin/env python3
"""Minimal async_create_window + respawn-pane test for Issue #17."""
import asyncio
import json
import shlex
import sys
from pathlib import Path

import iterm2

SESSION = sys.argv[1] if len(sys.argv) > 1 else "issue17-test"
CWD = Path("/tmp/issue17-cwd-a")
OUT = Path("/tmp/issue17-async-create-results.json")


async def main(connection):
    app = await iterm2.async_get_app(connection)
    tmux_conn = None
    for conn in await iterm2.async_get_tmux_connections(connection):
        name = (await conn.async_send_command("display-message -p '#{session_name}'")).strip()
        if name == SESSION:
            tmux_conn = conn
            break
    if not tmux_conn:
        raise RuntimeError(f"No CC connection for {SESSION}")

    windows_before = len(app.windows)
    tab_counts = {w.window_id: len(w.tabs) for w in app.windows}

    w = await tmux_conn.async_create_window()
    await asyncio.sleep(0.15)
    windows_after = len(app.windows)
    native = windows_after > windows_before

    tab = w.current_tab
    wid = str(tab.tmux_window_id).lstrip("@")
    path = shlex.quote(str(CWD))
    await tmux_conn.async_send_command(f"respawn-pane -t @{wid} -c {path} -k")
    await asyncio.sleep(0.15)
    pane_path = (
        await tmux_conn.async_send_command(
            f"display-message -t @{wid} -p '#{{pane_current_path}}'"
        )
    ).strip()

    await tmux_conn.async_send_command(f"kill-window -t @{wid}")

    result = {
        "method": "async_create_window + respawn-pane -c -k",
        "native_window": native,
        "startup_cwd_match": Path(pane_path).resolve() == CWD.resolve(),
        "pane_path": pane_path,
        "expected_path": str(CWD.resolve()),
        "operation_count": 3,
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


iterm2.run_until_complete(main)
