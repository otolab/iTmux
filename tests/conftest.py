"""tests/conftest.py - pytest設定と共通フィクスチャ."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from itmux.models import WindowSize, SessionConfig, ProjectConfig


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


# Orchestrator用モックフィクスチャ


@pytest.fixture
def mock_config_manager():
    """ConfigManagerのモック."""
    config = MagicMock()
    config.get_project.return_value = ProjectConfig(
        name="test-project", tmux_sessions=[SessionConfig(name="session1")]
    )
    config.list_projects.return_value = ["test-project"]
    return config


@pytest.fixture
def mock_iterm2_bridge():
    """ITerm2Bridgeのモック（非同期）."""
    bridge = AsyncMock()
    bridge.find_windows_by_project.return_value = []
    bridge.attach_session.return_value = "window-id-1"
    bridge.add_session.return_value = "window-id-2"
    return bridge


@pytest.fixture
def mock_subprocess():
    """subprocessのモック."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        yield mock_run


@pytest.fixture
def mock_environ():
    """os.environのモック."""
    with patch.dict(os.environ, {}, clear=True):
        yield os.environ
