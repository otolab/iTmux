"""tests/e2e/conftest.py - E2Eテスト用のフィクスチャ."""

import os
import pytest
import tempfile
import shutil
from pathlib import Path
import subprocess

# CI環境ではE2Eテストをスキップ
def pytest_configure(config):
    """pytestの設定."""
    config.addinivalue_line(
        "markers", "e2e: mark test as e2e test (deselect with '-m \"not e2e\"')"
    )


@pytest.fixture(scope="session")
def check_environment():
    """E2Eテスト実行環境をチェック."""
    # CI環境チェック
    if os.environ.get("CI"):
        pytest.skip("E2E tests are not run in CI environment")

    # tmuxがインストールされているか確認
    result = subprocess.run(["which", "tmux"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("tmux is not installed")

    # iTerm2 Python APIが有効かチェック
    try:
        import iterm2
        import asyncio

        async def check_api():
            try:
                connection = await iterm2.Connection.async_create()
                # 接続できればOK（Connectionオブジェクトにcloseメソッドはない）
                return True
            except Exception as e:
                return False

        if not asyncio.run(check_api()):
            pytest.skip(
                "iTerm2 Python API is not enabled or not accessible. "
                "Enable it in iTerm2 > Settings > General > Magic > Enable Python API"
            )
    except ImportError:
        pytest.skip("iterm2 module is not available")


@pytest.fixture
def temp_config_dir(tmp_path):
    """一時的な設定ディレクトリを作成."""
    config_dir = tmp_path / ".itmux"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_config_file(temp_config_dir):
    """一時的な設定ファイルを作成."""
    config_file = temp_config_dir / "config.json"

    # 初期設定を書き込み
    import json
    initial_config = {
        "projects": {
            "e2e-test-project": {
                "name": "e2e-test-project",
                "tmux_windows": [
                    {"name": "e2e_session1"},
                    {"name": "e2e_session2"}
                ]
            }
        }
    }
    with open(config_file, "w") as f:
        json.dump(initial_config, f, indent=2)

    return config_file


@pytest.fixture
def cleanup_tmux_sessions():
    """テスト後にtmuxセッションをクリーンアップ."""
    # テスト前の状態を記録
    yield

    # テスト後: e2e-で始まるセッションを削除
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        sessions = result.stdout.strip().split("\n")
        for session in sessions:
            if session.startswith("e2e_"):
                subprocess.run(
                    ["tmux", "kill-session", "-t", session],
                    capture_output=True
                )


@pytest.fixture
def cli_runner(temp_config_file, cleanup_tmux_sessions, monkeypatch):
    """CLIコマンド実行用のヘルパー."""
    import subprocess
    from pathlib import Path

    # 環境変数でconfig pathを上書き
    monkeypatch.setenv("ITMUX_CONFIG_PATH", str(temp_config_file))

    # cli.pyでインポートされたDEFAULT_CONFIG_PATHもパッチ
    import itmux.cli
    monkeypatch.setattr(itmux.cli, "DEFAULT_CONFIG_PATH", temp_config_file)

    def run_command(*args, **kwargs):
        """コマンドを実行して結果を返す."""
        # 実際のプロセスでCLIを実行
        cmd = ["uv", "run", "itmux"] + list(args)
        env = os.environ.copy()
        env["ITMUX_CONFIG_PATH"] = str(temp_config_file)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env
        )

        # Click.CliRunnerのResultと互換性のあるオブジェクトを返す
        class Result:
            def __init__(self, returncode, stdout, stderr):
                self.exit_code = returncode
                self.output = stdout + stderr
                self.exception = None if returncode == 0 else returncode

        return Result(result.returncode, result.stdout, result.stderr)

    return run_command
