"""tests/itmux/test_environment.py - tmux環境変数適用のテスト."""

import os
from unittest.mock import MagicMock, patch

from itmux.tmux.environment import apply_session_environments, tmux_has_session


class TestTmuxHasSession:
    """tmux_has_session()のテスト."""

    @patch("itmux.tmux.environment.subprocess.run")
    def test_session_exists(self, mock_run):
        """セッションが存在する場合True."""
        mock_run.return_value = MagicMock(returncode=0)

        assert tmux_has_session("my-project") is True
        mock_run.assert_called_once_with(
            ["tmux", "has-session", "-t", "my-project"],
            capture_output=True,
            env=os.environ.copy(),
        )

    @patch("itmux.tmux.environment.subprocess.run")
    def test_session_not_exists(self, mock_run):
        """セッションが存在しない場合False."""
        mock_run.return_value = MagicMock(returncode=1)

        assert tmux_has_session("missing") is False


class TestApplySessionEnvironments:
    """apply_session_environments()のテスト."""

    @patch("itmux.tmux.environment.tmux_has_session")
    @patch("itmux.tmux.environment.subprocess.run")
    def test_apply_all_variables(self, mock_run, mock_has_session):
        """各環境変数に対して set-environment を実行."""
        mock_has_session.return_value = True

        result = apply_session_environments(
            "my-project",
            {"NODE_ENV": "development", "FOO": "bar"},
        )

        assert result is True
        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["tmux", "set-environment", "-t", "my-project", "NODE_ENV", "development"],
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )
        mock_run.assert_any_call(
            ["tmux", "set-environment", "-t", "my-project", "FOO", "bar"],
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )

    @patch("itmux.tmux.environment.tmux_has_session")
    @patch("itmux.tmux.environment.subprocess.run")
    def test_empty_environments_skipped(self, mock_run, mock_has_session):
        """空の environments は何もしない."""
        result = apply_session_environments("my-project", {})

        assert result is False
        mock_has_session.assert_not_called()
        mock_run.assert_not_called()

    @patch("itmux.tmux.environment.tmux_has_session")
    @patch("itmux.tmux.environment.subprocess.run")
    def test_session_not_found_skipped(self, mock_run, mock_has_session):
        """セッションが存在しない場合はスキップ."""
        mock_has_session.return_value = False

        result = apply_session_environments("my-project", {"FOO": "bar"})

        assert result is False
        mock_run.assert_not_called()
