"""iTmux project orchestrator."""

import os
import subprocess
from typing import Optional

from .config import ConfigManager
from .iterm2_bridge import ITerm2Bridge
from .models import SessionConfig


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

    def _generate_session_name(self, project_name: str) -> str:
        """セッション名を自動生成.

        Args:
            project_name: プロジェクト名

        Returns:
            str: 生成されたセッション名（例: "project-1", "project-2"）
        """
        project = self.config.get_project(project_name)
        existing_sessions = {s.name for s in project.tmux_sessions}

        counter = 1
        while True:
            candidate = f"{project_name}-{counter}"
            if candidate not in existing_sessions:
                return candidate
            counter += 1

    def list(self) -> dict:
        """プロジェクト一覧取得.

        Returns:
            dict: プロジェクト情報の辞書
                {
                    "project-name": {
                        "sessions": ["session1", "session2"],
                        "count": 2
                    }
                }
        """
        result = {}
        for project_name in self.config.list_projects():
            project = self.config.get_project(project_name)
            result[project_name] = {
                "sessions": [s.name for s in project.tmux_sessions],
                "count": len(project.tmux_sessions),
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

        # 2. 各セッションをアタッチ
        for session_config in project.tmux_sessions:
            # 2.1 tmuxセッション存在確認
            if not self._tmux_has_session(session_config.name):
                # 存在しない場合は新規作成
                await self.bridge.add_session(project_name, session_config.name)
            else:
                # 存在する場合はアタッチ
                await self.bridge.attach_session(
                    project_name,
                    session_config.name,
                    session_config.window_size,
                )

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
        sessions = []
        for window in windows:
            session_name = await window.async_get_variable("user.tmux_session")
            # ウィンドウサイズ取得（オプション）
            # TODO: 将来的にウィンドウサイズの保存を実装
            sessions.append(SessionConfig(name=session_name))

        # 4. 設定を更新
        if sessions:
            self.config.update_project(project_name, sessions)

        # 5. 各ウィンドウをデタッチ
        for window in windows:
            await self.bridge.detach_session(window.window_id)

        # 6. 環境変数クリア
        if "ITMUX_PROJECT" in os.environ:
            del os.environ["ITMUX_PROJECT"]

    async def add(
        self, project_name: Optional[str] = None, session_name: Optional[str] = None
    ) -> None:
        """プロジェクトに新規セッション追加.

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得）
            session_name: セッション名（省略時は自動生成）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        # 1. プロジェクト名決定
        if project_name is None:
            project_name = os.environ.get("ITMUX_PROJECT")
            if project_name is None:
                raise ValueError("No project specified and ITMUX_PROJECT not set")

        # 2. セッション名決定
        if session_name is None:
            session_name = self._generate_session_name(project_name)

        # 3. 新規セッション作成
        await self.bridge.add_session(project_name, session_name)

        # 4. 設定に追加
        self.config.add_session(project_name, SessionConfig(name=session_name))
