"""tests/itmux/test_cli.py - CLIコマンドのテスト."""

import pytest
from click.testing import CliRunner
from unittest.mock import AsyncMock, MagicMock, patch

from itmux.cli import main
from itmux.exceptions import ProjectNotFoundError, ITerm2Error, ConfigError


class TestList:
    """listコマンドのテスト."""

    def test_list_projects(self):
        """プロジェクト一覧表示."""
        runner = CliRunner()

        # orchestratorのモック
        mock_orchestrator = MagicMock()
        mock_orchestrator.list.return_value = {
            "project1": {"windows": ["editor", "server"], "count": 2},
            "project2": {"windows": ["main"], "count": 1},
        }

        # get_orchestratorを非同期関数としてモック
        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["list"])

        assert result.exit_code == 0
        assert "Projects:" in result.output
        assert "project1 (2 windows)" in result.output
        assert "editor" in result.output
        assert "server" in result.output
        assert "project2 (1 windows)" in result.output
        assert "main" in result.output

    def test_list_no_projects(self):
        """プロジェクトが0個."""
        runner = CliRunner()

        mock_orchestrator = MagicMock()
        mock_orchestrator.list.return_value = {}

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["list"])

        assert result.exit_code == 0
        assert "No projects configured." in result.output

    def test_list_config_error(self):
        """設定エラー."""
        runner = CliRunner()

        mock_orchestrator = MagicMock()
        mock_orchestrator.list.side_effect = ConfigError("Invalid config")

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["list"])

        assert result.exit_code == 1
        assert "✗ Config Error: Invalid config" in result.output


class TestOpen:
    """openコマンドのテスト."""

    def test_open_success(self):
        """プロジェクトを開く（成功）."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.open = AsyncMock()

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["open", "test-project"])

        assert result.exit_code == 0
        assert "✓ Opened project: test-project" in result.output
        mock_orchestrator.open.assert_called_once_with("test-project")

    def test_open_project_not_found(self):
        """存在しないプロジェクト."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.open.side_effect = ProjectNotFoundError(
            "Project 'nonexistent' not found"
        )

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["open", "nonexistent"])

        assert result.exit_code == 1
        assert "✗ Error: Project 'nonexistent' not found" in result.output

    def test_open_iterm2_error(self):
        """iTerm2エラー."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.open.side_effect = ITerm2Error("Connection failed")

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["open", "test-project"])

        assert result.exit_code == 1
        assert "✗ iTerm2 Error: Connection failed" in result.output


class TestClose:
    """closeコマンドのテスト."""

    def test_close_with_project_name(self):
        """プロジェクト名指定でクローズ."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.close = AsyncMock()

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["close", "test-project"])

        assert result.exit_code == 0
        assert "✓ Closed project: test-project" in result.output
        mock_orchestrator.close.assert_called_once_with("test-project")

    def test_close_without_project_name(self):
        """プロジェクト名省略."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.close = AsyncMock()

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["close"])

        assert result.exit_code == 0
        assert "✓ Closed project: current" in result.output
        mock_orchestrator.close.assert_called_once_with(None)

    def test_close_no_project_specified_error(self):
        """プロジェクト名未指定エラー."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.close.side_effect = ValueError(
            "No project specified and ITMUX_PROJECT not set"
        )

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["close"])

        assert result.exit_code == 1
        assert "✗ Error: No project specified" in result.output


class TestAdd:
    """addコマンドのテスト."""

    def test_add_with_both_args(self):
        """プロジェクト名とウィンドウ名を指定."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.add = AsyncMock()

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["add", "test-project", "new-session"])

        assert result.exit_code == 0
        assert "✓ Added window to project: test-project" in result.output
        mock_orchestrator.add.assert_called_once_with("test-project", "new-session")

    def test_add_with_project_only(self):
        """プロジェクト名のみ（ウィンドウ名自動生成）."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.add = AsyncMock()

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["add", "test-project"])

        assert result.exit_code == 0
        assert "✓ Added window to project: test-project" in result.output
        mock_orchestrator.add.assert_called_once_with("test-project", None)

    def test_add_without_args(self):
        """引数なし（環境変数から取得）."""
        runner = CliRunner()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.add = AsyncMock()

        async def mock_get_orchestrator():
            return mock_orchestrator

        with patch("itmux.cli.get_orchestrator", side_effect=mock_get_orchestrator):
            result = runner.invoke(main, ["add"])

        assert result.exit_code == 0
        assert "✓ Added window to project: current" in result.output
        mock_orchestrator.add.assert_called_once_with(None, None)
