"""iTmux configuration management."""

import json
from pathlib import Path
from typing import Optional

from filelock import FileLock

from .models import Config, ProjectConfig, WindowConfig
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
        self.lock_path = self.config_path.parent / f".{self.config_path.name}.lock"
        self._config: Optional[Config] = None

    def load(self) -> Config:
        """設定ファイルを読み込む（ファイルロック付き）.

        Returns:
            Config: 読み込んだ設定

        Raises:
            ConfigError: ファイル読み込みエラー、JSON形式エラー
        """
        # ロックファイルのディレクトリを作成
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        with FileLock(self.lock_path, timeout=10):
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
        """設定ファイルを保存する（ファイルロック付き）.

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
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        with FileLock(self.lock_path, timeout=10):
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
        self, project_name: str, windows: list[WindowConfig]
    ) -> None:
        """プロジェクトのウィンドウリストを更新（自動同期用）.

        close時に現在のウィンドウリストで設定を上書きします。

        Args:
            project_name: プロジェクト名
            windows: 現在のウィンドウリスト

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        if self._config is None:
            self.load()

        if project_name not in self._config.projects:
            raise ProjectNotFoundError(f"Project '{project_name}' not found")

        # ウィンドウリストを更新
        self._config.projects[project_name].tmux_windows = windows

        # 自動保存
        self.save()

    def add_window(self, project_name: str, window: WindowConfig) -> None:
        """プロジェクトに新しいウィンドウを追加.

        Args:
            project_name: プロジェクト名
            window: 追加するウィンドウ

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
            ConfigError: ウィンドウ名が重複
        """
        if self._config is None:
            self.load()

        if project_name not in self._config.projects:
            raise ProjectNotFoundError(f"Project '{project_name}' not found")

        project = self._config.projects[project_name]

        # 重複チェック
        if any(w.name == window.name for w in project.tmux_windows):
            raise ConfigError(
                f"Window '{window.name}' already exists in project '{project_name}'"
            )

        # ウィンドウ追加
        project.tmux_windows.append(window)

        # 自動保存
        self.save()

    def create_project(
        self, project_name: str, windows: Optional[list[WindowConfig]] = None
    ) -> None:
        """プロジェクトを新規作成.

        Args:
            project_name: プロジェクト名
            windows: ウィンドウリスト（省略時は空リスト）

        Raises:
            ConfigError: プロジェクトが既に存在する
        """
        if self._config is None:
            self.load()

        if project_name in self._config.projects:
            raise ConfigError(f"Project '{project_name}' already exists")

        # プロジェクト作成
        self._config.projects[project_name] = ProjectConfig(
            name=project_name,
            tmux_windows=windows or []
        )

        # 自動保存
        self.save()

    def delete_project(self, project_name: str) -> None:
        """プロジェクトを削除.

        Args:
            project_name: プロジェクト名

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        if self._config is None:
            self.load()

        if project_name not in self._config.projects:
            raise ProjectNotFoundError(f"Project '{project_name}' not found")

        # プロジェクト削除
        del self._config.projects[project_name]

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
