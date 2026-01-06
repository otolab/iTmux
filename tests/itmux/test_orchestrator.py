"""tests/itmux/test_orchestrator.py - ProjectOrchestratorのテスト."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from itmux.orchestrator import ProjectOrchestrator
from itmux.models import WindowConfig, ProjectConfig, WindowSize
from itmux.exceptions import ProjectNotFoundError


class TestHelpers:
    """ヘルパーメソッドのテスト."""

    def test_tmux_has_session_exists(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """セッションが存在する場合True."""
        mock_subprocess.return_value = MagicMock(returncode=0)

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        result = orchestrator._tmux_has_session("test-session")

        assert result is True
        mock_subprocess.assert_called_once_with(
            ["tmux", "has-session", "-t", "test-session"],
            capture_output=True,
        )

    def test_tmux_has_session_not_exists(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """セッションが存在しない場合False."""
        mock_subprocess.return_value = MagicMock(returncode=1)

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        result = orchestrator._tmux_has_session("nonexistent")

        assert result is False
        mock_subprocess.assert_called_once_with(
            ["tmux", "has-session", "-t", "nonexistent"],
            capture_output=True,
        )

    def test_generate_window_name_first(
        self, mock_config_manager, mock_iterm2_bridge
    ):
        """最初のウィンドウ名生成（window-1）."""
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project", tmux_windows=[]
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        result = orchestrator._generate_window_name("test-project")

        assert result == "window-1"

    def test_generate_window_name_avoid_collision(
        self, mock_config_manager, mock_iterm2_bridge
    ):
        """既存ウィンドウ名との衝突を回避."""
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            tmux_windows=[
                WindowConfig(name="window-1"),
                WindowConfig(name="window-2"),
            ],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        result = orchestrator._generate_window_name("test-project")

        assert result == "window-3"


class TestList:
    """list()のテスト."""

    def test_list_projects(self, mock_config_manager, mock_iterm2_bridge):
        """プロジェクト一覧取得."""
        mock_config_manager.list_projects.return_value = ["project1", "project2"]
        mock_config_manager.get_project.side_effect = [
            ProjectConfig(
                name="project1",
                tmux_windows=[
                    WindowConfig(name="editor"),
                    WindowConfig(name="server"),
                ],
            ),
            ProjectConfig(
                name="project2",
                tmux_windows=[WindowConfig(name="main")],
            ),
        ]

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        result = orchestrator.list()

        assert result == {
            "project1": {"windows": ["editor", "server"], "count": 2},
            "project2": {"windows": ["main"], "count": 1},
        }

    def test_list_empty_projects(self, mock_config_manager, mock_iterm2_bridge):
        """空のプロジェクトリスト."""
        mock_config_manager.list_projects.return_value = []

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        result = orchestrator.list()

        assert result == {}

    def test_list_project_with_no_windows(
        self, mock_config_manager, mock_iterm2_bridge
    ):
        """セッションが0個のプロジェクト."""
        mock_config_manager.list_projects.return_value = ["empty-project"]
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="empty-project", tmux_windows=[]
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        result = orchestrator.list()

        assert result == {"empty-project": {"windows": [], "count": 0}}


class TestOpen:
    """open()のテスト."""

    @pytest.mark.asyncio
    async def test_open_attach_existing_windows(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess, mock_environ
    ):
        """既存ウィンドウにアタッチ."""
        windows = [
            WindowConfig(name="editor"),
            WindowConfig(name="server"),
        ]
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            tmux_windows=windows,
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.open("test-project")

        # open_project_windowsが呼ばれる
        mock_iterm2_bridge.open_project_windows.assert_called_once_with(
            "test-project", windows
        )

        # 環境変数が設定される
        assert os.environ["ITMUX_PROJECT"] == "test-project"

    @pytest.mark.asyncio
    async def test_open_create_missing_windows(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess, mock_environ
    ):
        """セッション不在時に新規作成."""
        windows = [WindowConfig(name="new-session")]
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            tmux_windows=windows,
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.open("test-project")

        # open_project_windowsが呼ばれる
        mock_iterm2_bridge.open_project_windows.assert_called_once_with(
            "test-project", windows
        )

        # 環境変数が設定される
        assert os.environ["ITMUX_PROJECT"] == "test-project"

    @pytest.mark.asyncio
    async def test_open_with_window_size(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess, mock_environ
    ):
        """ウィンドウサイズ付きウィンドウ."""
        window_size = WindowSize(columns=200, lines=60)
        windows = [WindowConfig(name="editor", window_size=window_size)]
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            tmux_windows=windows,
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.open("test-project")

        # open_project_windowsが呼ばれる（ウィンドウサイズはWindowConfig内に含まれる）
        mock_iterm2_bridge.open_project_windows.assert_called_once_with(
            "test-project", windows
        )

    @pytest.mark.asyncio
    async def test_open_project_not_found(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """プロジェクトが存在しない."""
        mock_config_manager.get_project.side_effect = ProjectNotFoundError(
            "Project 'nonexistent' not found"
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        with pytest.raises(ProjectNotFoundError):
            await orchestrator.open("nonexistent")
