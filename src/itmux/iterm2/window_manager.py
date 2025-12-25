"""iTerm2ウィンドウの管理."""

import iterm2
from typing import Optional


class WindowManager:
    """iTerm2ウィンドウの作成・タグ付けを管理するクラス."""

    def __init__(self, app: iterm2.App):
        """Initialize WindowManager.

        Args:
            app: iTerm2 App instance
        """
        self.app = app

    async def tag_window_by_tmux_id(
        self,
        tmux_window_id: str,
        project_name: str,
        window_name: str
    ) -> Optional[str]:
        """tmux_window_idでiTerm2ウィンドウを探してタグ付け.

        Args:
            tmux_window_id: tmuxウィンドウID（@なし）
            project_name: プロジェクト名
            window_name: ウィンドウ名

        Returns:
            タグ付けしたウィンドウID、見つからない場合はNone
        """
        for window in self.app.windows:
            if window.current_tab and window.current_tab.tmux_window_id == tmux_window_id:
                await window.async_set_variable("user.projectID", project_name)
                await window.async_set_variable("user.window_name", window_name)
                return window.window_id
        return None

    async def find_windows_by_project(self, project_name: str) -> list[iterm2.Window]:
        """プロジェクト名でiTerm2ウィンドウを検索.

        Args:
            project_name: プロジェクト名

        Returns:
            該当するウィンドウのリスト
        """
        result = []
        for window in self.app.windows:
            project_id = await window.async_get_variable("user.projectID")
            if project_id == project_name:
                result.append(window)
        return result
