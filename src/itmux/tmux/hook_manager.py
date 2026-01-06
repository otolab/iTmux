"""tmux hookの管理."""

import os
import iterm2


class HookManager:
    """tmuxセッションのhookを管理するクラス.

    プロジェクトの自動同期のため、window/pane操作時のhookを設定します。
    """

    # セッションスコープのhook定義（hook名, 説明, debounce有効）
    # 将来的な追加・削除を容易にするためリストで管理
    SESSION_HOOKS = [
        ("after-new-window", "ウィンドウ作成時", False),
        ("window-unlinked", "ウィンドウ削除時", False),
        ("after-split-window", "pane分割時", False),
        ("after-kill-pane", "pane削除時", False),
        ("after-resize-pane", "paneリサイズ時", True),  # debounce有効
    ]

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
    def _build_debounced_hook_command(
        project_name: str,
        hook_name: str,
        itmux_command: str = "itmux",
        debounce_seconds: int = 1
    ) -> str:
        """debounce付きhookコマンドを生成.

        Args:
            project_name: プロジェクト名
            hook_name: hook名（ロックファイル識別用）
            itmux_command: itmuxコマンドのパス
            debounce_seconds: debounce時間（秒）

        Returns:
            str: debounce付きhookから実行するコマンド文字列
        """
        current_path = os.environ.get("PATH", "")
        # シェルスクリプトでdebounceを実装
        # ロックファイルに最後の実行時刻を記録し、指定秒数以内は実行しない
        return (
            f"LOCK=~/.itmux/.lock_{project_name}_{hook_name}; "
            f"NOW=$(date +%s); "
            f"LAST=$(cat $LOCK 2>/dev/null || echo 0); "
            f"if [ $((NOW - LAST)) -ge {debounce_seconds} ]; then "
            f"echo $NOW > $LOCK; "
            f"PATH={current_path} {itmux_command} sync {project_name} >> ~/.itmux/hook.log 2>&1 || true; "
            f"fi"
        )

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
        # run-shell -b を使って外部コマンドをバックグラウンド実行
        # -b: バックグラウンド実行（デッドロック防止）
        for hook_name, description, use_debounce in self.SESSION_HOOKS:
            if use_debounce:
                # debounce付きhookコマンド
                command = self._build_debounced_hook_command(
                    project_name, hook_name, itmux_command
                )
            else:
                # 通常のhookコマンド
                command = self._build_hook_command(project_name, itmux_command)

            await tmux_conn.async_send_command(
                f"set-hook -t {project_name} {hook_name} \"run-shell -b '{command}'\""
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
            for hook_name, _, _ in self.SESSION_HOOKS:
                await tmux_conn.async_send_command(
                    f"set-hook -u -t {project_name} {hook_name}"
                )
            # session-closedはグローバルスコープなので削除しない
        except Exception:
            # hookが存在しない場合もエラーになるが、無視する
            pass
