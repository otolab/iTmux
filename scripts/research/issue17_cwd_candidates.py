#!/usr/bin/env python3
"""Issue #17: attach 後の追加ウィンドウ cwd 候補 A〜D の実機検証.

Usage (iTerm2 内):
  /Applications/iTerm.app/Contents/Resources/it2run \\
    scripts/research/issue17_cwd_candidates.py [session_name]

Results are written to /tmp/issue17-cwd-results.json
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import iterm2
from iterm2.profile import InitialWorkingDirectory, LocalWriteOnlyProfile

SESSION_NAME = sys.argv[1] if len(sys.argv) > 1 else "e2e-test-project"
RESULT_PATH = Path("/tmp/issue17-cwd-results.json")

CWD_PATHS = {
    "A": Path("/tmp/issue17-cwd-a"),
    "B": Path("/tmp/issue17-cwd-b"),
    "C": Path("/tmp/issue17-cwd-c"),
    "D": Path("/tmp/issue17-cwd-d"),
    "baseline": Path("/tmp/issue17-cwd-a"),
}


@dataclass
class CandidateResult:
    candidate: str
    native_window: Optional[bool] = None
    startup_cwd_match: Optional[bool] = None
    pane_path: Optional[str] = None
    expected_path: Optional[str] = None
    operation_count: int = 0
    notes: list[str] = field(default_factory=list)
    error: Optional[str] = None


def count_iterm_windows(app: iterm2.App) -> int:
    return len(app.windows)


def window_has_single_tab(window: iterm2.Window) -> bool:
    return len(window.tabs) == 1


async def get_tmux_conn(
    connection: iterm2.Connection, session_name: str
) -> tuple[iterm2.TmuxConnection, iterm2.App]:
    app = await iterm2.async_get_app(connection)
    for conn in await iterm2.async_get_tmux_connections(connection):
        result = await conn.async_send_command("display-message -p '#{session_name}'")
        if result.strip() == session_name:
            return conn, app
    raise RuntimeError(
        f"No Control Mode connection for session {session_name!r}. "
        f"Attach with: tmux -CC attach -t {session_name}"
    )


async def pane_current_path(tmux_conn: iterm2.TmuxConnection, tmux_window_id: str) -> str:
    wid = tmux_window_id.lstrip("@")
    result = await tmux_conn.async_send_command(
        f"display-message -t @{wid} -p '#{{pane_current_path}}'"
    )
    return result.strip()


async def kill_test_window(tmux_conn: iterm2.TmuxConnection, tmux_window_id: str) -> None:
    wid = tmux_window_id.lstrip("@")
    await tmux_conn.async_send_command(f"kill-window -t @{wid}")


async def observe_window_creation(
    app: iterm2.App,
    tmux_conn: iterm2.TmuxConnection,
    create_fn,
) -> tuple[iterm2.Window, str, int, bool]:
    """Returns (window, tmux_window_id, op_count, native_window)."""
    windows_before = count_iterm_windows(app)
    tab_counts_before = {w.window_id: len(w.tabs) for w in app.windows}
    op_count = 0

    iterm_window = await create_fn()
    op_count += 1
    await asyncio.sleep(0.15)

    windows_after = count_iterm_windows(app)
    native_window = windows_after > windows_before

    if not native_window:
        for w in app.windows:
            before = tab_counts_before.get(w.window_id, 0)
            if len(w.tabs) > before:
                iterm_window = w
                break

    tab = iterm_window.current_tab
    tmux_window_id = str(tab.tmux_window_id) if tab.tmux_window_id else ""
    return iterm_window, tmux_window_id, op_count, native_window


async def test_a(tmux_conn, app, session_name, cwd) -> CandidateResult:
    result = CandidateResult("A", expected_path=str(cwd.resolve()))
    try:
        quoted = shlex.quote(str(cwd))
        await tmux_conn.async_send_command(
            f"set-option -t {session_name} default-path {quoted}"
        )
        result.operation_count += 1

        async def create():
            return await tmux_conn.async_create_window()

        window, wid, ops, native = await observe_window_creation(
            app, tmux_conn, create
        )
        result.operation_count += ops
        result.native_window = native
        result.pane_path = await pane_current_path(tmux_conn, wid)
        result.startup_cwd_match = result.pane_path == result.expected_path
        if not result.startup_cwd_match:
            result.notes.append("default-path did not apply to async_create_window()")
        await kill_test_window(tmux_conn, wid)
        result.operation_count += 1
        await tmux_conn.async_send_command(
            f"set-option -t {session_name} default-path ~"
        )
        result.operation_count += 1
    except Exception as exc:
        result.error = str(exc)
    return result


async def test_b(tmux_conn, app, session_name, cwd) -> CandidateResult:
    result = CandidateResult("B", expected_path=str(cwd.resolve()))
    try:

        async def create():
            return await tmux_conn.async_create_window()

        window, wid, ops, native = await observe_window_creation(
            app, tmux_conn, create
        )
        result.operation_count += ops
        result.native_window = native
        path = shlex.quote(str(cwd))
        await tmux_conn.async_send_command(
            f"send-keys -t @{wid.lstrip('@')} 'cd {path}' Enter"
        )
        result.operation_count += 1
        await asyncio.sleep(0.2)
        result.pane_path = await pane_current_path(tmux_conn, wid)
        result.startup_cwd_match = result.pane_path == result.expected_path
        result.notes.append("post-start cd; does not satisfy startup cwd requirement")
        await kill_test_window(tmux_conn, wid)
        result.operation_count += 1
    except Exception as exc:
        result.error = str(exc)
    return result


async def test_c(tmux_conn, app, session_name, cwd) -> CandidateResult:
    result = CandidateResult("C", expected_path=str(cwd.resolve()))
    try:

        async def create():
            return await tmux_conn.async_create_window()

        window, wid, ops, native = await observe_window_creation(
            app, tmux_conn, create
        )
        result.operation_count += ops
        result.native_window = native
        session = window.current_tab.current_session
        lwop = LocalWriteOnlyProfile()
        lwop.set_initial_directory_mode(
            InitialWorkingDirectory.INITIAL_WORKING_DIRECTORY_CUSTOM
        )
        lwop.set_custom_directory(str(cwd))
        await session.async_set_profile_properties(lwop)
        result.operation_count += 1
        await asyncio.sleep(0.1)
        result.pane_path = await pane_current_path(tmux_conn, wid)
        result.startup_cwd_match = result.pane_path == result.expected_path
        result.notes.append(
            "async_set_profile_properties on running tmux pane; no respawn"
        )
        await kill_test_window(tmux_conn, wid)
        result.operation_count += 1
    except Exception as exc:
        result.error = str(exc)
    return result


async def test_d_api(tmux_conn, app, session_name, cwd) -> CandidateResult:
    result = CandidateResult("D-api", expected_path=str(cwd.resolve()))
    try:
        path = shlex.quote(str(cwd))

        async def create():
            await tmux_conn.async_send_command(
                f"new-window -t {session_name} -c {path}"
            )
            await asyncio.sleep(0.05)
            matched = []
            for w in app.windows:
                for tab in w.tabs:
                    if tab.tmux_connection_id != tmux_conn.connection_id:
                        continue
                    twid = str(tab.tmux_window_id) if tab.tmux_window_id else None
                    if twid:
                        matched.append(w)
                        break
            if not matched:
                raise RuntimeError("window not found after new-window -c")
            matched.sort(key=lambda w: w.window_id)
            return matched[-1]

        window, wid, ops, native = await observe_window_creation(
            app, tmux_conn, create
        )
        result.operation_count += ops + 1
        result.native_window = native
        result.pane_path = await pane_current_path(tmux_conn, wid)
        result.startup_cwd_match = result.pane_path == result.expected_path
        result.notes.append("async_send_command new-window -c")
        await kill_test_window(tmux_conn, wid)
        result.operation_count += 1
    except Exception as exc:
        result.error = str(exc)
    return result


async def test_d_subprocess(
    tmux_conn, app, session_name, cwd
) -> CandidateResult:
    result = CandidateResult("D-subprocess", expected_path=str(cwd.resolve()))
    try:
        windows_before = count_iterm_windows(app)
        tab_counts_before = {w.window_id: len(w.tabs) for w in app.windows}
        subprocess.run(
            ["tmux", "new-window", "-t", session_name, "-c", str(cwd)],
            check=True,
            capture_output=True,
        )
        result.operation_count += 1
        await asyncio.sleep(0.15)
        windows_after = count_iterm_windows(app)
        result.native_window = windows_after > windows_before
        iterm_window = None
        wid = ""
        if not result.native_window:
            for w in app.windows:
                before = tab_counts_before.get(w.window_id, 0)
                if len(w.tabs) > before:
                    iterm_window = w
                    break
        else:
            new_windows = [w for w in app.windows if w.window_id not in tab_counts_before]
            if new_windows:
                iterm_window = new_windows[-1]
        if iterm_window is None:
            raise RuntimeError("window not found after subprocess new-window -c")
        wid = str(iterm_window.current_tab.tmux_window_id)
        result.pane_path = await pane_current_path(tmux_conn, wid)
        result.startup_cwd_match = result.pane_path == result.expected_path
        result.notes.append("subprocess tmux new-window -c")
        await kill_test_window(tmux_conn, wid)
        result.operation_count += 1
    except Exception as exc:
        result.error = str(exc)
    return result


async def test_baseline(tmux_conn, app, session_name, cwd) -> CandidateResult:
    result = CandidateResult("baseline(PR#16)", expected_path=str(cwd.resolve()))
    try:

        async def create():
            w = await tmux_conn.async_create_window()
            tab = w.current_tab
            wid = str(tab.tmux_window_id).lstrip("@")
            path = shlex.quote(str(cwd))
            await tmux_conn.async_send_command(
                f"respawn-pane -t @{wid} -c {path} -k"
            )
            await asyncio.sleep(0.1)
            return w

        window, wid, ops, native = await observe_window_creation(
            app, tmux_conn, create
        )
        result.operation_count += ops + 1
        result.native_window = native
        result.pane_path = await pane_current_path(tmux_conn, wid)
        result.startup_cwd_match = result.pane_path == result.expected_path
        result.notes.append("async_create_window + respawn-pane -c -k")
        await kill_test_window(tmux_conn, wid)
        result.operation_count += 1
    except Exception as exc:
        result.error = str(exc)
    return result


async def main(connection: iterm2.Connection) -> None:
    tmux_conn, app = await get_tmux_conn(connection, SESSION_NAME)
    results: list[CandidateResult] = []

    tests = [
        ("A", test_a, "A"),
        ("B", test_b, "B"),
        ("C", test_c, "C"),
        ("D-api", test_d_api, "D"),
        ("D-subprocess", test_d_subprocess, "D"),
        ("baseline(PR#16)", test_baseline, "baseline"),
    ]
    for _name, fn, cwd_key in tests:
        cwd = CWD_PATHS[cwd_key]
        r = await fn(tmux_conn, app, SESSION_NAME, cwd)
        results.append(r)
        await asyncio.sleep(0.2)

    payload: dict[str, Any] = {
        "session": SESSION_NAME,
        "iterm2_version": iterm2.__version__,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results": [asdict(r) for r in results],
    }
    RESULT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(json.dumps(payload, indent=2, ensure_ascii=False))


iterm2.run_until_complete(main)
