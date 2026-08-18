"""tmuxセッションへの環境変数適用."""

import os
import subprocess
from typing import Optional


def tmux_has_session(session_name: str, env: Optional[dict[str, str]] = None) -> bool:
    """tmuxセッションが存在するか確認."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
        env=(env or os.environ).copy(),
    )
    return result.returncode == 0


def apply_session_environments(
    session_name: str,
    environments: dict[str, str],
    env: Optional[dict[str, str]] = None,
) -> bool:
    """tmuxセッションスコープの環境変数を適用.

    Args:
        session_name: tmuxセッション名（= プロジェクト名）
        environments: 適用する環境変数
        env: subprocess に渡す環境変数（省略時は os.environ）

    Returns:
        bool: 適用を試みた場合 True、スキップした場合 False
    """
    if not environments:
        return False

    if not tmux_has_session(session_name, env=env):
        return False

    run_env = (env or os.environ).copy()
    for key, value in environments.items():
        subprocess.run(
            ["tmux", "set-environment", "-t", session_name, key, value],
            capture_output=True,
            check=False,
            env=run_env,
        )
    return True
