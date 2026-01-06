"""tmuxセッションの管理."""

import iterm2
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
