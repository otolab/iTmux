"""tests/itmux/test_orchestrator.py - ProjectOrchestratorのテスト."""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from itmux.orchestrator import ProjectOrchestrator
from itmux.models import WindowConfig, ProjectConfig, WindowSize
from itmux.exceptions import (
    ProjectNotFoundError,
    ProjectNotOpenError,
    ProjectNotOpenReason,
    ITerm2Error,
)


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
            env=os.environ.copy()
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
            env=os.environ.copy()
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
            "project1": {"windows": ["editor", "server"], "count": 2, "description": None},
            "project2": {"windows": ["main"], "count": 1, "description": None},
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

        assert result == {"empty-project": {"windows": [], "count": 0, "description": None}}


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
            "test-project", windows, {}, cwd=None
        )

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
            "test-project", windows, {}, cwd=None
        )

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
            "test-project", windows, {}, cwd=None
        )

    @pytest.mark.asyncio
    @patch('itmux.orchestrator.ProjectOrchestrator._is_tmux_running')
    async def test_open_project_not_found(
        self, mock_is_tmux_running, mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """プロジェクトが存在しない場合は自動作成される."""
        # 最初のget_projectはProjectNotFoundErrorを発生
        # その後create_projectが呼ばれ、2回目のget_projectは成功
        mock_config_manager.get_project.side_effect = [
            ProjectNotFoundError("Project 'nonexistent' not found"),
            ProjectConfig(name="nonexistent", tmux_windows=[])
        ]

        # tmuxが起動していることをモック
        mock_is_tmux_running.return_value = True

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        # エラーは発生せず、プロジェクトが自動作成される
        await orchestrator.open("nonexistent")

        # create_projectが呼ばれたことを確認
        mock_config_manager.create_project.assert_called_once_with("nonexistent", windows=[])

    @pytest.mark.asyncio
    @patch('itmux.orchestrator.ProjectOrchestrator._is_tmux_running')
    async def test_open_passes_environments_to_bridge(
        self, mock_is_tmux_running,
        mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """open 時に environments を bridge へ渡す（シェル起動前適用）."""
        mock_is_tmux_running.return_value = True
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            environments={"MY_KEY": "my_value"},
            tmux_windows=[WindowConfig(name="editor")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.open("test-project")

        mock_iterm2_bridge.open_project_windows.assert_called_once_with(
            "test-project",
            [WindowConfig(name="editor")],
            {"MY_KEY": "my_value"},
            cwd=None,
        )

    @pytest.mark.asyncio
    @patch("itmux.orchestrator.apply_session_environments")
    @patch('itmux.orchestrator.ProjectOrchestrator._is_tmux_running')
    async def test_open_skips_env_when_all_windows_already_open(
        self, mock_is_tmux_running, mock_apply_env,
        mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """全ウィンドウが既に開いていても environments は適用."""
        mock_is_tmux_running.return_value = True
        mock_window = AsyncMock()
        mock_window.async_get_variable.return_value = "editor"
        mock_iterm2_bridge.find_windows_by_project.return_value = [mock_window]
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            environments={"FOO": "bar"},
            tmux_windows=[WindowConfig(name="editor")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.open("test-project")

        mock_iterm2_bridge.open_project_windows.assert_not_called()
        mock_apply_env.assert_called_once_with("test-project", {"FOO": "bar"})

    @pytest.mark.asyncio
    @patch('itmux.orchestrator.ProjectOrchestrator._is_tmux_running')
    async def test_open_passes_cwd_to_bridge(
        self, mock_is_tmux_running,
        mock_config_manager, mock_iterm2_bridge, mock_environ, tmp_path
    ):
        """open 時に cwd を bridge へ渡す."""
        mock_is_tmux_running.return_value = True
        cwd = tmp_path.resolve()
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            cwd=cwd,
            tmux_windows=[WindowConfig(name="editor")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.open("test-project")

        mock_iterm2_bridge.open_project_windows.assert_called_once_with(
            "test-project",
            [WindowConfig(name="editor")],
            {},
            cwd=cwd,
        )

    @pytest.mark.asyncio
    @patch('itmux.orchestrator.ProjectOrchestrator._is_tmux_running')
    async def test_open_skips_cwd_when_all_windows_already_open(
        self, mock_is_tmux_running,
        mock_config_manager, mock_iterm2_bridge, mock_environ, tmp_path
    ):
        """全ウィンドウが既に開いている場合は cwd を再適用しない."""
        mock_is_tmux_running.return_value = True
        cwd = tmp_path.resolve()
        mock_window = AsyncMock()
        mock_window.async_get_variable.return_value = "editor"
        mock_iterm2_bridge.find_windows_by_project.return_value = [mock_window]
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            cwd=cwd,
            tmux_windows=[WindowConfig(name="editor")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.open("test-project")

        mock_iterm2_bridge.open_project_windows.assert_not_called()

    @pytest.mark.asyncio
    @patch('itmux.orchestrator.ProjectOrchestrator._is_tmux_running')
    async def test_open_invalid_cwd_raises(
        self, mock_is_tmux_running,
        mock_config_manager, mock_iterm2_bridge, mock_environ
    ):
        """存在しない cwd で open は失敗."""
        from itmux.exceptions import CwdError

        mock_is_tmux_running.return_value = True
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            cwd=Path("/nonexistent/itmux-cwd-open"),
            tmux_windows=[WindowConfig(name="editor")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        with pytest.raises(CwdError):
            await orchestrator.open("test-project")


class TestAdd:
    """add() のテスト."""

    @pytest.mark.asyncio
    @patch("itmux.orchestrator.apply_session_environments")
    async def test_add_passes_cwd_to_bridge(
        self, mock_apply_env,
        mock_config_manager, mock_iterm2_bridge, tmp_path
    ):
        """add 時に cwd を bridge へ渡す."""
        cwd = tmp_path.resolve()
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            cwd=cwd,
            tmux_windows=[WindowConfig(name="window-1")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator.add("test-project", "window-2")

        mock_iterm2_bridge.add_window.assert_called_once_with(
            "test-project", "window-2", cwd=cwd
        )

    @pytest.mark.asyncio
    async def test_add_invalid_cwd_raises(
        self, mock_config_manager, mock_iterm2_bridge
    ):
        """存在しない cwd で add は失敗."""
        from itmux.exceptions import CwdError

        mock_config_manager.get_project.return_value = ProjectConfig(
            name="test-project",
            cwd=Path("/nonexistent/itmux-cwd-add"),
            tmux_windows=[WindowConfig(name="window-1")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        with pytest.raises(CwdError):
            await orchestrator.add("test-project", "window-2")

    @pytest.mark.asyncio
    async def test_add_raises_when_config_exists_but_not_open(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """config に存在するが iTerm2 で未オープンの場合."""
        mock_iterm2_bridge.get_tmux_connection.side_effect = ITerm2Error(
            "TmuxConnection not found for project: iTmux"
        )
        mock_subprocess.return_value = MagicMock(returncode=1)
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="iTmux",
            tmux_windows=[WindowConfig(name="window-1")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        with pytest.raises(ProjectNotOpenError) as exc_info:
            await orchestrator.add("iTmux")

        assert exc_info.value.reason is ProjectNotOpenReason.NOT_OPEN
        assert "iTerm2 で開いていません" in str(exc_info.value)
        assert "itmux open iTmux" in str(exc_info.value)
        mock_iterm2_bridge.add_window.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_raises_when_tmux_session_exists_but_detached(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """tmux セッションはあるが iTerm2 で未オープンの場合."""
        mock_iterm2_bridge.get_tmux_connection.side_effect = ITerm2Error(
            "TmuxConnection not found for project: iTmux"
        )
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_config_manager.get_project.return_value = ProjectConfig(
            name="iTmux",
            tmux_windows=[WindowConfig(name="window-1")],
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        with pytest.raises(ProjectNotOpenError) as exc_info:
            await orchestrator.add("iTmux")

        assert exc_info.value.reason is ProjectNotOpenReason.TMUX_DETACHED
        assert "tmux 上に存在しますが" in str(exc_info.value)
        assert "itmux open iTmux" in str(exc_info.value)
        mock_iterm2_bridge.add_window.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_raises_when_not_in_config_or_tmux(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """config にも tmux にも存在しない場合."""
        mock_iterm2_bridge.get_tmux_connection.side_effect = ITerm2Error(
            "TmuxConnection not found for project: iTmux"
        )
        mock_subprocess.return_value = MagicMock(returncode=1)
        mock_config_manager.get_project.side_effect = ProjectNotFoundError(
            "Project 'iTmux' not found"
        )

        orchestrator = ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

        with pytest.raises(ProjectNotOpenError) as exc_info:
            await orchestrator.add("iTmux")

        assert exc_info.value.reason is ProjectNotOpenReason.NOT_FOUND
        assert "設定に存在しません" in str(exc_info.value)
        assert "itmux open iTmux" in str(exc_info.value)
        mock_iterm2_bridge.add_window.assert_not_called()


class TestSyncDataProtection:
    """sync 時のユーザー設定保護."""

    def _orchestrator(self, mock_config_manager, mock_iterm2_bridge):
        return ProjectOrchestrator(mock_config_manager, mock_iterm2_bridge)

    def _no_session(self, mock_subprocess):
        mock_subprocess.return_value = MagicMock(returncode=1)

    def test_should_delete_window_only_project(
        self, mock_config_manager, mock_iterm2_bridge
    ):
        """ウィンドウ定義のみのプロジェクトは削除対象."""
        project = ProjectConfig(
            name="proj",
            tmux_windows=[WindowConfig(name="editor")],
        )
        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        assert orchestrator._should_delete_project_on_sync(project) is True

    def test_should_not_delete_with_cwd(
        self, mock_config_manager, mock_iterm2_bridge
    ):
        """cwd があるプロジェクトは削除しない."""
        project = ProjectConfig(
            name="proj",
            cwd=Path("/tmp"),
            tmux_windows=[WindowConfig(name="editor")],
        )
        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        assert orchestrator._should_delete_project_on_sync(project) is False

    def test_should_not_delete_with_environments(
        self, mock_config_manager, mock_iterm2_bridge
    ):
        """非空 environments があるプロジェクトは削除しない."""
        project = ProjectConfig(
            name="proj",
            environments={"FOO": "bar"},
            tmux_windows=[WindowConfig(name="editor")],
        )
        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        assert orchestrator._should_delete_project_on_sync(project) is False

    def test_should_not_delete_with_description(
        self, mock_config_manager, mock_iterm2_bridge
    ):
        """description があるプロジェクトは削除しない."""
        project = ProjectConfig(
            name="proj",
            description="my project",
            tmux_windows=[WindowConfig(name="editor")],
        )
        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        assert orchestrator._should_delete_project_on_sync(project) is False

    @pytest.mark.asyncio
    async def test_sync_single_preserves_cwd_clears_windows(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """セッション不在 + cwd → 削除せず tmux_windows をクリア."""
        self._no_session(mock_subprocess)
        project = ProjectConfig(
            name="proj",
            cwd=Path("/tmp"),
            tmux_windows=[WindowConfig(name="editor")],
        )
        mock_config_manager.get_project.return_value = project

        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator._sync_single_project("proj")

        mock_config_manager.delete_project.assert_not_called()
        mock_config_manager.update_project.assert_called_once_with("proj", [])

    @pytest.mark.asyncio
    async def test_sync_single_preserves_environments(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """セッション不在 + 非空 environments → 削除しない."""
        self._no_session(mock_subprocess)
        project = ProjectConfig(
            name="proj",
            environments={"FOO": "bar"},
            tmux_windows=[WindowConfig(name="editor")],
        )
        mock_config_manager.get_project.return_value = project

        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator._sync_single_project("proj")

        mock_config_manager.delete_project.assert_not_called()
        mock_config_manager.update_project.assert_called_once_with("proj", [])

    @pytest.mark.asyncio
    async def test_sync_single_deletes_window_only_project(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """セッション不在 + ウィンドウ定義のみ → 削除."""
        self._no_session(mock_subprocess)
        project = ProjectConfig(
            name="proj",
            tmux_windows=[WindowConfig(name="editor")],
        )
        mock_config_manager.get_project.return_value = project

        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator._sync_single_project("proj")

        mock_config_manager.delete_project.assert_called_once_with("proj")
        mock_config_manager.update_project.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_all_preserves_cwd(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """sync --all: セッション不在 + cwd → 削除しない."""
        self._no_session(mock_subprocess)
        project = ProjectConfig(
            name="proj",
            cwd=Path("/tmp"),
            tmux_windows=[WindowConfig(name="editor")],
        )
        mock_config_manager.list_projects.return_value = ["proj"]
        mock_config_manager.get_project.return_value = project

        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator._sync_all_projects()

        mock_config_manager.delete_project.assert_not_called()
        mock_config_manager.update_project.assert_called_once_with("proj", [])

    @pytest.mark.asyncio
    async def test_sync_all_deletes_window_only_project(
        self, mock_config_manager, mock_iterm2_bridge, mock_subprocess
    ):
        """sync --all: セッション不在 + ウィンドウ定義のみ → 削除."""
        self._no_session(mock_subprocess)
        project = ProjectConfig(
            name="proj",
            tmux_windows=[WindowConfig(name="editor")],
        )
        mock_config_manager.list_projects.return_value = ["proj"]
        mock_config_manager.get_project.return_value = project

        orchestrator = self._orchestrator(mock_config_manager, mock_iterm2_bridge)
        await orchestrator._sync_all_projects()

        mock_config_manager.delete_project.assert_called_once_with("proj")
        mock_config_manager.update_project.assert_not_called()
