"""tests/itmux/test_cwd.py - tmux cwd 適用のテスト."""

import os
import subprocess
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from itmux.exceptions import CwdError
from itmux.tmux.cwd import (
    apply_session_cwd,
    cwd_creation_args,
    list_session_pane_ids,
    respawn_pane_cwd,
    set_session_working_directory,
    validate_cwd_path,
)


class TestValidateCwdPath:
    """validate_cwd_path() のテスト."""

    def test_valid_directory(self, tmp_path):
        """存在するディレクトリは通過."""
        validate_cwd_path(tmp_path.resolve())

    def test_nonexistent_raises(self):
        """存在しないパスは CwdError."""
        with pytest.raises(CwdError, match="does not exist"):
            validate_cwd_path(Path("/nonexistent/itmux-cwd-test"))

    def test_file_raises(self, tmp_path):
        """ファイルパスは CwdError."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")
        with pytest.raises(CwdError, match="Not a directory"):
            validate_cwd_path(file_path.resolve())


class TestCwdCreationArgs:
    """cwd_creation_args() のテスト."""

    def test_none_returns_empty(self):
        assert cwd_creation_args(None) == []

    def test_path_returns_c_flag(self, tmp_path):
        path = tmp_path.resolve()
        assert cwd_creation_args(path) == ["-c", str(path)]


class TestListSessionPaneIds:
    """list_session_pane_ids() のテスト."""

    @patch("itmux.tmux.cwd.subprocess.run")
    def test_returns_pane_ids(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="%1\n%2\n")

        result = list_session_pane_ids("my-project")

        assert result == ["%1", "%2"]
        mock_run.assert_called_once_with(
            ["tmux", "list-panes", "-t", "my-project", "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )

    @patch("itmux.tmux.cwd.subprocess.run")
    def test_session_missing_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        assert list_session_pane_ids("missing") == []


class TestSetSessionWorkingDirectory:
    """set_session_working_directory() のテスト."""

    @patch("itmux.tmux.cwd.subprocess.run")
    def test_attach_session_with_cwd(self, mock_run, tmp_path):
        path = tmp_path.resolve()
        set_session_working_directory("my-project", path)

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == [
            "tmux",
            "attach-session",
            "-t",
            "my-project",
            "-c",
            str(path),
        ]
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert "TMUX" not in kwargs["env"]


class TestRespawnPaneCwd:
    """respawn_pane_cwd() のテスト."""

    @patch("itmux.tmux.cwd.subprocess.run")
    def test_respawn_pane_with_cwd(self, mock_run, tmp_path):
        path = tmp_path.resolve()
        respawn_pane_cwd("%1", path)

        mock_run.assert_called_once_with(
            ["tmux", "respawn-pane", "-k", "-t", "%1", "-c", str(path)],
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )


class TestApplySessionCwd:
    """apply_session_cwd() のテスト."""

    @patch("itmux.tmux.cwd.respawn_pane_cwd")
    @patch("itmux.tmux.cwd.set_session_working_directory")
    @patch("itmux.tmux.cwd.list_session_pane_ids")
    @patch("itmux.tmux.environment.tmux_has_session")
    def test_applies_to_all_panes(
        self,
        mock_has_session,
        mock_list_panes,
        mock_set_session,
        mock_respawn,
        tmp_path,
    ):
        mock_has_session.return_value = True
        mock_list_panes.return_value = ["%1", "%2"]
        path = tmp_path.resolve()

        result = apply_session_cwd("my-project", path)

        assert result is True
        mock_set_session.assert_called_once_with("my-project", path, env=None)
        assert mock_respawn.call_count == 2
        assert mock_respawn.call_args_list[0].args[0] == "%1"
        assert mock_respawn.call_args_list[1].args[0] == "%2"
        assert mock_respawn.call_args_list[0].args[1] == path

    @patch("itmux.tmux.environment.tmux_has_session")
    def test_invalid_path_raises(self, mock_has_session, tmp_path):
        mock_has_session.return_value = True
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")

        with pytest.raises(CwdError):
            apply_session_cwd("my-project", file_path.resolve())

    @patch("itmux.tmux.cwd.list_session_pane_ids")
    @patch("itmux.tmux.environment.tmux_has_session")
    def test_session_missing_skipped(self, mock_has_session, mock_list_panes, tmp_path):
        mock_has_session.return_value = False
        path = tmp_path.resolve()

        result = apply_session_cwd("my-project", path)

        assert result is False
        mock_list_panes.assert_not_called()
