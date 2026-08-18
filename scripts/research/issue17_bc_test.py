#!/usr/bin/env python3
"""Test candidates B and C on async_create_window path."""
import asyncio
import json
import shlex
import sys
from pathlib import Path

import iterm2
from iterm2.profile import InitialWorkingDirectory, LocalWriteOnlyProfile

SESSION = sys.argv[1] if len(sys.argv) > 1 else "issue17-test"
OUT = Path("/tmp/issue17-bc-results.json")


async def get_conn(connection, session):
    for conn in await iterm2.async_get_tmux_connections(connection):
        name = (await conn.async_send_command("display-message -p '#{session_name}'")).strip()
        if name == session:
            return conn
    raise RuntimeError("no conn")


async def pane_path(tmux_conn, wid):
    return (
        await tmux_conn.async_send_command(
            f"display-message -t @{wid} -p '#{{pane_current_path}}'"
        )
    ).strip()


async def test_b(tmux_conn, app, cwd):
    w_before = len(app.windows)
    w = await tmux_conn.async_create_window()
    await asyncio.sleep(0.1)
    native = len(app.windows) > w_before
    wid = str(w.current_tab.tmux_window_id).lstrip("@")
    path = shlex.quote(str(cwd))
    await tmux_conn.async_send_command(f"send-keys -t @{wid} 'cd {path}' Enter")
    await asyncio.sleep(0.25)
    pp = await pane_path(tmux_conn, wid)
    await tmux_conn.async_send_command(f"kill-window -t @{wid}")
    return {
        "candidate": "B",
        "native_window": native,
        "startup_cwd_match": Path(pp).resolve() == cwd.resolve(),
        "pane_path": pp,
        "expected_path": str(cwd.resolve()),
    }


async def test_c(tmux_conn, app, cwd):
    w_before = len(app.windows)
    w = await tmux_conn.async_create_window()
    await asyncio.sleep(0.1)
    native = len(app.windows) > w_before
    wid = str(w.current_tab.tmux_window_id).lstrip("@")
    session = w.current_tab.current_session
    lwop = LocalWriteOnlyProfile()
    lwop.set_initial_directory_mode(
        InitialWorkingDirectory.INITIAL_WORKING_DIRECTORY_CUSTOM
    )
    lwop.set_custom_directory(str(cwd))
    await session.async_set_profile_properties(lwop)
    await asyncio.sleep(0.1)
    pp = await pane_path(tmux_conn, wid)
    await tmux_conn.async_send_command(f"kill-window -t @{wid}")
    return {
        "candidate": "C",
        "native_window": native,
        "startup_cwd_match": Path(pp).resolve() == cwd.resolve(),
        "pane_path": pp,
        "expected_path": str(cwd.resolve()),
    }


async def main(connection):
    app = await iterm2.async_get_app(connection)
    tmux_conn = await get_conn(connection, SESSION)
    results = [
        await test_b(tmux_conn, app, Path("/tmp/issue17-cwd-b")),
        await test_c(tmux_conn, app, Path("/tmp/issue17-cwd-c")),
    ]
    OUT.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


iterm2.run_until_complete(main)
