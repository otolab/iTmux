"""tmuxセッションへの環境変数適用."""

import os
import subprocess
from typing import Optional

# 環境変数適用前の一時ウィンドウ名（ユーザー向けシェルは起動しない）
BOOTSTRAP_WINDOW = "_itmux_bootstrap"


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


def prepare_session_environments(
    session_name: str,
    environments: dict[str, str],
    first_window_name: str,
    env: Optional[dict[str, str]] = None,
) -> bool:
    """シェル起動前にセッション環境変数を整える.

    新規セッションかつ environments がある場合は、一時ウィンドウで
    セッションだけ作成してから set-environment し、初回ウィンドウを作る。

    Args:
        session_name: tmuxセッション名
        environments: 適用する環境変数
        first_window_name: 初回ウィンドウ名
        env: subprocess に渡す環境変数

    Returns:
        bool: 新規セッションを作成した場合 True
    """
    run_env = (env or os.environ).copy()

    if tmux_has_session(session_name, env=run_env):
        apply_session_environments(session_name, environments, env=run_env)
        return False

    if environments:
        subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session_name,
                "-n",
                BOOTSTRAP_WINDOW,
            ],
            capture_output=True,
            check=False,
            env=run_env,
        )
        apply_session_environments(session_name, environments, env=run_env)
        if first_window_name != BOOTSTRAP_WINDOW:
            subprocess.run(
                ["tmux", "new-window", "-t", session_name, "-n", first_window_name],
                capture_output=True,
                check=False,
                env=run_env,
            )
            subprocess.run(
                [
                    "tmux",
                    "kill-window",
                    "-t",
                    f"{session_name}:{BOOTSTRAP_WINDOW}",
                ],
                capture_output=True,
                check=False,
                env=run_env,
            )
    else:
        subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session_name,
                "-n",
                first_window_name,
            ],
            capture_output=True,
            check=False,
            env=run_env,
        )

    return True
