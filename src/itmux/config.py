"""iTmux configuration management."""

import json
from pathlib import Path
from typing import Optional

from .models import Config, ProjectConfig, SessionConfig
from .exceptions import ConfigError, ProjectNotFoundError


DEFAULT_CONFIG_PATH = Path.home() / ".itmux" / "config.json"


class ConfigManager:
    """設定ファイル管理クラス."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Args:
            config_path: 設定ファイルパス（省略時はデフォルト）
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: Optional[Config] = None

    def load(self) -> Config:
        """設定ファイルを読み込む.

        Returns:
            Config: 読み込んだ設定

        Raises:
            ConfigError: ファイル読み込みエラー、JSON形式エラー
        """
        if not self.config_path.exists():
            # ファイルが存在しない場合は空の設定を返す
            self._config = Config(projects={})
            return self._config

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._config = Config.model_validate(data)
                return self._config
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON format: {e}") from e
        except Exception as e:
            raise ConfigError(f"Failed to load config: {e}") from e

    def save(self, config: Optional[Config] = None) -> None:
        """設定ファイルを保存する.

        Args:
            config: 保存する設定（省略時は現在の設定）

        Raises:
            ConfigError: ファイル書き込みエラー
        """
        if config is None:
            if self._config is None:
                raise ConfigError("No config to save")
            config = self._config

        # ディレクトリ作成
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                data = config.model_dump(exclude_none=True)
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")  # 末尾改行
        except Exception as e:
            raise ConfigError(f"Failed to save config: {e}") from e

    def get_project(self, project_name: str) -> ProjectConfig:
        """プロジェクト設定を取得.

        Args:
            project_name: プロジェクト名

        Returns:
            ProjectConfig: プロジェクト設定

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        if self._config is None:
            self.load()

        if project_name not in self._config.projects:
            raise ProjectNotFoundError(f"Project '{project_name}' not found")

        return self._config.projects[project_name]

    def list_projects(self) -> list[str]:
        """プロジェクト名一覧を取得.

        Returns:
            list[str]: プロジェクト名のリスト
        """
        if self._config is None:
            self.load()

        return list(self._config.projects.keys())

    def update_project(
        self, project_name: str, sessions: list[SessionConfig]
    ) -> None:
        """プロジェクトのセッションリストを更新（自動同期用）.

        close時に現在のセッションリストで設定を上書きします。

        Args:
            project_name: プロジェクト名
            sessions: 現在のセッションリスト

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        if self._config is None:
            self.load()

        if project_name not in self._config.projects:
            raise ProjectNotFoundError(f"Project '{project_name}' not found")

        # セッションリストを更新
        self._config.projects[project_name].tmux_sessions = sessions

        # 自動保存
        self.save()

    def add_session(self, project_name: str, session: SessionConfig) -> None:
        """プロジェクトに新しいセッションを追加.

        Args:
            project_name: プロジェクト名
            session: 追加するセッション

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
            ConfigError: セッション名が重複
        """
        if self._config is None:
            self.load()

        if project_name not in self._config.projects:
            raise ProjectNotFoundError(f"Project '{project_name}' not found")

        project = self._config.projects[project_name]

        # 重複チェック
        if any(s.name == session.name for s in project.tmux_sessions):
            raise ConfigError(
                f"Session '{session.name}' already exists in project '{project_name}'"
            )

        # セッション追加
        project.tmux_sessions.append(session)

        # 自動保存
        self.save()


# 便利関数（後方互換性・簡易API用）


def load_config(config_path: Optional[Path] = None) -> Config:
    """設定ファイルを読み込む（関数API）."""
    manager = ConfigManager(config_path)
    return manager.load()


def get_project(
    project_name: str, config_path: Optional[Path] = None
) -> ProjectConfig:
    """プロジェクト設定を取得（関数API）."""
    manager = ConfigManager(config_path)
    return manager.get_project(project_name)


def list_projects(config_path: Optional[Path] = None) -> list[str]:
    """プロジェクト名一覧を取得（関数API）."""
    manager = ConfigManager(config_path)
    return manager.list_projects()
