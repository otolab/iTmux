"""tests/conftest.py - pytest設定と共通フィクスチャ."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from itmux.models import WindowSize, SessionConfig


@pytest.fixture
def sample_window_size():
    """サンプルウィンドウサイズ."""
    return WindowSize(columns=200, lines=60)


@pytest.fixture
def sample_session():
    """サンプルセッション."""
    return SessionConfig(name="test_session")


# iTerm2 API モックフィクスチャ


@pytest.fixture
def mock_iterm2_connection():
    """iTerm2 Connection のモック."""
    connection = AsyncMock()
    return connection


@pytest.fixture
def mock_iterm2_app():
    """iTerm2 App のモック."""
    app = AsyncMock()
    app.windows = []
    app.get_window_by_id = MagicMock(return_value=None)
    app.async_select_menu_item = AsyncMock()
    return app


@pytest.fixture
def mock_iterm2_window():
    """iTerm2 Window のモック."""
    window = AsyncMock()
    window.window_id = "test-window-id"
    window.async_set_variable = AsyncMock()
    window.async_activate = AsyncMock()
    window.async_close = AsyncMock()
    return window


@pytest.fixture
def mock_iterm2_session():
    """iTerm2 Session のモック."""
    session = AsyncMock()
    session.async_send_text = AsyncMock()
    return session


@pytest.fixture
def mock_window_creation_monitor():
    """WindowCreationMonitor のモック（コンテキストマネージャ）."""

    class MockMonitor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def async_get(self):
            return "new-window-id"

    return MockMonitor
