"""tests/e2e/test_e2e_edge.py - E2Eエッジケース."""

import pytest


@pytest.mark.e2e
class TestE2EEdgeCases:
    """E2Eエッジケース."""

    def test_open_nonexistent_project(self, cli_runner, check_environment):
        """存在しないプロジェクトを開く（自動作成される）."""

        result = cli_runner("open", "nonexistent-project")
        # 存在しないプロジェクトは自動作成される
        assert result.exit_code == 0
        assert "✓ Opened project: nonexistent-project" in result.output

        # プロジェクトが作成されたことを確認
        result = cli_runner("list")
        assert result.exit_code == 0
        assert "nonexistent-project" in result.output

        # クリーンアップ
        cli_runner("close", "nonexistent-project")

    def test_add_with_auto_generated_name(self, cli_runner, check_environment):
        """ウィンドウ名を自動生成."""
        import time

        # プロジェクトを開く
        result = cli_runner("open", "e2e-test-project")
        assert result.exit_code == 0

        # ウィンドウ名を省略してadd
        result = cli_runner("add", "e2e-test-project")
        assert result.exit_code == 0
        assert "✓ Added window" in result.output

        # hookによるsync処理の完了を待つ
        time.sleep(5)

        # 自動生成されたウィンドウが存在する
        result = cli_runner("list")
        assert result.exit_code == 0
        # 自動生成されたウィンドウ名を確認（e2e-test-project-1など）
        assert "e2e-test-project-1" in result.output or "window-1" in result.output

        # クリーンアップ
        cli_runner("close", "e2e-test-project")
