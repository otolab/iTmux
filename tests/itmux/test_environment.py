"""tests/itmux/test_environment.py - tmux環境変数適用のテスト."""

import os
import pytest
from unittest.mock import MagicMock, patch

from itmux.tmux.environment import (
    BOOTSTRAP_WINDOW,
    apply_session_environments,
    prepare_session_environments,
    tmux_has_session,
)


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


class TestPrepareSessionEnvironments:
    """prepare_session_environments()のテスト."""

    @patch("itmux.tmux.environment.apply_session_environments")
    @patch("itmux.tmux.environment.tmux_has_session")
    @patch("itmux.tmux.environment.subprocess.run")
    def test_new_session_applies_env_before_first_window(
        self, mock_run, mock_has_session, mock_apply
    ):
        """新規セッションでは set-environment 後に初回ウィンドウを作成."""
        mock_has_session.return_value = False

        created = prepare_session_environments(
            "my-project",
            {"MY_KEY": "my_value"},
            "editor",
        )

        assert created is True
        mock_apply.assert_called_once()
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert calls[0][:4] == ["tmux", "new-session", "-d", "-s"]
        assert calls[0][6] == BOOTSTRAP_WINDOW
        assert calls[1][:3] == ["tmux", "new-window", "-t"]
        assert calls[1][4:6] == ["-n", "editor"]
        assert calls[2][:3] == ["tmux", "kill-window", "-t"]

    @patch("itmux.tmux.environment.apply_session_environments")
    @patch("itmux.tmux.environment.tmux_has_session")
    @patch("itmux.tmux.environment.subprocess.run")
    def test_existing_session_only_applies_env(
        self, mock_run, mock_has_session, mock_apply
    ):
        """既存セッションでは環境変数の再適用のみ."""
        mock_has_session.return_value = True

        created = prepare_session_environments(
            "my-project",
            {"MY_KEY": "my_value"},
            "editor",
        )

        assert created is False
        mock_apply.assert_called_once_with(
            "my-project", {"MY_KEY": "my_value"}, env=os.environ.copy()
        )
        mock_run.assert_not_called()

    @patch("itmux.tmux.environment.tmux_has_session")
    @patch("itmux.tmux.environment.subprocess.run")
    def test_new_session_without_environments(
        self, mock_run, mock_has_session
    ):
        """environments なしの新規セッションは通常作成."""
        mock_has_session.return_value = False

        created = prepare_session_environments("my-project", {}, "editor")

        assert created is True
        mock_run.assert_called_once_with(
            ["tmux", "new-session", "-d", "-s", "my-project", "-n", "editor"],
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )

    @patch("itmux.tmux.environment.tmux_has_session")
    @patch("itmux.tmux.environment.subprocess.run")
    def test_new_session_with_cwd(
        self, mock_run, mock_has_session, tmp_path
    ):
        """cwd 指定の新規セッションは -c 付きで作成."""
        mock_has_session.return_value = False
        cwd = tmp_path.resolve()

        created = prepare_session_environments("my-project", {}, "editor", cwd=cwd)

        assert created is True
        mock_run.assert_called_once_with(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                "my-project",
                "-n",
                "editor",
                "-c",
                str(cwd),
            ],
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )


class TestPrepareSessionEnvironmentsIntegration:
    """prepare_session_environments() の tmux 実機検証."""

    @pytest.fixture(autouse=True)
    def require_tmux(self):
        import shutil
        if shutil.which("tmux") is None:
            pytest.skip("tmux not available")

    def test_session_environment_is_set_before_shell(self):
        """set-environment が初回ウィンドウ作成前にセッションへ設定される."""
        import subprocess

        session = "itmux-test-env-integration"
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            capture_output=True,
            check=False,
        )

        prepare_session_environments(
            session,
            {"MY_KEY": "my_value"},
            "editor",
        )

        result = subprocess.run(
            ["tmux", "show-environment", "-t", session, "MY_KEY"],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            capture_output=True,
            check=False,
        )

        assert "my_value" in result.stdout

