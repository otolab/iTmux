"""iTmux project orchestrator."""

import os
import subprocess
from typing import Optional

from .config import ConfigManager
from .iterm2 import ITerm2Bridge
from .models import WindowConfig
from .exceptions import ProjectNotFoundError


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

    def _resolve_project_name(self, project_name: Optional[str]) -> str:
        """プロジェクト名を解決（引数 or tmux session or 環境変数）.

        Args:
            project_name: プロジェクト名（Noneの場合は自動検出）

        Returns:
            str: 解決されたプロジェクト名

        Raises:
            ValueError: プロジェクト名が指定されておらず、tmuxセッションからも環境変数からも取得できない
        """
        if project_name is None:
            # 1. tmux内で実行されている場合、session名を取得
            if os.environ.get("TMUX"):
                try:
                    result = subprocess.run(
                        ["tmux", "display-message", "-p", "#{session_name}"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    project_name = result.stdout.strip()
                    if project_name:
                        return project_name
                except Exception:
                    # tmuxコマンド失敗時は次の方法を試す
                    pass

            # 2. 環境変数から取得（後方互換性）
            project_name = os.environ.get("ITMUX_PROJECT")
            if project_name is None:
                raise ValueError("No project specified and ITMUX_PROJECT not set")

        return project_name

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

        プロジェクトが存在しない場合は自動作成します。

        Args:
            project_name: プロジェクト名

        Raises:
            ITerm2Error: iTerm2操作が失敗
        """
        # 1. プロジェクト設定取得（存在しない場合は作成）
        try:
            project = self.config.get_project(project_name)
        except ProjectNotFoundError:
            # プロジェクトが存在しない → 空のプロジェクトを作成
            self.config.create_project(project_name, windows=[])
            project = self.config.get_project(project_name)

        # 2. プロジェクトのtmuxウィンドウを開く
        await self.bridge.open_project_windows(project_name, project.tmux_windows)

        # 3. hookを設定（自動同期）
        # itmuxコマンドのパスを取得（scripts/itmuxまたはインストール済み）
        import sys
        from pathlib import Path
        script_path = Path(__file__).parent.parent.parent / "scripts" / "itmux"
        itmux_command = str(script_path) if script_path.exists() else "itmux"
        # 既存のhookを削除してから再設定（冪等性のため）
        await self.bridge.remove_hooks(project_name)
        await self.bridge.setup_hooks(project_name, itmux_command)

        # 4. 環境変数設定
        os.environ["ITMUX_PROJECT"] = project_name

    async def sync(self, project_name: Optional[str] = None) -> None:
        """プロジェクトの状態を同期（tmuxセッション → config.json）.

        tmuxセッションが存在しない場合（全ウィンドウ削除でセッション終了）、
        プロジェクトをconfig.jsonから削除し、gateway情報もクリアします。

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        import sys
        print(f"[sync] START pid={os.getpid()}", file=sys.stderr)

        # 1. プロジェクト名決定
        project_name = self._resolve_project_name(project_name)
        print(f"[sync] project={project_name}", file=sys.stderr)

        # 2. tmuxセッションが存在するかチェック
        if not self._tmux_has_session(project_name):
            # セッション終了 → プロジェクトを削除
            print(f"[sync] Session not found, deleting project", file=sys.stderr)
            try:
                self.config.delete_project(project_name)
            except Exception:
                # プロジェクトが既に存在しない場合は無視
                pass
            print(f"[sync] END (session deleted)", file=sys.stderr)
            return

        # 3. tmuxセッションから実際のウィンドウリストを取得
        print(f"[sync] Getting tmux windows", file=sys.stderr)
        windows_config = await self.bridge.get_tmux_windows(project_name)
        print(f"[sync] Got {len(windows_config)} windows", file=sys.stderr)

        # 4. 設定を更新
        if windows_config:
            self.config.update_project(project_name, windows_config)
            print(f"[sync] Config updated", file=sys.stderr)

        print(f"[sync] END", file=sys.stderr)

    async def close(self, project_name: Optional[str] = None) -> None:
        """プロジェクトを閉じる（自動同期）.

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        # 1. プロジェクト名決定
        project_name = self._resolve_project_name(project_name)

        # 2. 同期
        await self.sync(project_name)

        # 3. hookを削除
        await self.bridge.remove_hooks(project_name)

        # 4. セッションをデタッチ
        await self.bridge.detach_session(project_name)

        # 5. 環境変数クリア
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
        project_name = self._resolve_project_name(project_name)

        # 2. ウィンドウ名決定
        if window_name is None:
            window_name = self._generate_window_name(project_name)

        # 3. 新規ウィンドウ作成
        await self.bridge.add_window(project_name, window_name)

        # 4. 設定に追加
        window_config = WindowConfig(name=window_name)
        self.config.add_window(project_name, window_config)
