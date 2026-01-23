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

            # Connection確立後、tmux paneの初期化完了を待つ
            # Connection確立 ≠ paneが入力を受け付ける準備完了
            await asyncio.sleep(0.3)

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

            # フロー制御（%pause）によるview-mode遷移を防ぐため、
            # ウィンドウ作成直後にアクティブ化してPaused状態から復帰させる
            # 参考: docs/ideas/Tmuxウィンドウがview-modeに入る現象.md 6.2節
            await asyncio.sleep(0.05)
            await iterm_window.async_activate()

            # iTerm2ウィンドウにタグ付け（user.window_nameにIDを設定）
            await self.window_manager.tag_window(iterm_window, project_name, window_name)

            return iterm_window.window_id

        except Exception as e:
            raise ITerm2Error(f"Failed to add window: {e}") from e

    async def find_windows_by_tmux_session(
        self,
        tmux_conn: iterm2.TmuxConnection
    ) -> list[tuple[iterm2.Window, str, str]]:
        """tmuxセッションに属するiTerm2ウィンドウを検出.

        tmux list-windowsとtmux_connection_idを使って、
        セッションに属するiTerm2ウィンドウを正確に特定します。
        user.projectIDに依存しないため、デタッチ後の再アタッチでも正しく動作します。

        Args:
            tmux_conn: TmuxConnection

        Returns:
            list of (iterm2.Window, tmux_window_id, window_index)
        """
        # tmux list-windowsでセッションのウィンドウ一覧を取得
        result_str = await tmux_conn.async_send_command(
            "list-windows -F '#{window_index}:#{window_id}'"
        )
        lines = result_str.strip().split('\n') if result_str.strip() else []

        # tmux_window_id → window_index のマップ（@を除去）
        tmux_windows = {}
        for line in lines:
            parts = line.split(':')
            if len(parts) >= 2:
                window_index = parts[0]
                tmux_window_id = parts[1].lstrip('@')
                tmux_windows[tmux_window_id] = window_index

        # TmuxConnectionのIDを取得（セッションを特定するため）
        tmux_connection_id = tmux_conn.connection_id

        # iTerm2の全ウィンドウから、このセッションに属するものを探す
        matched_windows = []
        for window in self.app.windows:
            for tab in window.tabs:
                # セッションIDとウィンドウIDの両方で一致を確認
                if tab.tmux_connection_id != tmux_connection_id:
                    continue
                tmux_window_id = str(tab.tmux_window_id) if tab.tmux_window_id else None
                if tmux_window_id and tmux_window_id in tmux_windows:
                    matched_windows.append((window, tmux_window_id, tmux_windows[tmux_window_id]))
                    break  # 1ウィンドウにつき1タブのみチェック

        return matched_windows

    async def tag_session_windows(
        self,
        tmux_conn: iterm2.TmuxConnection,
        project_name: str,
        window_configs: list[WindowConfig]
    ) -> list[str]:
        """セッションの既存ウィンドウにタグ付けし、不足分を作成.

        Args:
            tmux_conn: TmuxConnection
            project_name: プロジェクト名
            window_configs: 必要なウィンドウ設定のリスト

        Returns:
            list[str]: 新規作成されたiTerm2ウィンドウIDのリスト
        """
        # セッションに属するウィンドウを検出
        matched_windows = await self.find_windows_by_tmux_session(tmux_conn)

        # window_index順にソート
        matched_windows.sort(key=lambda x: int(x[2]))

        # config名のセット
        config_names = {w.name for w in window_configs}
        tagged_names = set()
        created_window_ids = []

        # 既存ウィンドウにタグ付け（config順に対応させる）
        for i, (window, tmux_window_id, window_index) in enumerate(matched_windows):
            if i < len(window_configs):
                window_name = window_configs[i].name
            else:
                # configより多いウィンドウがある場合は自動命名
                counter = 1
                while True:
                    candidate = f"window-{counter}"
                    if candidate not in tagged_names and candidate not in config_names:
                        break
                    counter += 1
                window_name = candidate

            await self.window_manager.tag_window(window, project_name, window_name)
            tagged_names.add(window_name)

        # configにあるが既存ウィンドウがないものを作成
        for window_config in window_configs:
            if window_config.name not in tagged_names:
                iterm_window = await tmux_conn.async_create_window()

                # view-mode遷移防止
                await asyncio.sleep(0.05)
                await iterm_window.async_activate()

                await self.window_manager.tag_window(iterm_window, project_name, window_config.name)
                tagged_names.add(window_config.name)
                created_window_ids.append(iterm_window.window_id)

                # ウィンドウサイズ復元
                if window_config.window_size:
                    await self.set_window_size(iterm_window.window_id, window_config.window_size)

        return created_window_ids

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
            list[str]: 新規作成されたiTerm2ウィンドウIDのリスト

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

            # 4. 既存ウィンドウにタグ付けし、不足分を作成
            window_ids = await self.tag_session_windows(tmux_conn, project_name, window_configs)

            return window_ids

        except Exception as e:
            raise ITerm2Error(f"Failed to open project windows: {e}") from e
