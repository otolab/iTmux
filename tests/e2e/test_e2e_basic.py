"""tests/e2e/test_e2e_basic.py - E2E基本フロー."""

import pytest
import time
import subprocess


@pytest.mark.e2e
class TestE2EBasicFlow:
    """E2E基本フロー."""

    def test_full_workflow(self, cli_runner, check_environment):
        """完全なワークフロー: open → list → add → close → re-open."""

        # 1. プロジェクトを開く
        result = cli_runner("open", "e2e-test-project")
        assert result.exit_code == 0
        assert "✓ Opened project: e2e-test-project" in result.output

        # tmuxセッションが作成されたことを確認
        time.sleep(2)  # ウィンドウ作成を待つ
        # 1プロジェクト = 1セッション
        tmux_result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True
        )
        assert "e2e-test-project" in tmux_result.stdout

        # ウィンドウを確認
        tmux_windows = subprocess.run(
            ["tmux", "list-windows", "-t", "e2e-test-project", "-F", "#{window_name}"],
            capture_output=True,
            text=True
        )
        assert "e2e_editor" in tmux_windows.stdout
        assert "e2e_server" in tmux_windows.stdout

        # 2. プロジェクト一覧を確認
        result = cli_runner("list")
        assert result.exit_code == 0
        assert "e2e-test-project" in result.output
        assert "e2e_editor" in result.output
        assert "e2e_server" in result.output

        # 3. ウィンドウを追加
        result = cli_runner("add", "e2e-test-project", "e2e_logs")
        assert result.exit_code == 0
        assert "✓ Added window" in result.output

        time.sleep(2)
        tmux_windows = subprocess.run(
            ["tmux", "list-windows", "-t", "e2e-test-project", "-F", "#{window_name}"],
            capture_output=True,
            text=True
        )
        assert "e2e_logs" in tmux_windows.stdout

        # 4. プロジェクトを閉じる
        result = cli_runner("close", "e2e-test-project")
        assert result.exit_code == 0, f"Close failed: {result.output}"
        assert "✓ Closed project" in result.output

        # セッションはバックグラウンドで残っている
        time.sleep(2)
        tmux_result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True
        )
        # セッションはまだ存在する（デタッチされただけ）
        assert "e2e-test-project" in tmux_result.stdout

        # 5. 再度開く
        result = cli_runner("open", "e2e-test-project")
        assert result.exit_code == 0, f"Reopen failed: {result.output}"
        assert "✓ Opened project" in result.output

        # 追加したウィンドウも復元される
        time.sleep(2)
        result = cli_runner("list")
        assert "e2e_logs" in result.output

        # クリーンアップ
        result = cli_runner("close", "e2e-test-project")
        assert result.exit_code == 0

    def test_open_new_project(self, cli_runner, check_environment):
        """新規プロジェクトを開く（ウィンドウが存在しない場合）."""

        result = cli_runner("open", "e2e-test-project")
        assert result.exit_code == 0

        # 新規ウィンドウが作成される
        time.sleep(2)
        tmux_result = subprocess.run(
            ["tmux", "has-session", "-t", "e2e_editor"],
            capture_output=True
        )
        assert tmux_result.returncode == 0

        # クリーンアップ
        cli_runner("close", "e2e-test-project")
