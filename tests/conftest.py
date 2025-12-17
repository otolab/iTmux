"""tests/conftest.py - pytest設定と共通フィクスチャ."""

import pytest

from itmux.models import WindowSize, SessionConfig


@pytest.fixture
def sample_window_size():
    """サンプルウィンドウサイズ."""
    return WindowSize(columns=200, lines=60)


@pytest.fixture
def sample_session():
    """サンプルセッション."""
    return SessionConfig(name="test_session")
