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

    async def detach_session(self, project_name: str) -> None:
        """tmuxセッションをデタッチ（ウィンドウを閉じる、セッションは保持）.

        Args:
            project_name: プロジェクト名

        Raises:
            ITerm2Error: デタッチに失敗
        """
        try:
            # TmuxConnection を都度取得
            tmux_conn = await self.get_tmux_connection(project_name)

            # tmux detach-client コマンドを実行
            await tmux_conn.async_send_command("detach-client")

            # ウィンドウが閉じるのを待つ
            await asyncio.sleep(0.5)

        except Exception as e:
            raise ITerm2Error(f"Failed to detach session: {e}") from e

    async def open_project_windows(
        self,
        project_name: str,
        window_configs: list[WindowConfig],
    ) -> list[str]:
        """プロジェクトのtmuxウィンドウを開く.

        1プロジェクト = 1 tmuxセッション で、複数のtmuxウィンドウを作成します。
        最低限1つのウィンドウが必要で、window_configs が空の場合は "default" という名前のウィンドウを作成します。

        注意: iTerm2の設定で「Automatically bury the tmux client session after connecting」
        が有効になっている必要があります（Preferences > General > tmux）。

        Args:
            project_name: プロジェクト名
            window_configs: ウィンドウ設定のリスト（空の場合は default を作成）

        Returns:
            list[str]: 作成されたiTerm2ウィンドウIDのリスト

        Raises:
            ITerm2Error: iTerm2 APIエラー
        """
        try:
            # 1. window_configs が空なら default を追加
            if not window_configs:
                window_configs = [WindowConfig(name="default")]

            # 2. セッションに接続（最初のウィンドウ名を指定）
            await self.connect_to_session(project_name, window_configs[0].name)

            # 3. TmuxConnection を取得
            tmux_conn = await self.get_tmux_connection(project_name)

            # 4. 既存のtmuxウィンドウ名を取得
            result = await tmux_conn.async_send_command("list-windows -F '#{window_name}'")
            existing_window_names = set(result.strip().split('\n')) if result.strip() else set()

            # 5. 最初のウィンドウにタグ付け（connect_to_sessionで作成済み）
            await asyncio.sleep(0.5)  # ウィンドウ作成を待つ
            window_ids = []

            # tmux window 0（最初のウィンドウ）を探してタグ付け
            # tmuxコマンドでwindow 0のtmux_window_idを取得
            result = await tmux_conn.async_send_command("list-windows -F '#{window_index}:#{window_id}:#{window_name}'")
            lines = result.strip().split('\n') if result.strip() else []

            # window 0 を探す
            first_tmux_window_id = None
            for line in lines:
                parts = line.split(':')
                if len(parts) >= 3 and parts[0] == '0':
                    # @記号を削除（iTerm2 APIの tmux_window_id は@なし）
                    first_tmux_window_id = parts[1].lstrip('@')
                    break

            if first_tmux_window_id:
                # このtmux_window_idを持つiTerm2 Windowを探す
                for window in self.app.windows:
                    if window.current_tab:
                        tab_tmux_window_id = window.current_tab.tmux_window_id
                        if tab_tmux_window_id == first_tmux_window_id:
                            # 見つけた！タグ付け
                            await window.async_set_variable("user.projectID", project_name)
                            await window.async_set_variable("user.window_name", window_configs[0].name)
                            window_ids.append(window.window_id)
                            break

            # 6. 2つ目以降のウィンドウを作成（存在しない場合のみ）
            for i, window_config in enumerate(window_configs[1:], start=1):
                # 既に存在するウィンドウはスキップ
                if window_config.name in existing_window_names:
                    continue

                # 新しいウィンドウを作成
                iterm_window = await tmux_conn.async_create_window()

                # ウィンドウ名を設定
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

    async def connect_to_session(self, project_name: str, first_window_name: str = "default") -> None:
        """プロジェクトのtmuxセッションに接続.

        セッションが存在しなければ作成します。
        既に接続済みの場合は何もしません。

        注意: iTerm2の設定で「Automatically bury the tmux client session after connecting」
        が有効になっている必要があります（Preferences > General > tmux）。

        Args:
            project_name: プロジェクト名
            first_window_name: 最初のウィンドウ名（デフォルト: "default"）

        Raises:
            ITerm2Error: セッション接続に失敗
        """
        # 1. gateway情報を確認してconnectionが有効か確認
        gateway_info = self._load_gateway_info(project_name)
        if gateway_info:
            # connection IDで確認
            tmux_conn = await iterm2.async_get_tmux_connection_by_connection_id(
                self.connection, gateway_info["connection_id"]
            )
            if tmux_conn:
                # connection は有効 → 既に接続済み
                return
            else:
                # connection が無効 → gateway情報をクリアして再接続
                self._clear_gateway_info(project_name)

        # 3. 新規接続（最初のウィンドウ名を指定）
        gateway = await iterm2.Window.async_create(
            self.connection,
            command=f"/opt/homebrew/bin/tmux -CC new-session -A -s {project_name} -n {first_window_name}"
        )

        if not gateway:
            raise ITerm2Error("Failed to create gateway window")

        # 4. TmuxConnection取得（少し待機してから）
        await asyncio.sleep(1.0)
        tmux_conns = await iterm2.async_get_tmux_connections(self.connection)
        if not tmux_conns:
            raise ITerm2Error("Failed to get tmux connection")
        tmux_conn = tmux_conns[-1]  # 最新の接続

        # 5. 情報を保存
        self._save_gateway_info(project_name, {
            "connection_id": tmux_conn.connection_id,
            "session_name": project_name,
            "created_at": datetime.now().isoformat()
        })

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
        gateway_info = self._load_gateway_info(project_name)
        if not gateway_info:
            raise ITerm2Error(f"No gateway info found for project: {project_name}")

        # connection IDでTmuxConnectionを取得
        tmux_conn = await iterm2.async_get_tmux_connection_by_connection_id(
            self.connection, gateway_info["connection_id"]
        )

        if not tmux_conn:
            raise ITerm2Error(f"TmuxConnection not found for project: {project_name}")

        return tmux_conn

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
