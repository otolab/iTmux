"""iTmux custom exceptions."""


class ConfigError(Exception):
    """設定ファイル関連エラー."""

    pass


class ProjectNotFoundError(ConfigError):
    """プロジェクトが見つからないエラー."""

    pass


class SessionNotFoundError(ConfigError):
    """セッションが見つからないエラー."""

    pass


class ITerm2Error(Exception):
    """iTerm2 API連携エラー."""

    pass


class WindowCreationTimeoutError(ITerm2Error):
    """ウィンドウ生成タイムアウトエラー."""

    pass
