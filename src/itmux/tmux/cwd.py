"""tmuxセッションへの作業ディレクトリ（cwd）適用."""

import os
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


def set_session_working_directory(
    session_name: str,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> None:
    """セッションのデフォルト作業ディレクトリを更新（新規ウィンドウ/ペイン用）.

    tmux の attach-session -c を非対話で実行する。set-environment と同様、
    既存ペインのシェル cwd は変更しない。
    """
    run_env = (env or os.environ).copy()
    run_env.pop("TMUX", None)
    subprocess.run(
        ["tmux", "attach-session", "-t", session_name, "-c", str(cwd)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        env=run_env,
    )


def respawn_pane_cwd(
    pane_id: str,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> None:
    """既存ペインを再起動し、作業ディレクトリを設定."""
    run_env = (env or os.environ).copy()
    subprocess.run(
        ["tmux", "respawn-pane", "-k", "-t", pane_id, "-c", str(cwd)],
        capture_output=True,
        check=False,
        env=run_env,
    )


def apply_session_cwd(
    session_name: str,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> bool:
    """既存セッションへ cwd を再適用.

    1. attach-session -c でセッションのデフォルト作業ディレクトリを更新（新規用）
    2. 全ペインを respawn-pane -k -c で再起動（既存ペインの cwd を反映）

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

    set_session_working_directory(session_name, cwd, env=env)

    pane_ids = list_session_pane_ids(session_name, env=env)
    for pane_id in pane_ids:
        respawn_pane_cwd(pane_id, cwd, env=env)
    return bool(pane_ids)
