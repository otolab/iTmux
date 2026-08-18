#!/usr/bin/env python3
"""Re-test B with async_activate (view-mode mitigation)."""
import asyncio
import json
import shlex
import sys
from pathlib import Path

import iterm2

SESSION = sys.argv[1] if len(sys.argv) > 1 else "issue17-test"
OUT = Path("/tmp/issue17-b-retest.json")


async def main(connection):
    app = await iterm2.async_get_app(connection)
    tmux_conn = None
    for conn in await iterm2.async_get_tmux_connections(connection):
        name = (await conn.async_send_command("display-message -p '#{session_name}'")).strip()
        if name == SESSION:
            tmux_conn = conn
            break
    cwd = Path("/tmp/issue17-cwd-b")
    w_before = len(app.windows)
    w = await tmux_conn.async_create_window()
    await asyncio.sleep(0.05)
    await w.async_activate()
    await asyncio.sleep(0.05)
    native = len(app.windows) > w_before
    wid = str(w.current_tab.tmux_window_id).lstrip("@")
    path = shlex.quote(str(cwd))
    await tmux_conn.async_send_command(f"send-keys -t @{wid} 'cd {path}' Enter")
    await asyncio.sleep(0.4)
    pp = (
        await tmux_conn.async_send_command(
            f"display-message -t @{wid} -p '#{{pane_current_path}}'"
        )
    ).strip()
    await tmux_conn.async_send_command(f"kill-window -t @{wid}")
    result = {
        "candidate": "B-retest",
        "native_window": native,
        "startup_cwd_match": Path(pp).resolve() == cwd.resolve(),
        "pane_path": pp,
        "expected_path": str(cwd.resolve()),
        "notes": ["async_activate before send-keys; still post-start cd"],
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


iterm2.run_until_complete(main)
