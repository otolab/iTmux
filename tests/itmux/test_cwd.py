"""tests/itmux/test_cwd.py - tmux cwd 適用のテスト."""

import pytest
from pathlib import Path

from itmux.exceptions import CwdError
from itmux.tmux.cwd import cwd_creation_args, cwd_respawn_pane_command, validate_cwd_path


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


class TestCwdRespawnPaneCommand:
    """cwd_respawn_pane_command() のテスト."""

    def test_builds_respawn_pane_with_cwd(self, tmp_path):
        path = tmp_path.resolve()
        cmd = cwd_respawn_pane_command("42", path)
        assert cmd == f"respawn-pane -t @42 -c {path} -k"

    def test_strips_at_prefix_from_window_id(self, tmp_path):
        path = tmp_path.resolve()
        cmd = cwd_respawn_pane_command("@99", path)
        assert "@99" in cmd
        assert "@@99" not in cmd
