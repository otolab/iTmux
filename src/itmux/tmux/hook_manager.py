"""tmux hookの管理."""

import os
import iterm2


class HookManager:
    """tmuxセッションのhookを管理するクラス.

    プロジェクトの自動同期のため、window作成・削除・名前変更時のhookを設定します。
    """

    @staticmethod
    def _build_hook_command(project_name: str, itmux_command: str = "itmux") -> str:
        """単一プロジェクトのsyncコマンドを生成.

        Args:
            project_name: プロジェクト名
            itmux_command: itmuxコマンドのパス

        Returns:
            str: hookから実行するコマンド文字列
        """
        current_path = os.environ.get("PATH", "")
        return f"PATH={current_path} {itmux_command} sync {project_name} >> ~/.itmux/hook.log 2>&1 || true"

    @staticmethod
    def _build_sync_all_command(itmux_command: str = "itmux") -> str:
        """全プロジェクトのsync --allコマンドを生成.

        Args:
            itmux_command: itmuxコマンドのパス

        Returns:
            str: hookから実行するコマンド文字列
        """
        current_path = os.environ.get("PATH", "")
        return f"PATH={current_path} {itmux_command} sync --all >> ~/.itmux/hook.log 2>&1 || true"

    async def setup_hooks(
        self,
        tmux_conn: iterm2.TmuxConnection,
        project_name: str,
        itmux_command: str = "itmux"
    ) -> None:
        """プロジェクトのtmuxセッションにhookを設定して自動同期を有効化.

        Args:
            tmux_conn: TmuxConnection
            project_name: プロジェクト名
            itmux_command: itmuxコマンドのパス（デフォルト: "itmux"）
        """
        # セッションスコープのhookで使用するコマンド
        hook_command = self._build_hook_command(project_name, itmux_command)

        # run-shell -b を使って外部コマンドをバックグラウンド実行
        # -b: バックグラウンド実行（デッドロック防止）
        # window作成時のhook（セッションスコープ）
        await tmux_conn.async_send_command(
            f"set-hook -t {project_name} after-new-window \"run-shell -b '{hook_command}'\""
        )

        # window削除時のhook（セッションスコープ）
        await tmux_conn.async_send_command(
            f"set-hook -t {project_name} window-unlinked \"run-shell -b '{hook_command}'\""
        )

        # session終了時のhook（グローバルスコープ）
        # 全プロジェクトの整合性をチェック（-gで上書き、-agではない）
        # どのセッションが閉じても、全プロジェクトをチェックして存在しないセッションを削除
        sync_all_command = self._build_sync_all_command(itmux_command)
        await tmux_conn.async_send_command(
            f"set-hook -g session-closed \"run-shell -b '{sync_all_command}'\""
        )

    async def remove_hooks(
        self,
        tmux_conn: iterm2.TmuxConnection,
        project_name: str
    ) -> None:
        """プロジェクトのtmuxセッションからhookを削除.

        Args:
            tmux_conn: TmuxConnection
            project_name: プロジェクト名

        注意: グローバルsession-closedフックは削除しない（他のプロジェクトも使用）
        """
        try:
            # セッションスコープのhookを削除（-u オプション）
            await tmux_conn.async_send_command(
                f"set-hook -u -t {project_name} after-new-window"
            )
            await tmux_conn.async_send_command(
                f"set-hook -u -t {project_name} window-unlinked"
            )
            # session-closedはグローバルスコープなので削除しない
        except Exception:
            # hookが存在しない場合もエラーになるが、無視する
            pass
