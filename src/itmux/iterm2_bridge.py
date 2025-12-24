"""iTerm2 Python API integration layer."""

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import iterm2

from .models import WindowSize, WindowConfig
from .exceptions import ITerm2Error, WindowCreationTimeoutError


class ITerm2Bridge:
    """iTerm2 Python APIとの連携を管理するクラス."""

    def __init__(self, connection: iterm2.Connection, app: iterm2.App):
        """
        Args:
            connection: iTerm2接続オブジェクト
            app: iTerm2アプリケーションオブジェクト
        """
        self.connection = connection
        self.app = app

    async def find_windows_by_project(self, project_name: str) -> list[iterm2.Window]:
        """プロジェクトに属するウィンドウを検索.

        Args:
            project_name: プロジェクト名

        Returns:
            list[iterm2.Window]: プロジェクトに属するウィンドウのリスト
        """
        matching_windows = []

        for window in self.app.windows:
            project_id = await window.async_get_variable("user.projectID")
            if project_id == project_name:
                matching_windows.append(window)

        return matching_windows

    async def set_window_size(
        self, window_id: str, window_size: WindowSize
    ) -> None:
        """ウィンドウサイズを変更.

        Args:
            window_id: ウィンドウID
            window_size: 変更後のウィンドウサイズ

        Raises:
            ITerm2Error: ウィンドウが見つからない、またはサイズ変更に失敗
        """
        window = self.app.get_window_by_id(window_id)
        if window is None:
            raise ITerm2Error(f"Window not found: {window_id}")

        # tmux resize-window コマンドを送信
        session = window.current_tab.current_session
        cmd = f"tmux resize-window -x {window_size.columns} -y {window_size.lines}\n"
        await session.async_send_text(cmd)

    async def detach_session(self, window_id: str) -> None:
        """tmuxセッションをデタッチ（ウィンドウを閉じる、セッションは保持）.

        Args:
            window_id: ウィンドウID

        Raises:
            ITerm2Error: ウィンドウが見つからない、またはデタッチに失敗
        """
        window = self.app.get_window_by_id(window_id)
        if window is None:
            raise ITerm2Error(f"Window not found: {window_id}")

        # ウィンドウをアクティブ化
        await window.async_activate()

        # tmux.Detach メニュー実行
        await iterm2.MainMenu.async_select_menu_item(self.connection, "tmux.Detach")

        # 待機（ウィンドウが閉じるまで）
        await asyncio.sleep(0.5)

    async def open_project_windows(
        self,
        project_name: str,
        window_configs: list[WindowConfig],
    ) -> list[str]:
        """プロジェクトのtmuxウィンドウを開く.

        1プロジェクト = 1 tmuxセッション で、複数のtmuxウィンドウを作成します。

        注意: iTerm2の設定で「Automatically bury the tmux client session after connecting」
        が有効になっている必要があります（Preferences > General > tmux）。

        Args:
            project_name: プロジェクト名
            window_configs: ウィンドウ設定のリスト

        Returns:
            list[str]: 作成されたiTerm2ウィンドウIDのリスト

        Raises:
            ITerm2Error: iTerm2 APIエラー
        """
        try:
            # 1. プロジェクトのtmuxセッションに接続（gateway取得/作成）
            gateway_session, tmux_conn = await self.get_or_create_gateway(project_name)

            # 2. 各ウィンドウを作成
            window_ids = []
            for window_config in window_configs:
                # TmuxConnection.async_create_window()で新しいtmuxウィンドウ作成
                iterm_window = await tmux_conn.async_create_window()

                # ウィンドウ名を設定（tmux rename-window）
                await tmux_conn.async_send_command(
                    f"rename-window {window_config.name}"
                )

                # iTerm2ウィンドウにタグ付け
                await iterm_window.async_set_variable("user.projectID", project_name)
                await iterm_window.async_set_variable("user.window_name", window_config.name)

                # ウィンドウサイズ復元
                if window_config.window_size:
                    await self.set_window_size(iterm_window.window_id, window_config.window_size)

                window_ids.append(iterm_window.window_id)

            return window_ids

        except Exception as e:
            raise ITerm2Error(f"Failed to open project windows: {e}") from e

    def _load_gateway_info(self, project_name: str) -> Optional[dict]:
        """プロジェクトのGateway情報を読み込み."""
        gateway_path = Path.home() / ".itmux" / "gateway.json"
        if not gateway_path.exists():
            return None

        data = json.loads(gateway_path.read_text())
        projects = data.get("projects", {})
        return projects.get(project_name)

    def _save_gateway_info(self, project_name: str, info: dict) -> None:
        """プロジェクトのGateway情報を保存."""
        gateway_path = Path.home() / ".itmux" / "gateway.json"
        gateway_path.parent.mkdir(parents=True, exist_ok=True)

        # 既存データを読み込み
        if gateway_path.exists():
            data = json.loads(gateway_path.read_text())
        else:
            data = {"projects": {}}

        # プロジェクト情報を更新
        if "projects" not in data:
            data["projects"] = {}
        data["projects"][project_name] = info

        gateway_path.write_text(json.dumps(data, indent=2))

    def _clear_gateway_info(self, project_name: str) -> None:
        """プロジェクトのGateway情報をクリア."""
        gateway_path = Path.home() / ".itmux" / "gateway.json"
        if not gateway_path.exists():
            return

        data = json.loads(gateway_path.read_text())
        if "projects" in data and project_name in data["projects"]:
            del data["projects"][project_name]
            gateway_path.write_text(json.dumps(data, indent=2))

    async def get_or_create_gateway(
        self, project_name: str
    ) -> tuple[Optional[iterm2.Session], iterm2.TmuxConnection]:
        """プロジェクトのtmuxセッションに接続するgatewayを取得/作成.

        注意: iTerm2の設定で「Automatically bury the tmux client session after connecting」
        が有効になっている必要があります（Preferences > General > tmux）。

        Args:
            project_name: プロジェクト名

        Returns:
            tuple[Optional[iterm2.Session], iterm2.TmuxConnection]:
                (gateway session, tmux connection)
                既存gateway再利用時はgateway sessionはNone

        Raises:
            ITerm2Error: Gateway作成に失敗
        """
        # 1. プロジェクトのgateway情報を読む
        gateway_info = self._load_gateway_info(project_name)

        if gateway_info:
            # 2. connection IDで既存TmuxConnectionを取得
            tmux_conn = await iterm2.async_get_tmux_connection_by_connection_id(
                self.connection, gateway_info["connection_id"]
            )

            if tmux_conn:
                # connection存在 → そのまま返す（健全性チェックは行わない）
                # gateway sessionは取得しない（使わない）
                return None, tmux_conn
            else:
                # connection IDが見つからない → gateway情報をクリアして新規作成へ
                self._clear_gateway_info(project_name)

        # 4. 既存gatewayがない、または無効 → 新規作成
        gateway = await iterm2.Window.async_create(
            self.connection,
            command=f"/opt/homebrew/bin/tmux -CC new-session -A -s {project_name}"
        )

        if not gateway:
            raise ITerm2Error("Failed to create gateway window")

        gateway_session = gateway.current_tab.current_session

        # 5. TmuxConnection取得（少し待機してから）
        await asyncio.sleep(1.0)
        tmux_conns = await iterm2.async_get_tmux_connections(self.connection)
        if not tmux_conns:
            raise ITerm2Error("Failed to get tmux connection")
        tmux_conn = tmux_conns[-1]  # 最新の接続

        # 6. 情報を保存（プロジェクト単位で）
        self._save_gateway_info(project_name, {
            "connection_id": tmux_conn.connection_id,
            "session_name": project_name,
            "created_at": datetime.now().isoformat()
        })

        return gateway_session, tmux_conn

    async def close_gateway(self, project_name: str) -> None:
        """プロジェクトのGatewayを明示的にクローズし、情報をクリア.

        Args:
            project_name: プロジェクト名

        注意: 対象プロジェクトのtmuxセッションがdetachされます。
        """
        try:
            # プロジェクトのtmuxセッションを終了（gatewayウィンドウも自動的に閉じる）
            subprocess.run(
                ["tmux", "kill-session", "-t", project_name],
                capture_output=True,
            )
        except Exception:
            # エラーが発生してもクリーンアップは続行
            pass
        finally:
            # gateway情報を必ずクリア
            self._clear_gateway_info(project_name)

    async def get_gateway_status(self, project_name: str) -> Optional[dict]:
        """プロジェクトのGateway状態を確認.

        Args:
            project_name: プロジェクト名

        Returns:
            Optional[dict]: Gateway情報（alive=True/False付き）、なければNone
        """
        gateway_info = self._load_gateway_info(project_name)
        if not gateway_info:
            return None

        # connection IDで既存TmuxConnectionを取得
        tmux_conn = await iterm2.async_get_tmux_connection_by_connection_id(
            self.connection, gateway_info["connection_id"]
        )

        # connectionが存在するかどうかだけをチェック（健全性チェックは行わない）
        is_alive = tmux_conn is not None

        return {
            **gateway_info,
            "alive": is_alive
        }
