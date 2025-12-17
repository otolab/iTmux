"""tests/itmux/test_config.py - ConfigManagerのテスト."""

import json
import pytest
from pathlib import Path

from itmux.config import ConfigManager, load_config, get_project, list_projects
from itmux.models import Config, ProjectConfig, SessionConfig, WindowSize
from itmux.exceptions import ConfigError, ProjectNotFoundError


@pytest.fixture
def temp_config_file(tmp_path):
    """一時設定ファイル."""
    return tmp_path / "config.json"


@pytest.fixture
def sample_config_data():
    """サンプル設定データ."""
    return {
        "projects": {
            "test-project": {
                "name": "test-project",
                "tmux_sessions": [
                    {"name": "session1", "window_size": {"columns": 200, "lines": 60}},
                    {"name": "session2"},
                ],
            }
        }
    }


class TestConfigManager:
    """ConfigManagerのテスト."""

    def test_load_nonexistent_file_returns_empty_config(self, temp_config_file):
        """存在しないファイルは空の設定を返す."""
        manager = ConfigManager(temp_config_file)
        config = manager.load()
        assert config.projects == {}

    def test_load_valid_config(self, temp_config_file, sample_config_data):
        """正常な設定ファイル読み込み."""
        # ファイル作成
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        manager = ConfigManager(temp_config_file)
        config = manager.load()

        assert "test-project" in config.projects
        assert len(config.projects["test-project"].tmux_sessions) == 2

    def test_load_invalid_json_raises_error(self, temp_config_file):
        """不正なJSON形式はエラー."""
        with open(temp_config_file, "w") as f:
            f.write("{invalid json")

        manager = ConfigManager(temp_config_file)
        with pytest.raises(ConfigError, match="Invalid JSON format"):
            manager.load()

    def test_save_creates_directory(self, tmp_path):
        """保存時にディレクトリを作成."""
        config_path = tmp_path / "nested" / "dir" / "config.json"
        manager = ConfigManager(config_path)

        config = Config()
        manager.save(config)

        assert config_path.exists()
        assert config_path.parent.exists()

    def test_save_and_load_roundtrip(self, temp_config_file):
        """保存→読み込みの往復."""
        manager = ConfigManager(temp_config_file)

        # 設定作成
        original = Config(
            projects={
                "my-project": ProjectConfig(
                    name="my-project",
                    tmux_sessions=[
                        SessionConfig(
                            name="s1", window_size=WindowSize(columns=100, lines=50)
                        )
                    ],
                )
            }
        )

        # 保存
        manager.save(original)

        # 読み込み
        loaded = manager.load()

        assert loaded.projects == original.projects

    def test_get_project_existing(self, temp_config_file, sample_config_data):
        """存在するプロジェクト取得."""
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        manager = ConfigManager(temp_config_file)
        project = manager.get_project("test-project")

        assert project.name == "test-project"
        assert len(project.tmux_sessions) == 2

    def test_get_project_nonexistent_raises_error(self, temp_config_file):
        """存在しないプロジェクトはエラー."""
        manager = ConfigManager(temp_config_file)
        manager.load()  # 空の設定

        with pytest.raises(ProjectNotFoundError):
            manager.get_project("nonexistent")

    def test_list_projects(self, temp_config_file, sample_config_data):
        """プロジェクト一覧取得."""
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        manager = ConfigManager(temp_config_file)
        projects = manager.list_projects()

        assert projects == ["test-project"]

    def test_list_projects_empty(self, temp_config_file):
        """空のプロジェクト一覧."""
        manager = ConfigManager(temp_config_file)
        projects = manager.list_projects()

        assert projects == []

    def test_update_project_sessions(self, temp_config_file, sample_config_data):
        """セッションリスト更新."""
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        manager = ConfigManager(temp_config_file)
        manager.load()

        # 新しいセッションリスト
        new_sessions = [
            SessionConfig(name="updated1"),
            SessionConfig(name="updated2"),
            SessionConfig(name="updated3"),
        ]

        manager.update_project("test-project", new_sessions)

        # 再読み込みして確認
        manager2 = ConfigManager(temp_config_file)
        project = manager2.get_project("test-project")

        assert len(project.tmux_sessions) == 3
        assert project.tmux_sessions[0].name == "updated1"

    def test_update_project_nonexistent_raises_error(self, temp_config_file):
        """存在しないプロジェクトの更新はエラー."""
        manager = ConfigManager(temp_config_file)
        manager.load()

        with pytest.raises(ProjectNotFoundError):
            manager.update_project("nonexistent", [])

    def test_add_session(self, temp_config_file, sample_config_data):
        """セッション追加."""
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        manager = ConfigManager(temp_config_file)
        manager.load()

        new_session = SessionConfig(name="session3")
        manager.add_session("test-project", new_session)

        # 確認
        project = manager.get_project("test-project")
        assert len(project.tmux_sessions) == 3

    def test_add_duplicate_session_raises_error(
        self, temp_config_file, sample_config_data
    ):
        """重複セッション追加はエラー."""
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        manager = ConfigManager(temp_config_file)
        manager.load()

        duplicate_session = SessionConfig(name="session1")

        with pytest.raises(ConfigError, match="already exists"):
            manager.add_session("test-project", duplicate_session)

    def test_add_session_to_nonexistent_project_raises_error(self, temp_config_file):
        """存在しないプロジェクトへのセッション追加はエラー."""
        manager = ConfigManager(temp_config_file)
        manager.load()

        with pytest.raises(ProjectNotFoundError):
            manager.add_session("nonexistent", SessionConfig(name="session"))

    def test_save_without_load_raises_error(self, temp_config_file):
        """load前のsave（引数なし）はエラー."""
        manager = ConfigManager(temp_config_file)

        with pytest.raises(ConfigError, match="No config to save"):
            manager.save()

    def test_save_with_explicit_config(self, temp_config_file):
        """明示的なconfig指定での保存."""
        manager = ConfigManager(temp_config_file)

        config = Config(
            projects={
                "my-project": ProjectConfig(
                    name="my-project", tmux_sessions=[SessionConfig(name="s1")]
                )
            }
        )

        manager.save(config)

        # 確認
        with open(temp_config_file) as f:
            data = json.load(f)

        assert "my-project" in data["projects"]


class TestFunctionAPI:
    """関数APIのテスト."""

    def test_load_config(self, temp_config_file, sample_config_data):
        """load_config関数."""
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        config = load_config(temp_config_file)

        assert "test-project" in config.projects

    def test_get_project(self, temp_config_file, sample_config_data):
        """get_project関数."""
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        project = get_project("test-project", temp_config_file)

        assert project.name == "test-project"

    def test_list_projects(self, temp_config_file, sample_config_data):
        """list_projects関数."""
        with open(temp_config_file, "w") as f:
            json.dump(sample_config_data, f)

        projects = list_projects(temp_config_file)

        assert projects == ["test-project"]
