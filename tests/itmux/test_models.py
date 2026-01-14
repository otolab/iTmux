"""tests/itmux/test_models.py"""

import pytest
from pydantic import ValidationError

from itmux.models import WindowSize, WindowConfig, ProjectConfig, Config


class TestWindowSize:
    """WindowSizeのテスト."""

    def test_valid_window_size(self):
        """正常なウィンドウサイズ."""
        ws = WindowSize(columns=200, lines=60)
        assert ws.columns == 200
        assert ws.lines == 60

    def test_zero_columns_raises_error(self):
        """列数0はエラー."""
        with pytest.raises(ValidationError):
            WindowSize(columns=0, lines=60)

    def test_negative_lines_raises_error(self):
        """行数負数はエラー."""
        with pytest.raises(ValidationError):
            WindowSize(columns=200, lines=-10)

    def test_json_serialization(self):
        """JSON変換."""
        ws = WindowSize(columns=150, lines=50)
        data = ws.model_dump()
        assert data == {"columns": 150, "lines": 50}

    def test_json_deserialization(self):
        """JSONからの復元."""
        data = {"columns": 120, "lines": 40}
        ws = WindowSize.model_validate(data)
        assert ws.columns == 120
        assert ws.lines == 40


class TestWindowConfig:
    """WindowConfigのテスト."""

    def test_valid_window(self):
        """正常なウィンドウ."""
        window = WindowConfig(name="my_editor")
        assert window.name == "my_editor"
        assert window.window_size is None

    def test_window_with_window_size(self):
        """ウィンドウサイズ付きウィンドウ."""
        window = WindowConfig(
            name="my_server", window_size=WindowSize(columns=120, lines=40)
        )
        assert window.window_size.columns == 120

    def test_invalid_window_name_with_colon(self):
        """ウィンドウ名にコロン含むとエラー."""
        with pytest.raises(ValidationError):
            WindowConfig(name="invalid:name")

    def test_invalid_window_name_with_dot(self):
        """ウィンドウ名にドット含むとエラー."""
        with pytest.raises(ValidationError):
            WindowConfig(name="invalid.name")

    def test_invalid_window_name_with_bracket(self):
        """ウィンドウ名にブラケット含むとエラー."""
        with pytest.raises(ValidationError):
            WindowConfig(name="invalid[name]")

    def test_empty_window_name_raises_error(self):
        """空のウィンドウ名はエラー."""
        with pytest.raises(ValidationError):
            WindowConfig(name="")

    def test_json_serialization(self):
        """JSON変換."""
        window = WindowConfig(
            name="test_window", window_size=WindowSize(columns=200, lines=60)
        )
        data = window.model_dump(exclude_none=True)
        assert data == {
            "name": "test_window",
            "window_size": {"columns": 200, "lines": 60},
        }

    def test_json_serialization_without_window_size(self):
        """ウィンドウサイズなしのJSON変換."""
        window = WindowConfig(name="test_window")
        data = window.model_dump(exclude_none=True)
        assert data == {"name": "test_window"}


class TestProjectConfig:
    """ProjectConfigのテスト."""

    def test_valid_project(self):
        """正常なプロジェクト."""
        project = ProjectConfig(
            name="my-project",
            tmux_windows=[
                WindowConfig(name="window1"),
                WindowConfig(name="window2"),
            ],
        )
        assert project.name == "my-project"
        assert len(project.tmux_windows) == 2

    def test_duplicate_window_names_raise_error(self):
        """ウィンドウ名重複はエラー."""
        with pytest.raises(ValidationError):
            ProjectConfig(
                name="my-project",
                tmux_windows=[
                    WindowConfig(name="same"),
                    WindowConfig(name="same"),
                ],
            )

    def test_empty_windows_list(self):
        """ウィンドウなしも許可."""
        project = ProjectConfig(name="empty-project")
        assert project.tmux_windows == []

    def test_invalid_project_name_with_colon(self):
        """プロジェクト名にコロン含むとエラー."""
        with pytest.raises(ValidationError):
            ProjectConfig(name="invalid:name")

    def test_invalid_project_name_with_dot(self):
        """プロジェクト名にドット含むとエラー."""
        with pytest.raises(ValidationError):
            ProjectConfig(name="invalid.name")

    def test_project_with_description(self):
        """説明付きプロジェクト."""
        project = ProjectConfig(
            name="my-project",
            description="This is my project",
            tmux_windows=[WindowConfig(name="window1")]
        )
        assert project.description == "This is my project"

    def test_project_without_description(self):
        """説明なしプロジェクト（省略可能）."""
        project = ProjectConfig(name="my-project")
        assert project.description is None

    def test_json_serialization(self):
        """JSON変換."""
        project = ProjectConfig(
            name="test-project",
            tmux_windows=[
                WindowConfig(
                    name="window1", window_size=WindowSize(columns=200, lines=60)
                )
            ],
        )
        data = project.model_dump(exclude_none=True)
        assert data == {
            "name": "test-project",
            "tmux_windows": [
                {"name": "window1", "window_size": {"columns": 200, "lines": 60}}
            ],
        }


class TestConfig:
    """Configのテスト."""

    def test_valid_config(self):
        """正常な全体設定."""
        config = Config(
            projects={
                "project1": ProjectConfig(
                    name="project1", tmux_windows=[WindowConfig(name="w1")]
                )
            }
        )
        assert "project1" in config.projects

    def test_project_key_mismatch_raises_error(self):
        """キーと名前の不一致はエラー."""
        with pytest.raises(ValidationError):
            Config(
                projects={"wrong-key": ProjectConfig(name="correct-name")}
            )

    def test_empty_config(self):
        """空の設定."""
        config = Config()
        assert config.projects == {}

    def test_json_serialization(self):
        """JSON変換."""
        config = Config(
            projects={
                "test-project": ProjectConfig(
                    name="test-project",
                    tmux_windows=[WindowConfig(name="w1")],
                )
            }
        )
        data = config.model_dump(exclude_none=True)
        assert "test-project" in data["projects"]
        assert data["projects"]["test-project"]["name"] == "test-project"

    def test_json_deserialization(self):
        """JSONからの復元（tmux_windows形式）."""
        data = {
            "projects": {
                "test-project": {
                    "name": "test-project",
                    "tmux_windows": [
                        {
                            "name": "window1",
                            "window_size": {"columns": 200, "lines": 60},
                        }
                    ],
                }
            }
        }
        config = Config.model_validate(data)
        assert "test-project" in config.projects
        assert len(config.projects["test-project"].tmux_windows) == 1
        assert (
            config.projects["test-project"].tmux_windows[0].window_size.columns
            == 200
        )
