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
                    WindowConfig(name="session1"),
                    WindowConfig(name="session2"),
                ],
            ),
            ProjectConfig(
                name="project2",
                tmux_windows=[WindowConfig(name="session3")],
            ),
        ]

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        result = orchestrator.list()

        assert result == {
            "project1": {"windows": ["session1", "session2"], "count": 2},
            "project2": {"windows": ["session3"], "count": 1},
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
        """既存セッションにアタッチ."""
        windows = [
            WindowConfig(name="session1"),
            WindowConfig(name="session2"),
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
        """ウィンドウサイズ付きセッション."""
        window_size = WindowSize(columns=200, lines=60)
        windows = [WindowConfig(name="session1", window_size=window_size)]
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


class TestClose:
    """close()のテスト."""

    @pytest.mark.asyncio
    async def test_close_with_project_name(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """プロジェクト名指定でクローズ."""
        # モックウィンドウ設定
        window1 = AsyncMock()
        window1.window_id = "window-1"
        window1.async_get_variable = AsyncMock(return_value="session1")

        window2 = AsyncMock()
        window2.window_id = "window-2"
        window2.async_get_variable = AsyncMock(return_value="session2")

        mock_iterm2_bridge.find_windows_by_project.return_value = [window1, window2]

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.close("test-project")

        # update_projectが呼ばれる
        mock_config_manager.update_project.assert_called_once()
        args = mock_config_manager.update_project.call_args
        assert args[0][0] == "test-project"
        windows = args[0][1]
        assert len(windows) == 2
        assert windows[0].name == "session1"
        assert windows[1].name == "session2"

        # detach_sessionが呼ばれる
        assert mock_iterm2_bridge.detach_session.call_count == 2
        mock_iterm2_bridge.detach_session.assert_any_call("window-1")
        mock_iterm2_bridge.detach_session.assert_any_call("window-2")

    @pytest.mark.asyncio
    async def test_close_from_environment(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """環境変数からプロジェクト名取得."""
        os.environ["ITMUX_PROJECT"] = "env-project"

        mock_iterm2_bridge.find_windows_by_project.return_value = []

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.close()

        # env-projectでfind_windows_by_projectが呼ばれる
        mock_iterm2_bridge.find_windows_by_project.assert_called_once_with(
            "env-project"
        )

        # 環境変数がクリアされる
        assert "ITMUX_PROJECT" not in os.environ

    @pytest.mark.asyncio
    async def test_close_clears_environment(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """環境変数クリア."""
        os.environ["ITMUX_PROJECT"] = "test-project"

        mock_iterm2_bridge.find_windows_by_project.return_value = []

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.close("test-project")

        # 環境変数がクリアされる
        assert "ITMUX_PROJECT" not in os.environ

    @pytest.mark.asyncio
    async def test_close_no_windows(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """ウィンドウが0個の場合."""
        mock_iterm2_bridge.find_windows_by_project.return_value = []

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.close("test-project")

        # update_projectは呼ばれない（空リストの場合）
        mock_config_manager.update_project.assert_not_called()

        # detach_sessionは呼ばれない
        mock_iterm2_bridge.detach_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_no_project_specified(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """プロジェクト名未指定かつ環境変数なし."""
        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        with pytest.raises(ValueError, match="No project specified"):
            await orchestrator.close()


class TestAdd:
    """add()のテスト."""

    @pytest.mark.asyncio
    async def test_add_with_window_name(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """ウィンドウ名指定で追加."""
        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.add("test-project", "new-window")

        # open_project_windowsが呼ばれる（1ウィンドウのリスト）
        mock_iterm2_bridge.open_project_windows.assert_called_once()
        args = mock_iterm2_bridge.open_project_windows.call_args[0]
        assert args[0] == "test-project"
        assert len(args[1]) == 1
        assert args[1][0].name == "new-window"

        # config.add_windowが呼ばれる
        mock_config_manager.add_window.assert_called_once()
        args = mock_config_manager.add_window.call_args
        assert args[0][0] == "test-project"
        assert args[0][1].name == "new-window"

    @pytest.mark.asyncio
    async def test_add_auto_generate_window_name(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """ウィンドウ名自動生成."""
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project", tmux_windows=[]
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.add("test-project")

        # open_project_windowsが生成されたウィンドウ名で呼ばれる
        mock_iterm2_bridge.open_project_windows.assert_called_once()
        args = mock_iterm2_bridge.open_project_windows.call_args[0]
        assert args[0] == "test-project"
        assert len(args[1]) == 1
        assert args[1][0].name == "window-1"

        # config.add_windowが呼ばれる
        mock_config_manager.add_window.assert_called_once()
        args = mock_config_manager.add_window.call_args
        assert args[0][1].name == "window-1"

    @pytest.mark.asyncio
    async def test_add_from_environment(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """環境変数からプロジェクト名取得."""
        os.environ["ITMUX_PROJECT"] = "env-project"

        mock_config_manager.get_project.return_value = ProjectConfig(
            name="env-project", tmux_windows=[]
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.add()

        # env-projectで呼ばれる
        mock_iterm2_bridge.open_project_windows.assert_called_once()
        args = mock_iterm2_bridge.open_project_windows.call_args[0]
        assert args[0] == "env-project"
        assert args[1][0].name == "window-1"

    @pytest.mark.asyncio
    async def test_add_no_project_specified(
        self, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """プロジェクト名未指定かつ環境変数なし."""
        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        with pytest.raises(ValueError, match="No project specified"):
            await orchestrator.add()
