"""tests/e2e/test_e2e_edge.py - E2Eエッジケース."""

import pytest


@pytest.mark.e2e
class TestE2EEdgeCases:
    """E2Eエッジケース."""

    def test_open_nonexistent_project(self, cli_runner, check_environment):
        """存在しないプロジェクトを開こうとする."""

        result = cli_runner("open", "nonexistent-project")
        assert result.exit_code == 1
        assert "✗ Error:" in result.output
        assert "not found" in result.output.lower()

    def test_close_with_environment_variable(
        self, cli_runner, check_environment, monkeypatch
    ):
        """環境変数を使ってプロジェクトを閉じる."""

        # プロジェクトを開く
        result = cli_runner("open", "e2e-test-project")
        assert result.exit_code == 0

        # 環境変数を設定
        monkeypatch.setenv("ITMUX_PROJECT", "e2e-test-project")

        # プロジェクト名を省略してclose
        result = cli_runner("close")
        assert result.exit_code == 0
        assert "✓ Closed project: current" in result.output

    def test_add_with_auto_generated_name(self, cli_runner, check_environment):
        """セッション名を自動生成."""

        # プロジェクトを開く
        result = cli_runner("open", "e2e-test-project")
        assert result.exit_code == 0

        # セッション名を省略してadd
        result = cli_runner("add", "e2e-test-project")
        assert result.exit_code == 0
        assert "✓ Added session" in result.output

        # 自動生成されたセッションが存在する
        result = cli_runner("list")
        assert "e2e-test-project-1" in result.output

        # クリーンアップ
        cli_runner("close", "e2e-test-project")
