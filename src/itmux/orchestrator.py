"""iTmux project orchestrator."""

import os
import subprocess
from typing import Optional

from .config import ConfigManager
from .iterm2_bridge import ITerm2Bridge
from .models import WindowConfig


class ProjectOrchestrator:
    """プロジェクトのopen/close/add/list機能を提供するオーケストレーター."""

    def __init__(self, config_manager: ConfigManager, iterm2_bridge: ITerm2Bridge):
        """
        Args:
            config_manager: 設定管理インスタンス
            iterm2_bridge: iTerm2ブリッジインスタンス
        """
        self.config = config_manager
        self.bridge = iterm2_bridge

    def _tmux_has_session(self, session_name: str) -> bool:
        """tmuxセッションが存在するか確認.

        Args:
            session_name: セッション名

        Returns:
            bool: セッションが存在すればTrue
        """
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
        )
        return result.returncode == 0

    def _generate_window_name(self, project_name: str) -> str:
        """ウィンドウ名を自動生成.

        Args:
            project_name: プロジェクト名

        Returns:
            str: 生成されたウィンドウ名（例: "window-1", "window-2"）
        """
        project = self.config.get_project(project_name)
        existing_windows = {w.name for w in project.tmux_windows}

        counter = 1
        while True:
            candidate = f"window-{counter}"
            if candidate not in existing_windows:
                return candidate
            counter += 1

    def list(self) -> dict:
        """プロジェクト一覧取得.

        Returns:
            dict: プロジェクト情報の辞書
                {
                    "project-name": {
                        "windows": ["window1", "window2"],
                        "count": 2
                    }
                }
        """
        result = {}
        for project_name in self.config.list_projects():
            project = self.config.get_project(project_name)
            result[project_name] = {
                "windows": [w.name for w in project.tmux_windows],
                "count": len(project.tmux_windows),
            }
        return result

    async def open(self, project_name: str) -> None:
        """プロジェクトを開く.

        Args:
            project_name: プロジェクト名

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
            ITerm2Error: iTerm2操作が失敗
        """
        # 1. プロジェクト設定取得
        project = self.config.get_project(project_name)

        # 2. プロジェクトのtmuxウィンドウを開く
        await self.bridge.open_project_windows(project_name, project.tmux_windows)

        # 3. 環境変数設定
        os.environ["ITMUX_PROJECT"] = project_name

    async def close(self, project_name: Optional[str] = None) -> None:
        """プロジェクトを閉じる（自動同期）.

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        # 1. プロジェクト名決定
        if project_name is None:
            project_name = os.environ.get("ITMUX_PROJECT")
            if project_name is None:
                raise ValueError("No project specified and ITMUX_PROJECT not set")

        # 2. プロジェクトウィンドウを検索
        windows = await self.bridge.find_windows_by_project(project_name)

        # 3. 現在の状態を取得（自動同期用）
        windows_config = []
        for window in windows:
            session_name = await window.async_get_variable("user.tmux_session")
            # ウィンドウサイズ取得（オプション）
            # TODO: 将来的にウィンドウサイズの保存を実装
            windows_config.append(WindowConfig(name=session_name))

        # 4. 設定を更新
        if windows_config:
            self.config.update_project(project_name, windows_config)

        # 5. 各ウィンドウをデタッチ
        for window in windows:
            await self.bridge.detach_session(window.window_id)

        # 6. 環境変数クリア
        if "ITMUX_PROJECT" in os.environ:
            del os.environ["ITMUX_PROJECT"]

    async def add(
        self, project_name: Optional[str] = None, window_name: Optional[str] = None
    ) -> None:
        """プロジェクトに新規ウィンドウ追加.

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得）
            window_name: ウィンドウ名（省略時は自動生成）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        # 1. プロジェクト名決定
        if project_name is None:
            project_name = os.environ.get("ITMUX_PROJECT")
            if project_name is None:
                raise ValueError("No project specified and ITMUX_PROJECT not set")

        # 2. ウィンドウ名決定
        if window_name is None:
            window_name = self._generate_window_name(project_name)

        # 3. 新規ウィンドウ作成（1ウィンドウ版のopen）
        window_config = WindowConfig(name=window_name)
        await self.bridge.open_project_windows(project_name, [window_config])

        # 4. 設定に追加
        self.config.add_window(project_name, window_config)
