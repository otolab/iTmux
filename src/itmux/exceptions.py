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
