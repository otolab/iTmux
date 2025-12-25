"""tmuxセッションの管理."""

import iterm2
from ..models import WindowConfig
from ..exceptions import ITerm2Error


class SessionManager:
    """tmuxセッションの管理を担当するクラス."""

    def __init__(self, connection: iterm2.Connection):
        """Initialize SessionManager.

        Args:
            connection: iTerm2 Connection
        """
        self.connection = connection

    async def get_tmux_connection(self, project_name: str) -> iterm2.TmuxConnection:
        """プロジェクトのTmuxConnectionを取得.

        tmuxコマンドでsession nameを確認しながらTmuxConnectionを都度検索します（キャッシュしません）。

        Args:
            project_name: プロジェクト名

        Returns:
            iterm2.TmuxConnection: Tmux接続

        Raises:
            ITerm2Error: TmuxConnection取得に失敗
        """
        # 全てのTmuxConnectionを取得
        tmux_conns = await iterm2.async_get_tmux_connections(self.connection)

        # 各connectionのsession nameを確認
        for conn in tmux_conns:
            try:
                # tmuxコマンドでsession nameを取得
                result = await conn.async_send_command("display-message -p '#{session_name}'")
                session_name = result.strip()

                if session_name == project_name:
                    return conn
            except Exception:
                # このconnectionでコマンド実行に失敗した場合は次へ
                continue

        raise ITerm2Error(f"TmuxConnection not found for project: {project_name}")

    async def get_tmux_windows(self, project_name: str) -> list[WindowConfig]:
        """プロジェクトのtmuxセッションから実際のウィンドウリストを取得.

        iTerm2 Windowが閉じられていても、tmuxセッションに存在するウィンドウを全て取得します。

        Args:
            project_name: プロジェクト名

        Returns:
            list[WindowConfig]: ウィンドウ設定のリスト

        Raises:
            ITerm2Error: tmuxコマンド実行に失敗
        """
        try:
            tmux_conn = await self.get_tmux_connection(project_name)
            result = await tmux_conn.async_send_command("list-windows -F '#{window_name}'")
            window_names = result.strip().split('\n') if result.strip() else []

            return [WindowConfig(name=name) for name in window_names]
        except Exception as e:
            raise ITerm2Error(f"Failed to get tmux windows: {e}") from e
