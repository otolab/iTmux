"""tmuxセッションの管理."""

import iterm2
from ..models import WindowConfig
from ..gateway.gateway_manager import GatewayManager
from ..exceptions import ITerm2Error


class SessionManager:
    """tmuxセッションの管理を担当するクラス."""

    def __init__(self, connection: iterm2.Connection, gateway_manager: GatewayManager):
        """Initialize SessionManager.

        Args:
            connection: iTerm2 Connection
            gateway_manager: GatewayManager instance
        """
        self.connection = connection
        self.gateway_manager = gateway_manager

    async def get_tmux_connection(self, project_name: str) -> iterm2.TmuxConnection:
        """プロジェクトのTmuxConnectionを取得.

        gateway情報から connection_id を使って TmuxConnection を都度取得します（キャッシュしません）。

        Args:
            project_name: プロジェクト名

        Returns:
            iterm2.TmuxConnection: Tmux接続

        Raises:
            ITerm2Error: TmuxConnection取得に失敗
        """
        # gateway情報からconnection_idを取得
        gateway_info = self.gateway_manager.load(project_name)
        if not gateway_info:
            raise ITerm2Error(f"No gateway info found for project: {project_name}")

        # connection IDでTmuxConnectionを取得
        tmux_conn = await iterm2.async_get_tmux_connection_by_connection_id(
            self.connection, gateway_info["connection_id"]
        )

        if not tmux_conn:
            raise ITerm2Error(f"TmuxConnection not found for project: {project_name}")

        return tmux_conn

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
