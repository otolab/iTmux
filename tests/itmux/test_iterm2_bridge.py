"""tests/itmux/test_iterm2_bridge.py - ITerm2Bridgeのテスト."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from itmux.iterm2.bridge import ITerm2Bridge
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