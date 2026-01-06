"""iTerm2 Python API integration layer."""

import asyncio
from pathlib import Path
from typing import Optional

import iterm2

from ..models import WindowSize, WindowConfig
from ..exceptions import ITerm2Error
from ..tmux.session_manager import SessionManager
from ..tmux.hook_manager import HookManager
from .window_manager import WindowManager


class ITerm2Bridge:
    """iTerm2 Python APIとの連携を管理するクラス.

    各種マネージャーを統合し、高レベルの操作を提供します。
    """

    def __init__(self, connection: iterm2.Connection, app: iterm2.App):
        """Initialize ITerm2Bridge.

        Args:
            connection: iTerm2接続オブジェクト
            app: iTerm2アプリケーションオブジェクト
        """
        self.connection = connection
        self.app = app

        # 各種マネージャーを初期化
        self.session_manager = SessionManager(connection)
        self.hook_manager = HookManager()
        self.window_manager = WindowManager(app)

    async def find_windows_by_project(self, project_name: str) -> list[iterm2.Window]:
        """プロジェクトに属するウィンドウを検索.

        Args:
            project_name: プロジェクト名

        Returns:
            list[iterm2.Window]: プロジェクトに属するウィンドウのリスト
        """
        return await self.window_manager.find_windows_by_project(project_name)

    async def set_window_size(
        self, window_id: str, window_size: WindowSize
    ) -> None:
        """ウィンドウサイズを変更.

        Args:
            window_id: ウィンドウID
            window_size: 変更後のウィンドウサイズ

        Raises:
            ITerm2Error: ウィンドウが見つからない、またはサイズ変更に失敗
        """
        window = self.app.get_window_by_id(window_id)
        if window is None:
            raise ITerm2Error(f"Window not found: {window_id}")

        # tmux resize-window コマンドを送信
        session = window.current_tab.current_session
        cmd = f"tmux resize-window -x {window_size.columns} -y {window_size.lines}\n"
        await session.async_send_text(cmd)

    async def connect_to_session(self, project_name: str, first_window_name: str = "default") -> None:
        """tmux Control Modeセッションに接続.

        Args:
            project_name: プロジェクト名
            first_window_name: 最初のウィンドウ名

        Raises:
            ITerm2Error: 接続に失敗
        """
        try:
            # Control Modeでtmuxセッションに接続
            # -A: セッションが存在しない場合は作成、存在する場合はアタッチ
            # -s: セッション名
            # -n: 最初のウィンドウ名
            gateway = await iterm2.Window.async_create(
                self.connection,
                command=f"/opt/homebrew/bin/tmux -CC new-session -A -s {project_name} -n {first_window_name}"
            )

            if not gateway:
                raise ITerm2Error("Failed to create gateway window")

            # TmuxConnection確立を待つ（ポーリング）
            for attempt in range(20):  # 最大2秒（0.1秒 × 20回）
                await asyncio.sleep(0.1)
                try:
                    await self.session_manager.get_tmux_connection(project_name)
                    break  # 接続確立完了
                except ITerm2Error:
                    if attempt == 19:
                        raise ITerm2Error(f"TmuxConnection not established after 2 seconds for project: {project_name}")
                    continue

        except Exception as e:
            raise ITerm2Error(f"Failed to connect to session: {e}") from e

    async def get_tmux_connection(self, project_name: str) -> iterm2.TmuxConnection:
        """プロジェクトのTmuxConnectionを取得.

        Args:
            project_name: プロジェクト名

        Returns:
            iterm2.TmuxConnection: Tmux接続

        Raises:
            ITerm2Error: TmuxConnection取得に失敗
        """
        return await self.session_manager.get_tmux_connection(project_name)

    async def setup_hooks(self, project_name: str, itmux_command: str = "itmux") -> None:
        """プロジェクトのtmuxセッションにhookを設定して自動同期を有効化.

        Args:
            project_name: プロジェクト名
            itmux_command: itmuxコマンドのパス（デフォルト: "itmux"）

        Raises:
            ITerm2Error: hook設定に失敗
        """
        try:
            tmux_conn = await self.get_tmux_connection(project_name)
            await self.hook_manager.setup_hooks(tmux_conn, project_name, itmux_command)
        except Exception as e:
            raise ITerm2Error(f"Failed to setup hooks: {e}") from e

    async def remove_hooks(self, project_name: str) -> None:
        """プロジェクトのtmuxセッションからhookを削除.

        Args:
            project_name: プロジェクト名
        """
        try:
            tmux_conn = await self.get_tmux_connection(project_name)
            await self.hook_manager.remove_hooks(tmux_conn, project_name)
        except Exception:
            pass

    async def add_window(self, project_name: str, window_name: str) -> str:
        """既存プロジェクトに新しいウィンドウを追加.

        Args:
            project_name: プロジェクト名
            window_name: ウィンドウ名

        Returns:
            str: 作成されたiTerm2ウィンドウID

        Raises:
            ITerm2Error: ウィンドウ作成に失敗
        """
        try:
            # TmuxConnection を取得
            tmux_conn = await self.get_tmux_connection(project_name)

            # 新しいウィンドウを作成（openと同じ方法）
            iterm_window = await tmux_conn.async_create_window()

            # ウィンドウ名を設定（async_create_windowで作成完了済み）
            await tmux_conn.async_send_command(f"rename-window {window_name}")

            # iTerm2ウィンドウにタグ付け
            await self.window_manager.tag_window(iterm_window, project_name, window_name)

            return iterm_window.window_id

        except Exception as e:
            raise ITerm2Error(f"Failed to add window: {e}") from e

    async def _get_existing_window_names(self, tmux_conn: iterm2.TmuxConnection) -> set[str]:
        """既存のtmuxウィンドウ名を取得.

        Args:
            tmux_conn: TmuxConnection

        Returns:
            set[str]: 既存のウィンドウ名のセット
        """
        result = await tmux_conn.async_send_command("list-windows -F '#{window_name}'")
        return set(result.strip().split('\n')) if result.strip() else set()

    async def _tag_first_window(
        self,
        tmux_conn: iterm2.TmuxConnection,
        project_name: str,
        first_window_name: str
    ) -> Optional[str]:
        """最初のウィンドウ（window 0）にタグ付け.

        Args:
            tmux_conn: TmuxConnection
            project_name: プロジェクト名
            first_window_name: 最初のウィンドウ名

        Returns:
            Optional[str]: タグ付けされたiTerm2ウィンドウID（失敗時はNone）
        """
        # tmux window 0（最初のウィンドウ）を探してタグ付け
        result = await tmux_conn.async_send_command("list-windows -F '#{window_index}:#{window_id}:#{window_name}'")
        lines = result.strip().split('\n') if result.strip() else []

        # window 0 を探す
        first_tmux_window_id = None
        for line in lines:
            parts = line.split(':')
            if len(parts) >= 3 and parts[0] == '0':
                # @記号を削除（iTerm2 APIの tmux_window_id は@なし）
                first_tmux_window_id = parts[1].lstrip('@')
                break

        if first_tmux_window_id:
            return await self.window_manager.tag_window_by_tmux_id(
                first_tmux_window_id, project_name, first_window_name
            )
        return None

    async def _create_or_tag_window(
        self,
        tmux_conn: iterm2.TmuxConnection,
        project_name: str,
        window_config: WindowConfig,
        existing_window_names: set[str]
    ) -> Optional[str]:
        """既存ウィンドウにタグ付け、または新規ウィンドウを作成.

        Args:
            tmux_conn: TmuxConnection
            project_name: プロジェクト名
            window_config: ウィンドウ設定
            existing_window_names: 既存のウィンドウ名のセット

        Returns:
            Optional[str]: iTerm2ウィンドウID（失敗時はNone）
        """
        if window_config.name in existing_window_names:
            # 既存のウィンドウにタグ付け
            result = await tmux_conn.async_send_command("list-windows -F '#{window_name}:#{window_id}'")
            lines = result.strip().split('\n') if result.strip() else []

            target_tmux_window_id = None
            for line in lines:
                parts = line.split(':')
                if len(parts) >= 2 and parts[0] == window_config.name:
                    target_tmux_window_id = parts[1].lstrip('@')
                    break

            if target_tmux_window_id:
                return await self.window_manager.tag_window_by_tmux_id(
                    target_tmux_window_id, project_name, window_config.name
                )
        else:
            # 新しいウィンドウを作成
            iterm_window = await tmux_conn.async_create_window()

            # ウィンドウ名を設定
            await tmux_conn.async_send_command(f"rename-window {window_config.name}")

            # iTerm2ウィンドウにタグ付け
            await self.window_manager.tag_window(iterm_window, project_name, window_config.name)

            # ウィンドウサイズ復元
            if window_config.window_size:
                await self.set_window_size(iterm_window.window_id, window_config.window_size)

            return iterm_window.window_id

        return None

    async def open_project_windows(
        self,
        project_name: str,
        window_configs: list[WindowConfig],
    ) -> list[str]:
        """プロジェクトのtmuxウィンドウを開く.

        1プロジェクト = 1 tmuxセッション で、複数のtmuxウィンドウを作成します。
        最低限1つのウィンドウが必要で、window_configs が空の場合は "default" という名前のウィンドウを作成します。

        Args:
            project_name: プロジェクト名
            window_configs: ウィンドウ設定のリスト（空の場合は default を作成）

        Returns:
            list[str]: 作成されたiTerm2ウィンドウIDのリスト

        Raises:
            ITerm2Error: iTerm2 APIエラー
        """
        try:
            # 1. window_configs が空なら default を追加
            if not window_configs:
                window_configs = [WindowConfig(name="default")]

            # 2. セッションに接続（最初のウィンドウ名を指定）
            await self.connect_to_session(project_name, window_configs[0].name)

            # 3. TmuxConnection を取得
            tmux_conn = await self.get_tmux_connection(project_name)

            # 4. 既存のtmuxウィンドウ名を取得
            existing_window_names = await self._get_existing_window_names(tmux_conn)

            # 5. 最初のウィンドウにタグ付け（connect_to_sessionで作成済み）
            window_ids = []
            first_window_id = await self._tag_first_window(
                tmux_conn, project_name, window_configs[0].name
            )
            if first_window_id:
                window_ids.append(first_window_id)

            # 6. 2つ目以降のウィンドウを作成/タグ付け
            for window_config in window_configs[1:]:
                window_id = await self._create_or_tag_window(
                    tmux_conn, project_name, window_config, existing_window_names
                )
                if window_id:
                    window_ids.append(window_id)

            return window_ids

        except Exception as e:
            raise ITerm2Error(f"Failed to open project windows: {e}") from e
