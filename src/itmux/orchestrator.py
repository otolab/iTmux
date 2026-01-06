"""iTmux project orchestrator."""

import asyncio
import os
import subprocess
from typing import Optional

from .config import ConfigManager
from .iterm2 import ITerm2Bridge
from .models import WindowConfig
from .exceptions import ProjectNotFoundError


class ProjectOrchestrator:
    """プロジェクトのopen/close/add/list機能を提供するオーケストレーター."""

    def __init__(self, config_manager: ConfigManager, iterm2_bridge: ITerm2Bridge):
        """
        Args:
            config_manager: 設定管理インスタンス
            iterm2_bridge: iTerm2ブリッジインスタンス
        """
        self.config = config_manager
        self.bridge = iterm2_bridge

    def _tmux_has_session(self, session_name: str) -> bool:
        """tmuxセッションが存在するか確認.

        Args:
            session_name: セッション名

        Returns:
            bool: セッションが存在すればTrue
        """
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
        )
        return result.returncode == 0

    async def _get_windows_from_user_variables(self, project_name: str) -> list[WindowConfig]:
        """iTerm2のuser変数からウィンドウリストを取得.

        Args:
            project_name: プロジェクト名

        Returns:
            list[WindowConfig]: ウィンドウ設定のリスト（user.window_nameベース）
        """
        windows = await self.bridge.find_windows_by_project(project_name)
        result = []
        for window in windows:
            window_id = await window.async_get_variable("user.window_name")
            if window_id:
                result.append(WindowConfig(name=window_id))
        return result

    def _resolve_project_name(self, project_name: Optional[str]) -> str:
        """プロジェクト名を解決（引数 or tmux session or 環境変数）.

        Args:
            project_name: プロジェクト名（Noneの場合は自動検出）

        Returns:
            str: 解決されたプロジェクト名

        Raises:
            ValueError: プロジェクト名が指定されておらず、tmuxセッションからも環境変数からも取得できない
        """
        if project_name is None:
            # 1. tmux内で実行されている場合、session名を取得
            if os.environ.get("TMUX"):
                try:
                    result = subprocess.run(
                        ["tmux", "display-message", "-p", "#{session_name}"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    project_name = result.stdout.strip()
                    if project_name:
                        return project_name
                except Exception:
                    # tmuxコマンド失敗時は次の方法を試す
                    pass

            # 2. 環境変数から取得（後方互換性）
            project_name = os.environ.get("ITMUX_PROJECT")
            if project_name is None:
                raise ValueError("No project specified and ITMUX_PROJECT not set")

        return project_name

    def _generate_window_name(self, project_name: str) -> str:
        """ウィンドウ名を自動生成.

        Args:
            project_name: プロジェクト名

        Returns:
            str: 生成されたウィンドウ名（例: "window-1", "window-2"）
        """
        project = self.config.get_project(project_name)
        existing_windows = {w.name for w in project.tmux_windows}

        counter = 1
        while True:
            candidate = f"window-{counter}"
            if candidate not in existing_windows:
                return candidate
            counter += 1

    @staticmethod
    def _should_save_resurrect(project_name: str, debounce_seconds: float = 1.0) -> bool:
        """tmux-resurrect保存のdebounce判定.

        Args:
            project_name: プロジェクト名
            debounce_seconds: debounce時間（秒）

        Returns:
            bool: 保存を実行すべき場合True
        """
        import time
        from pathlib import Path

        lock_file = Path.home() / ".itmux" / f".last_save_{project_name}"
        now = time.time()

        if lock_file.exists():
            try:
                last = float(lock_file.read_text().strip())
                if now - last < debounce_seconds:
                    return False  # 指定秒数以内なのでスキップ
            except (ValueError, OSError):
                pass  # ファイル読み取り失敗時は実行

        # タイムスタンプ更新
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(str(now))
        return True

    def _save_tmux_resurrect(self, debounce: bool = False, project_name: str = "") -> None:
        """tmux-resurrectで状態を保存.

        Args:
            debounce: debounce判定を行うか
            project_name: debounce判定用のプロジェクト名（debounce=Trueの場合必須）

        tmux-continuumの自動保存の代替として、sync時に手動で保存を実行します。
        tmux-resurrectの保存スクリプトが存在する場合のみ実行します。
        """
        import sys
        import subprocess
        from pathlib import Path

        # debounce判定
        if debounce:
            if not project_name:
                print(f"[save] Error: project_name required for debounce", file=sys.stderr)
                return
            if not self._should_save_resurrect(project_name):
                print(f"[save] Skipped (debounce)", file=sys.stderr)
                return

        save_script = Path.home() / ".tmux" / "plugins" / "tmux-resurrect" / "scripts" / "save.sh"

        if not save_script.exists():
            # tmux-resurrectがインストールされていない場合はスキップ
            return

        try:
            result = subprocess.run(
                [str(save_script)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            if result.returncode != 0:
                print(f"[save] tmux-resurrect save failed: {result.stderr}", file=sys.stderr)
            else:
                print(f"[save] tmux-resurrect saved", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print(f"[save] tmux-resurrect save timeout", file=sys.stderr)
        except Exception as e:
            print(f"[save] tmux-resurrect save error: {e}", file=sys.stderr)

    def list(self) -> dict:
        """プロジェクト一覧取得.

        Returns:
            dict: プロジェクト情報の辞書
                {
                    "project-name": {
                        "windows": ["window1", "window2"],
                        "count": 2
                    }
                }
        """
        result = {}
        for project_name in self.config.list_projects():
            project = self.config.get_project(project_name)
            result[project_name] = {
                "windows": [w.name for w in project.tmux_windows],
                "count": len(project.tmux_windows),
            }
        return result

    def _is_tmux_running(self) -> bool:
        """tmuxプロセスが起動しているかチェック.

        Returns:
            bool: tmuxが起動していればTrue
        """
        result = subprocess.run(
            ["tmux", "ls"],
            capture_output=True,
        )
        return result.returncode == 0

    def _restore_tmux_sessions(self) -> None:
        """tmux-resurrectで保存されたセッションを復元.

        tmux-resurrectのrestore.shを実行して全セッションを復元します。
        """
        import sys
        from pathlib import Path

        restore_script = Path.home() / ".tmux" / "plugins" / "tmux-resurrect" / "scripts" / "restore.sh"
        if not restore_script.exists():
            print("[restore] tmux-resurrect not installed, skipping restore", file=sys.stderr)
            return

        print("[restore] Restoring tmux sessions...", file=sys.stderr)
        try:
            result = subprocess.run(
                [str(restore_script)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if result.returncode != 0:
                print(f"[restore] Failed: {result.stderr}", file=sys.stderr)
            else:
                print("[restore] Sessions restored", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("[restore] Timeout", file=sys.stderr)
        except Exception as e:
            print(f"[restore] Error: {e}", file=sys.stderr)

    async def open(self, project_name: str, create_default: bool = True) -> None:
        """プロジェクトを開く.

        プロジェクトが存在しない場合は自動作成します。

        Args:
            project_name: プロジェクト名
            create_default: プロジェクトのウィンドウが0個の場合、defaultウィンドウを作成するか

        Raises:
            ITerm2Error: iTerm2操作が失敗
        """
        # 0. tmuxが起動していない場合、tmux-resurrectで復元
        if not self._is_tmux_running():
            self._restore_tmux_sessions()

        # 1. プロジェクト設定取得（存在しない場合は作成）
        try:
            project = self.config.get_project(project_name)
        except ProjectNotFoundError:
            # プロジェクトが存在しない → 空のプロジェクトを作成
            self.config.create_project(project_name, windows=[])
            project = self.config.get_project(project_name)

        # 2. 既存のiTerm2ウィンドウを検索（既に開いているwindowを特定）
        existing_windows = await self.bridge.find_windows_by_project(project_name)
        existing_window_names = set()
        for window in existing_windows:
            window_name = await window.async_get_variable("user.window_name")
            if window_name:
                existing_window_names.add(window_name)

        # 3. まだ開かれていないwindowだけを開く（差分のみ）
        windows_to_open = [
            w for w in project.tmux_windows
            if w.name not in existing_window_names
        ]

        # windows_to_openが空でも、プロジェクトのウィンドウが0個かつcreate_default=Trueなら開く
        if windows_to_open or (not project.tmux_windows and create_default):
            await self.bridge.open_project_windows(project_name, windows_to_open)

        # 4. hookを設定（自動同期を有効化）
        # セッションスコープのhook（after-new-window等）は上書きされるため、
        # グローバルのsession-closedも上書きされるため、何回openしても多重登録されない
        itmux_command = os.environ.get("ITMUX_COMMAND", "itmux")
        await self.bridge.setup_hooks(project_name, itmux_command=itmux_command)

        # 5. 環境変数設定
        os.environ["ITMUX_PROJECT"] = project_name

    async def sync(self, project_name: Optional[str] = None, sync_all: bool = False) -> None:
        """プロジェクトの状態を同期（tmuxセッション → config.json）.

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得、sync_all=Trueの場合は無視）
            sync_all: 全プロジェクトの整合性をチェック（session-closed hookから呼ばれる）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない（sync_all=Falseの場合のみ）
        """
        import sys
        print(f"[sync] START pid={os.getpid()}", file=sys.stderr)

        if sync_all:
            await self._sync_all_projects()
        else:
            await self._sync_single_project(project_name)

        # tmux-resurrectで状態を保存（continuum代替）
        self._save_tmux_resurrect()

        print(f"[sync] END", file=sys.stderr)

    def save(self, project_name: Optional[str] = None, debounce: bool = False) -> None:
        """tmux-resurrectで状態を保存.

        Args:
            project_name: プロジェクト名（debounce=Trueの場合は必須、省略時は環境変数から取得）
            debounce: debounce判定を行うか（連続実行の防止）

        Raises:
            ProjectNotFoundError: project_nameが必要だが指定されていない
        """
        import sys
        print(f"[save] START pid={os.getpid()}", file=sys.stderr)

        # debounce有効時はproject_name必須
        if debounce:
            if not project_name:
                project_name = os.environ.get("ITMUX_PROJECT")
            if not project_name:
                print(f"[save] Error: project_name required for debounce", file=sys.stderr)
                return

        # tmux-resurrect保存実行
        self._save_tmux_resurrect(debounce=debounce, project_name=project_name or "")

        print(f"[save] END", file=sys.stderr)

    async def _sync_all_projects(self) -> None:
        """全プロジェクトの整合性をチェック（session-closed hookから呼ばれる）.

        セッションが存在しないプロジェクトをconfig.jsonから削除します。
        """
        import sys
        print(f"[sync] Checking all projects", file=sys.stderr)

        for proj_name in self.config.list_projects():
            if not self._tmux_has_session(proj_name):
                print(f"[sync] Deleting project without session: {proj_name}", file=sys.stderr)
                try:
                    self.config.delete_project(proj_name)
                except Exception:
                    pass

    async def _sync_single_project(self, project_name: Optional[str] = None) -> None:
        """単一プロジェクトの状態を同期（tmuxセッション → config.json）.

        tmuxセッションが存在しない場合、プロジェクトをconfig.jsonから削除します。
        セッションが存在する場合、ウィンドウリストをconfig.jsonに反映します。

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        import sys

        # 1. プロジェクト名決定
        project_name = self._resolve_project_name(project_name)
        print(f"[sync] project={project_name}", file=sys.stderr)

        # 2. tmuxセッションが存在するかチェック
        if not self._tmux_has_session(project_name):
            # セッション終了 → プロジェクトを削除
            print(f"[sync] Session not found, deleting project", file=sys.stderr)
            try:
                self.config.delete_project(project_name)
            except Exception:
                # プロジェクトが既に存在しない場合は無視
                pass
            return

        # 3. iTerm2のuser変数から実際のウィンドウリストを取得
        print(f"[sync] Getting windows from user variables", file=sys.stderr)
        windows_config = await self._get_windows_from_user_variables(project_name)
        print(f"[sync] Got {len(windows_config)} windows", file=sys.stderr)

        # 4. 設定を更新
        if windows_config:
            try:
                self.config.update_project(project_name, windows_config)
                print(f"[sync] Config updated", file=sys.stderr)
            except ProjectNotFoundError:
                # プロジェクトが存在しない場合は作成してから更新
                print(f"[sync] Project not found, creating", file=sys.stderr)
                self.config.create_project(project_name, windows_config)
                print(f"[sync] Project created", file=sys.stderr)

    async def close(self, project_name: Optional[str] = None) -> None:
        """プロジェクトを閉じる（自動同期）.

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        # 1. プロジェクト名決定
        project_name = self._resolve_project_name(project_name)

        # 2. プロジェクトのiTerm2ウィンドウを検索
        windows = await self.bridge.find_windows_by_project(project_name)

        # 3. ウィンドウが見つからなければ何もしない
        if not windows:
            return

        # 4. 同期
        await self.sync(project_name)

        # 5. セッション全体をdetach（1つのウィンドウをアクティブにしてDetachすれば全ウィンドウが閉じる）
        import iterm2
        if windows:
            await windows[0].async_activate()
            await iterm2.MainMenu.async_select_menu_item(
                self.bridge.connection,
                "tmux.Detach"
            )

        # 6. 環境変数クリア
        if "ITMUX_PROJECT" in os.environ:
            del os.environ["ITMUX_PROJECT"]

    async def add(
        self, project_name: Optional[str] = None, window_name: Optional[str] = None
    ) -> None:
        """プロジェクトに新規ウィンドウ追加.

        Args:
            project_name: プロジェクト名（省略時は環境変数から取得）
            window_name: ウィンドウ名（省略時は自動生成）

        Raises:
            ProjectNotFoundError: プロジェクトが存在しない
        """
        # 1. プロジェクト名決定
        project_name = self._resolve_project_name(project_name)

        # 2. ウィンドウ名決定
        if window_name is None:
            window_name = self._generate_window_name(project_name)

        # 3. 新規ウィンドウ作成
        await self.bridge.add_window(project_name, window_name)

        # 4. 完了（hookが発火してconfig.jsonに自動追加される）
        # after-new-window hookにより、itmux sync が実行され、
        # config.jsonに自動的に追加されるため、手動での追加は不要
