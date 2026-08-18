"""iTmux custom exceptions."""

from enum import Enum


class ConfigError(Exception):
    """設定ファイル関連エラー."""

    pass


class CwdError(Exception):
    """作業ディレクトリ（cwd）関連エラー."""

    pass


class ProjectNotFoundError(ConfigError):
    """プロジェクトが見つからないエラー."""

    pass


class ProjectNotOpenReason(Enum):
    """プロジェクトが iTerm2 で開いていない理由."""

    NOT_OPEN = "not_open"
    TMUX_DETACHED = "tmux_detached"
    NOT_FOUND = "not_found"


class ProjectNotOpenError(Exception):
    """プロジェクトが iTerm2 で開いていないエラー."""

    def __init__(self, project_name: str, reason: ProjectNotOpenReason):
        self.project_name = project_name
        self.reason = reason
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if self.reason is ProjectNotOpenReason.TMUX_DETACHED:
            situation = (
                f"プロジェクト '{self.project_name}' は tmux 上に存在しますが、"
                f"iTerm2 で開いていません。"
            )
        elif self.reason is ProjectNotOpenReason.NOT_FOUND:
            situation = f"プロジェクト '{self.project_name}' は設定に存在しません。"
        else:
            situation = f"プロジェクト '{self.project_name}' は iTerm2 で開いていません。"

        return (
            f"{situation}\n"
            f"  先に次を実行してください: itmux open {self.project_name}"
        )


class SessionNotFoundError(ConfigError):
    """セッションが見つからないエラー."""

    pass


class ITerm2Error(Exception):
    """iTerm2 API連携エラー."""

    pass


class WindowCreationTimeoutError(ITerm2Error):
    """ウィンドウ生成タイムアウトエラー."""

    pass
