"""tests/itmux/test_iterm2_bridge.py - ITerm2Bridgeのテスト."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from itmux.iterm2_bridge import ITerm2Bridge
from itmux.models import WindowSize
from itmux.exceptions import ITerm2Error, WindowCreationTimeoutError


class TestFindWindowsByProject:
    """find_windows_by_project()のテスト."""

    @pytest.mark.asyncio
    async def test_find_windows_with_matching_project(
        self, mock_iterm2_connection, mock_iterm2_app
    ):
        """プロジェクトIDが一致するウィンドウを検索."""
        # モックウィンドウを2つ作成
        window1 = AsyncMock()
        window1.window_id = "window-1"
        window1.async_get_variable = AsyncMock(return_value="test-project")

        window2 = AsyncMock()
        window2.window_id = "window-2"
        window2.async_get_variable = AsyncMock(return_value="other-project")

        window3 = AsyncMock()
        window3.window_id = "window-3"
        window3.async_get_variable = AsyncMock(return_value="test-project")

        mock_iterm2_app.windows = [window1, window2, window3]

        bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)
        result = await bridge.find_windows_by_project("test-project")

        assert len(result) == 2
        assert window1 in result
        assert window3 in result
        assert window2 not in result

    @pytest.mark.asyncio
    async def test_find_windows_no_match(
        self, mock_iterm2_connection, mock_iterm2_app
    ):
        """一致するウィンドウがない場合は空リスト."""
        window1 = AsyncMock()
        window1.async_get_variable = AsyncMock(return_value="other-project")

        mock_iterm2_app.windows = [window1]

        bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)
        result = await bridge.find_windows_by_project("test-project")

        assert result == []

    @pytest.mark.asyncio
    async def test_find_windows_variable_not_set(
        self, mock_iterm2_connection, mock_iterm2_app
    ):
        """変数が設定されていないウィンドウは除外."""
        window1 = AsyncMock()
        window1.async_get_variable = AsyncMock(return_value=None)

        window2 = AsyncMock()
        window2.async_get_variable = AsyncMock(return_value="test-project")

        mock_iterm2_app.windows = [window1, window2]

        bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)
        result = await bridge.find_windows_by_project("test-project")

        assert len(result) == 1
        assert window2 in result


class TestSetWindowSize:
    """set_window_size()のテスト."""

    @pytest.mark.asyncio
    async def test_set_window_size_success(
        self, mock_iterm2_connection, mock_iterm2_app
    ):
        """ウィンドウサイズ変更成功."""
        window = AsyncMock()
        window.window_id = "test-window-id"
        window.current_tab = AsyncMock()
        session = AsyncMock()
        session.async_send_text = AsyncMock()
        window.current_tab.current_session = session

        mock_iterm2_app.get_window_by_id = MagicMock(return_value=window)

        bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)
        window_size = WindowSize(columns=200, lines=60)

        await bridge.set_window_size("test-window-id", window_size)

        # tmux resize-window コマンドが送信されたことを確認
        session.async_send_text.assert_called_once()
        call_args = session.async_send_text.call_args[0][0]
        assert "tmux resize-window" in call_args
        assert "-x 200" in call_args
        assert "-y 60" in call_args

    @pytest.mark.asyncio
    async def test_set_window_size_window_not_found(
        self, mock_iterm2_connection, mock_iterm2_app
    ):
        """ウィンドウが見つからない場合はエラー."""
        mock_iterm2_app.get_window_by_id = MagicMock(return_value=None)

        bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)
        window_size = WindowSize(columns=200, lines=60)

        with pytest.raises(ITerm2Error, match="Window not found"):
            await bridge.set_window_size("nonexistent-id", window_size)


class TestDetachSession:
    """detach_session()のテスト."""

    @pytest.mark.asyncio
    async def test_detach_session_success(
        self, mock_iterm2_connection, mock_iterm2_app
    ):
        """セッションデタッチ成功."""
        window = AsyncMock()
        window.window_id = "test-window-id"
        window.async_activate = AsyncMock()

        mock_iterm2_app.get_window_by_id = MagicMock(return_value=window)
        mock_iterm2_app.async_select_menu_item = AsyncMock()

        bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)

        await bridge.detach_session("test-window-id")

        # ウィンドウがアクティブ化され、メニューが実行されたことを確認
        window.async_activate.assert_called_once()
        mock_iterm2_app.async_select_menu_item.assert_called_once_with(
            "Shell", "tmux", "Detach"
        )

    @pytest.mark.asyncio
    async def test_detach_session_window_not_found(
        self, mock_iterm2_connection, mock_iterm2_app
    ):
        """ウィンドウが見つからない場合はエラー."""
        mock_iterm2_app.get_window_by_id = MagicMock(return_value=None)

        bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)

        with pytest.raises(ITerm2Error, match="Window not found"):
            await bridge.detach_session("nonexistent-id")


class TestAttachSession:
    """attach_session()のテスト."""

    @pytest.mark.asyncio
    async def test_attach_session_success(
        self,
        mock_iterm2_connection,
        mock_iterm2_app,
        mock_window_creation_monitor,
    ):
        """セッションアタッチ成功."""
        # ゲートウェイウィンドウのモック
        gateway_window = AsyncMock()
        gateway_window.window_id = "gateway-window-id"
        gateway_window.current_tab = AsyncMock()
        gateway_session = AsyncMock()
        gateway_session.async_send_text = AsyncMock()
        gateway_window.current_tab.current_session = gateway_session
        gateway_window.async_close = AsyncMock()

        # 新規作成されるウィンドウのモック
        new_window = AsyncMock()
        new_window.window_id = "new-window-id"
        new_window.async_set_variable = AsyncMock()

        mock_iterm2_app.current_terminal_window = gateway_window

        # get_window_by_idは新規ウィンドウを返す
        mock_iterm2_app.get_window_by_id = MagicMock(return_value=new_window)

        # WindowCreationMonitorのモックを設定
        monitor_instance = mock_window_creation_monitor()

        with patch(
            "itmux.iterm2_bridge.iterm2.WindowCreationMonitor",
            return_value=monitor_instance,
            create=True,
        ):
            bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)
            result = await bridge.attach_session("test-project", "editor")

        # 返り値が新規ウィンドウIDであることを確認
        assert result == "new-window-id"

        # tmux -CC attach-session コマンドが送信されたことを確認
        gateway_session.async_send_text.assert_called()
        cmd = gateway_session.async_send_text.call_args[0][0]
        assert "tmux -CC attach-session -t editor" in cmd

        # タグ付けが実行されたことを確認
        new_window.async_set_variable.assert_any_call("user.projectID", "test-project")
        new_window.async_set_variable.assert_any_call("user.tmux_session", "editor")

        # ゲートウェイがクリーンアップされたことを確認
        gateway_window.async_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_attach_session_with_window_size(
        self,
        mock_iterm2_connection,
        mock_iterm2_app,
        mock_window_creation_monitor,
    ):
        """ウィンドウサイズ指定ありのアタッチ."""
        gateway_window = AsyncMock()
        gateway_window.window_id = "gateway-window-id"
        gateway_window.current_tab = AsyncMock()
        gateway_session = AsyncMock()
        gateway_session.async_send_text = AsyncMock()
        gateway_window.current_tab.current_session = gateway_session
        gateway_window.async_close = AsyncMock()

        new_window = AsyncMock()
        new_window.window_id = "new-window-id"
        new_window.async_set_variable = AsyncMock()
        new_window.current_tab = AsyncMock()
        new_session = AsyncMock()
        new_session.async_send_text = AsyncMock()
        new_window.current_tab.current_session = new_session

        mock_iterm2_app.current_terminal_window = gateway_window
        mock_iterm2_app.get_window_by_id = MagicMock(return_value=new_window)

        monitor_instance = mock_window_creation_monitor()

        with patch(
            "itmux.iterm2_bridge.iterm2.WindowCreationMonitor",
            return_value=monitor_instance,
            create=True,
        ):
            bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)
            window_size = WindowSize(columns=200, lines=60)
            result = await bridge.attach_session(
                "test-project", "editor", window_size=window_size
            )

        assert result == "new-window-id"

        # ウィンドウサイズ変更コマンドが送信されたことを確認
        new_session.async_send_text.assert_called()
        cmd = new_session.async_send_text.call_args[0][0]
        assert "tmux resize-window" in cmd
        assert "-x 200" in cmd
        assert "-y 60" in cmd

    @pytest.mark.asyncio
    async def test_attach_session_timeout(
        self,
        mock_iterm2_connection,
        mock_iterm2_app,
        mock_window_creation_monitor,
    ):
        """ウィンドウ作成タイムアウト."""
        gateway_window = AsyncMock()
        gateway_window.window_id = "gateway-window-id"
        gateway_window.current_tab = AsyncMock()
        gateway_session = AsyncMock()
        gateway_session.async_send_text = AsyncMock()
        gateway_window.current_tab.current_session = gateway_session

        mock_iterm2_app.current_terminal_window = gateway_window

        # タイムアウトを発生させるモニター
        class TimeoutMonitor:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def async_get(self):
                await asyncio.sleep(10)  # タイムアウトより長い

        with patch(
            "itmux.iterm2_bridge.iterm2.WindowCreationMonitor",
            return_value=TimeoutMonitor(),
            create=True,
        ):
            bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)

            with pytest.raises(WindowCreationTimeoutError):
                await bridge.attach_session("test-project", "editor")


class TestAddSession:
    """add_session()のテスト."""

    @pytest.mark.asyncio
    async def test_add_session_success(
        self,
        mock_iterm2_connection,
        mock_iterm2_app,
        mock_window_creation_monitor,
    ):
        """新規セッション作成成功."""
        gateway_window = AsyncMock()
        gateway_window.window_id = "gateway-window-id"
        gateway_window.current_tab = AsyncMock()
        gateway_session = AsyncMock()
        gateway_session.async_send_text = AsyncMock()
        gateway_window.current_tab.current_session = gateway_session
        gateway_window.async_close = AsyncMock()

        new_window = AsyncMock()
        new_window.window_id = "new-window-id"
        new_window.async_set_variable = AsyncMock()

        mock_iterm2_app.current_terminal_window = gateway_window
        mock_iterm2_app.get_window_by_id = MagicMock(return_value=new_window)

        monitor_instance = mock_window_creation_monitor()

        with patch(
            "itmux.iterm2_bridge.iterm2.WindowCreationMonitor",
            return_value=monitor_instance,
            create=True,
        ):
            bridge = ITerm2Bridge(mock_iterm2_connection, mock_iterm2_app)
            result = await bridge.add_session("test-project", "logs")

        assert result == "new-window-id"

        # tmux -CC new-session コマンドが送信されたことを確認
        gateway_session.async_send_text.assert_called()
        cmd = gateway_session.async_send_text.call_args[0][0]
        assert "tmux -CC new-session -s logs" in cmd

        # タグ付けが実行されたことを確認
        new_window.async_set_variable.assert_any_call("user.projectID", "test-project")
        new_window.async_set_variable.assert_any_call("user.tmux_session", "logs")
