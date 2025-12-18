"""iTerm2 Python API integration layer."""

import asyncio
import iterm2
from typing import Optional

from .models import WindowSize
from .exceptions import ITerm2Error, WindowCreationTimeoutError


class ITerm2Bridge:
    """iTerm2 Python APIとの連携を管理するクラス."""

    def __init__(self, connection: iterm2.Connection, app: iterm2.App):
        """
        Args:
            connection: iTerm2接続オブジェクト
            app: iTerm2アプリケーションオブジェクト
        """
        self.connection = connection
        self.app = app

    async def find_windows_by_project(self, project_name: str) -> list[iterm2.Window]:
        """プロジェクトに属するウィンドウを検索.

        Args:
            project_name: プロジェクト名

        Returns:
            list[iterm2.Window]: プロジェクトに属するウィンドウのリスト
        """
        matching_windows = []

        for window in self.app.windows:
            project_id = await window.async_get_variable("user.projectID")
            if project_id == project_name:
                matching_windows.append(window)

        return matching_windows

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

    async def detach_session(self, window_id: str) -> None:
        """tmuxセッションをデタッチ（ウィンドウを閉じる、セッションは保持）.

        Args:
            window_id: ウィンドウID

        Raises:
            ITerm2Error: ウィンドウが見つからない、またはデタッチに失敗
        """
        window = self.app.get_window_by_id(window_id)
        if window is None:
            raise ITerm2Error(f"Window not found: {window_id}")

        # ウィンドウをアクティブ化
        await window.async_activate()

        # tmux.Detach メニュー実行
        await self.app.async_select_menu_item("Shell", "tmux", "Detach")

        # 待機（ウィンドウが閉じるまで）
        await asyncio.sleep(0.5)

    async def attach_session(
        self,
        project_name: str,
        session_name: str,
        window_size: Optional[WindowSize] = None,
    ) -> str:
        """既存tmuxセッションにアタッチし、新ウィンドウを作成.

        Args:
            project_name: プロジェクト名
            session_name: tmuxセッション名
            window_size: ウィンドウサイズ（オプション）

        Returns:
            str: 作成されたウィンドウID

        Raises:
            WindowCreationTimeoutError: セッション作成がタイムアウト
            ITerm2Error: その他のiTerm2 APIエラー
        """
        try:
            # 1. 専用ゲートウェイウィンドウを作成
            gateway = await self.app.async_create_window()

            # 2. NewSessionMonitorで新セッション監視開始
            async with iterm2.NewSessionMonitor(self.connection) as monitor:
                # 3. tmux -CC attach-session コマンド送信
                session = gateway.current_tab.current_session
                cmd = f"tmux -CC attach-session -t {session_name}\n"
                await session.async_send_text(cmd)

                # 4. 新セッション作成を待つ（タイムアウト5秒）
                try:
                    new_session_id = await asyncio.wait_for(
                        monitor.async_get(), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    raise WindowCreationTimeoutError(
                        f"Session creation timed out for: {session_name}"
                    )

            # 5. セッションIDからWindowを取得
            window = await self.app.async_get_window_containing_session(new_session_id)
            new_window_id = window.window_id

            # 6. 新ウィンドウにタグ付け
            await window.async_set_variable("user.projectID", project_name)
            await window.async_set_variable("user.tmux_session", session_name)

            # 7. ウィンドウサイズ復元（オプション）
            if window_size is not None:
                await self.set_window_size(new_window_id, window_size)

            # 8. ゲートウェイクリーンアップ
            try:
                await gateway.async_close()
            except Exception:
                # クリーンアップ失敗は無視（ベストエフォート）
                pass

            return new_window_id

        except WindowCreationTimeoutError:
            raise
        except Exception as e:
            raise ITerm2Error(f"Failed to attach session: {e}") from e

    async def add_session(
        self,
        project_name: str,
        session_name: str,
    ) -> str:
        """新規tmuxセッションを作成し、プロジェクトに追加.

        Args:
            project_name: プロジェクト名
            session_name: tmuxセッション名

        Returns:
            str: 作成されたウィンドウID

        Raises:
            WindowCreationTimeoutError: セッション作成がタイムアウト
            ITerm2Error: その他のiTerm2 APIエラー
        """
        try:
            # 1. 専用ゲートウェイウィンドウを作成
            gateway = await self.app.async_create_window()

            # 2. NewSessionMonitorで新セッション監視開始
            async with iterm2.NewSessionMonitor(self.connection) as monitor:
                # 3. tmux -CC new-session コマンド送信
                session = gateway.current_tab.current_session
                cmd = f"tmux -CC new-session -s {session_name}\n"
                await session.async_send_text(cmd)

                # 4. 新セッション作成を待つ（タイムアウト5秒）
                try:
                    new_session_id = await asyncio.wait_for(
                        monitor.async_get(), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    raise WindowCreationTimeoutError(
                        f"Session creation timed out for: {session_name}"
                    )

            # 5. セッションIDからWindowを取得
            window = await self.app.async_get_window_containing_session(new_session_id)
            new_window_id = window.window_id

            # 6. 新ウィンドウにタグ付け
            await window.async_set_variable("user.projectID", project_name)
            await window.async_set_variable("user.tmux_session", session_name)

            # 7. ゲートウェイクリーンアップ
            try:
                await gateway.async_close()
            except Exception:
                # クリーンアップ失敗は無視（ベストエフォート）
                pass

            return new_window_id

        except WindowCreationTimeoutError:
            raise
        except Exception as e:
            raise ITerm2Error(f"Failed to add session: {e}") from e
