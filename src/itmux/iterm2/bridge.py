"""iTerm2 Python API integration layer."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import iterm2

from ..models import WindowSize, WindowConfig
from ..exceptions import ITerm2Error
from ..gateway.gateway_manager import GatewayManager
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
        self.gateway_manager = GatewayManager()
        self.session_manager = SessionManager(connection, self.gateway_manager)
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

    async def detach_session(self, project_name: str) -> None:
        """tmuxセッションをデタッチ（ウィンドウを閉じる、セッションは保持）.

        Args:
            project_name: プロジェクト名

        Raises:
            ITerm2Error: デタッチに失敗
        """
        try:
            # TmuxConnection を取得
            tmux_conn = await self.session_manager.get_tmux_connection(project_name)

            # tmux detach-client コマンドを実行
            await tmux_conn.async_send_command("detach-client")

            # ウィンドウが閉じるのを待つ
            await asyncio.sleep(0.5)

        except Exception as e:
            raise ITerm2Error(f"Failed to detach session: {e}") from e

    async def connect_to_session(self, project_name: str, first_window_name: str = "default") -> None:
        """tmux Control Modeセッションに接続してGateway情報を保存.

        Args:
            project_name: プロジェクト名
            first_window_name: 最初のウィンドウ名

        Raises:
            ITerm2Error: 接続に失敗
        """
        try:
            # 1. Control Modeでtmuxセッションに接続
            # -A: セッションが存在しない場合は作成、存在する場合はアタッチ
            # -s: セッション名
            # -n: 最初のウィンドウ名
            gateway = await iterm2.Window.async_create(
                self.connection,
                command=f"/opt/homebrew/bin/tmux -CC new-session -A -s {project_name} -n {first_window_name}"
            )

            if not gateway:
                raise ITerm2Error("Failed to create gateway window")

            # 4. TmuxConnection取得（少し待機してから）
            await asyncio.sleep(1.0)
            tmux_conns = await iterm2.async_get_tmux_connections(self.connection)
            if not tmux_conns:
                raise ITerm2Error("Failed to get tmux connection")
            tmux_conn = tmux_conns[-1]  # 最新の接続

            # 5. 情報を保存
            self.gateway_manager.save(project_name, {
                "connection_id": tmux_conn.connection_id,
                "session_name": project_name,
                "created_at": datetime.now().isoformat()
            })

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

    async def get_tmux_windows(self, project_name: str) -> list[WindowConfig]:
        """プロジェクトのtmuxセッションから実際のウィンドウリストを取得.

        Args:
            project_name: プロジェクト名

        Returns:
            list[WindowConfig]: ウィンドウ設定のリスト

        Raises:
            ITerm2Error: tmuxコマンド実行に失敗
        """
        return await self.session_manager.get_tmux_windows(project_name)

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

    def _clear_gateway_info(self, project_name: str) -> None:
        """プロジェクトのGateway情報をクリア.

        Args:
            project_name: プロジェクト名
        """
        self.gateway_manager.clear(project_name)

    async def get_gateway_status(self, project_name: str) -> Optional[dict]:
        """プロジェクトのGateway情報を取得.

        Args:
            project_name: プロジェクト名

        Returns:
            Gateway情報の辞書、存在しない場合はNone
        """
        return self.gateway_manager.load(project_name)

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

            # ウィンドウ名を設定
            await tmux_conn.async_send_command(f"rename-window {window_name}")

            # iTerm2ウィンドウにタグ付け
            await self.window_manager.tag_window(iterm_window, project_name, window_name)

            return iterm_window.window_id

        except Exception as e:
            raise ITerm2Error(f"Failed to add window: {e}") from e

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
            result = await tmux_conn.async_send_command("list-windows -F '#{window_name}'")
            existing_window_names = set(result.strip().split('\n')) if result.strip() else set()

            # 5. 最初のウィンドウにタグ付け（connect_to_sessionで作成済み）
            await asyncio.sleep(0.5)  # ウィンドウ作成を待つ
            window_ids = []

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
                window_id = await self.window_manager.tag_window_by_tmux_id(
                    first_tmux_window_id, project_name, window_configs[0].name
                )
                if window_id:
                    window_ids.append(window_id)

            # 6. 2つ目以降のウィンドウを作成/タグ付け
            for window_config in window_configs[1:]:
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
                        window_id = await self.window_manager.tag_window_by_tmux_id(
                            target_tmux_window_id, project_name, window_config.name
                        )
                        if window_id:
                            window_ids.append(window_id)
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

                    window_ids.append(iterm_window.window_id)

            return window_ids

        except Exception as e:
            raise ITerm2Error(f"Failed to open project windows: {e}") from e
