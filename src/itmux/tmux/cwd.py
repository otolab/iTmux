"""tmuxセッションへの作業ディレクトリ（cwd）適用."""

import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional

from ..exceptions import CwdError


def validate_cwd_path(cwd: Path) -> None:
    """cwd が存在するディレクトリか検証（runtime 用）.

    Args:
        cwd: 検証するパス

    Raises:
        CwdError: パスが存在しない、またはディレクトリでない
    """
    if not cwd.exists():
        raise CwdError(f"Directory does not exist: {cwd}")
    if not cwd.is_dir():
        raise CwdError(f"Not a directory: {cwd}")


def cwd_creation_args(cwd: Optional[Path]) -> list[str]:
    """tmux new-session / new-window の -c 引数."""
    if cwd is None:
        return []
    return ["-c", str(cwd)]


def list_session_pane_ids(
    session_name: str,
    env: Optional[dict[str, str]] = None,
) -> list[str]:
    """セッション内の全ペイン ID を取得."""
    run_env = (env or os.environ).copy()
    result = subprocess.run(
        ["tmux", "list-panes", "-t", session_name, "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def cd_pane(
    pane_id: str,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> None:
    """ペインのシェルに cd を送信."""
    run_env = (env or os.environ).copy()
    path = shlex.quote(str(cwd))
    subprocess.run(
        ["tmux", "send-keys", "-t", pane_id, f"cd {path}", "Enter"],
        capture_output=True,
        check=False,
        env=run_env,
    )


def apply_session_cwd(
    session_name: str,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> bool:
    """既存セッションの全ペインへ cwd を再適用（cd 送信）.

    Args:
        session_name: tmuxセッション名（= プロジェクト名）
        cwd: 適用する作業ディレクトリ
        env: subprocess に渡す環境変数（省略時は os.environ）

    Returns:
        bool: 適用を試みた場合 True、スキップした場合 False

    Raises:
        CwdError: cwd が無効なパス
    """
    validate_cwd_path(cwd)

    from .environment import tmux_has_session

    if not tmux_has_session(session_name, env=env):
        return False

    pane_ids = list_session_pane_ids(session_name, env=env)
    for pane_id in pane_ids:
        cd_pane(pane_id, cwd, env=env)
    return bool(pane_ids)
