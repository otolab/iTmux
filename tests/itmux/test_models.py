"""tests/itmux/test_models.py"""

import pytest
from pydantic import ValidationError

from itmux.models import WindowSize, SessionConfig, ProjectConfig, Config


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


class TestSessionConfig:
    """SessionConfigのテスト."""

    def test_valid_session(self):
        """正常なセッション."""
        session = SessionConfig(name="my_editor")
        assert session.name == "my_editor"
        assert session.window_size is None

    def test_session_with_window_size(self):
        """ウィンドウサイズ付きセッション."""
        session = SessionConfig(
            name="my_server", window_size=WindowSize(columns=120, lines=40)
        )
        assert session.window_size.columns == 120

    def test_invalid_session_name_with_colon(self):
        """セッション名にコロン含むとエラー."""
        with pytest.raises(ValidationError):
            SessionConfig(name="invalid:name")

    def test_invalid_session_name_with_dot(self):
        """セッション名にドット含むとエラー."""
        with pytest.raises(ValidationError):
            SessionConfig(name="invalid.name")

    def test_invalid_session_name_with_bracket(self):
        """セッション名にブラケット含むとエラー."""
        with pytest.raises(ValidationError):
            SessionConfig(name="invalid[name]")

    def test_empty_session_name_raises_error(self):
        """空のセッション名はエラー."""
        with pytest.raises(ValidationError):
            SessionConfig(name="")

    def test_json_serialization(self):
        """JSON変換."""
        session = SessionConfig(
            name="test_session", window_size=WindowSize(columns=200, lines=60)
        )
        data = session.model_dump(exclude_none=True)
        assert data == {
            "name": "test_session",
            "window_size": {"columns": 200, "lines": 60},
        }

    def test_json_serialization_without_window_size(self):
        """ウィンドウサイズなしのJSON変換."""
        session = SessionConfig(name="test_session")
        data = session.model_dump(exclude_none=True)
        assert data == {"name": "test_session"}


class TestProjectConfig:
    """ProjectConfigのテスト."""

    def test_valid_project(self):
        """正常なプロジェクト."""
        project = ProjectConfig(
            name="my-project",
            tmux_sessions=[
                SessionConfig(name="session1"),
                SessionConfig(name="session2"),
            ],
        )
        assert project.name == "my-project"
        assert len(project.tmux_sessions) == 2

    def test_duplicate_session_names_raise_error(self):
        """セッション名重複はエラー."""
        with pytest.raises(ValidationError):
            ProjectConfig(
                name="my-project",
                tmux_sessions=[
                    SessionConfig(name="same"),
                    SessionConfig(name="same"),
                ],
            )

    def test_empty_sessions_list(self):
        """セッションなしも許可."""
        project = ProjectConfig(name="empty-project")
        assert project.tmux_sessions == []

    def test_json_serialization(self):
        """JSON変換."""
        project = ProjectConfig(
            name="test-project",
            tmux_sessions=[
                SessionConfig(
                    name="session1", window_size=WindowSize(columns=200, lines=60)
                )
            ],
        )
        data = project.model_dump(exclude_none=True)
        assert data == {
            "name": "test-project",
            "tmux_sessions": [
                {"name": "session1", "window_size": {"columns": 200, "lines": 60}}
            ],
        }


class TestConfig:
    """Configのテスト."""

    def test_valid_config(self):
        """正常な全体設定."""
        config = Config(
            projects={
                "project1": ProjectConfig(
                    name="project1", tmux_sessions=[SessionConfig(name="s1")]
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
                    tmux_sessions=[SessionConfig(name="s1")],
                )
            }
        )
        data = config.model_dump(exclude_none=True)
        assert "test-project" in data["projects"]
        assert data["projects"]["test-project"]["name"] == "test-project"

    def test_json_deserialization(self):
        """JSONからの復元."""
        data = {
            "projects": {
                "test-project": {
                    "name": "test-project",
                    "tmux_sessions": [
                        {
                            "name": "session1",
                            "window_size": {"columns": 200, "lines": 60},
                        }
                    ],
                }
            }
        }
        config = Config.model_validate(data)
        assert "test-project" in config.projects
        assert len(config.projects["test-project"].tmux_sessions) == 1
        assert (
            config.projects["test-project"].tmux_sessions[0].window_size.columns
            == 200
        )
