"""tmux hookの管理."""

import os
import shlex
import iterm2


class HookManager:
    """tmuxセッションのhookを管理するクラス.

    プロジェクトの自動同期のため、window/pane操作時のhookを設定します。
    """

    # セッションスコープのhook定義（hook名, 説明, sync必要, save必要, debounce有効）
    # 将来的な追加・削除を容易にするためリストで管理
    SESSION_HOOKS = [
        ("after-new-window", "ウィンドウ作成時", True, True, False),
        ("window-unlinked", "ウィンドウ削除時", True, True, False),
        ("after-split-window", "pane分割時", False, True, False),
        ("after-kill-pane", "pane削除時", False, True, False),
        ("after-resize-pane", "paneリサイズ時", False, True, True),
    ]

    @staticmethod
    def _build_hook_command(
        project_name: str,
        needs_sync: bool,
        needs_save: bool,
        use_debounce: bool,
        itmux_command: str = "itmux"
    ) -> str:
        """hookコマンドを生成.

        Args:
            project_name: プロジェクト名
            needs_sync: sync実行が必要か
            needs_save: save実行が必要か
            use_debounce: debounceが必要か
            itmux_command: itmuxコマンドのパス

        Returns:
            str: hookから実行するコマンド文字列
        """
        current_path = os.environ.get("PATH", "")
        config_path = os.environ.get("ITMUX_CONFIG_PATH", "")
        itmux_command_env = os.environ.get("ITMUX_COMMAND", "")

        # 環境変数の設定（shlex.quote()で安全にエスケープ）
        env_vars = f"PATH={shlex.quote(current_path)}"
        if config_path:
            env_vars += f" ITMUX_CONFIG_PATH={shlex.quote(config_path)}"
        if itmux_command_env:
            env_vars += f" ITMUX_COMMAND={shlex.quote(itmux_command_env)}"

        commands = []

        if needs_sync:
            commands.append(f"{itmux_command} sync {project_name}")

        if needs_save:
            save_cmd = f"{itmux_command} save {project_name}"
            if use_debounce:
                save_cmd += " --debounce"
            commands.append(save_cmd)

        # 複数コマンドを && で連結
        command = " && ".join(commands)
        # 全体を括弧で囲んでからリダイレクト（echoの出力も含めてリダイレクトする）
        return f"({env_vars} {command}) >> ~/.itmux/hook.log 2>&1 || true"

    @staticmethod
    def _build_sync_all_command(itmux_command: str = "itmux") -> str:
        """全プロジェクトのsync --allコマンドを生成.

        Args:
            itmux_command: itmuxコマンドのパス

        Returns:
            str: hookから実行するコマンド文字列
        """
        current_path = os.environ.get("PATH", "")
        config_path = os.environ.get("ITMUX_CONFIG_PATH", "")

        # 環境変数の設定（shlex.quote()で安全にエスケープ）
        env_vars = f"PATH={shlex.quote(current_path)}"
        if config_path:
            env_vars += f" ITMUX_CONFIG_PATH={shlex.quote(config_path)}"

        return f"{env_vars} {itmux_command} sync --all >> ~/.itmux/hook.log 2>&1 || true"

    @staticmethod
    def _check_resurrect_installed() -> bool:
        """tmux-resurrectがインストールされているかチェック.

        Returns:
            bool: インストール済みの場合True
        """
        from pathlib import Path
        save_script = Path.home() / ".tmux" / "plugins" / "tmux-resurrect" / "scripts" / "save.sh"
        return save_script.exists()

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
        import sys

        # tmux-resurrectの有無を確認
        resurrect_available = self._check_resurrect_installed()
        if not resurrect_available:
            print("⚠️  tmux-resurrect not installed, pane layouts won't be saved", file=sys.stderr)

        # run-shell -b を使って外部コマンドをバックグラウンド実行
        # -b: バックグラウンド実行（デッドロック防止）
        for hook_name, description, needs_sync, needs_save, use_debounce in self.SESSION_HOOKS:
            # tmux-resurrect必要だが未インストールの場合はスキップ
            if needs_save and not resurrect_available:
                continue

            # hookコマンド生成
            command = self._build_hook_command(
                project_name, needs_sync, needs_save, use_debounce, itmux_command
            )

            # run-shell の引数全体を shlex.quote() でエスケープ
            hook_command = f"run-shell -b {shlex.quote(command)}"
            await tmux_conn.async_send_command(
                f"set-hook -t {project_name} {hook_name} {shlex.quote(hook_command)}"
            )

        # session終了時のhook（グローバルスコープ）
        # 全プロジェクトの整合性をチェック（-gで上書き、-agではない）
        # どのセッションが閉じても、全プロジェクトをチェックして存在しないセッションを削除
        sync_all_command = self._build_sync_all_command(itmux_command)
        global_hook_command = f"run-shell -b {shlex.quote(sync_all_command)}"
        await tmux_conn.async_send_command(
            f"set-hook -g session-closed {shlex.quote(global_hook_command)}"
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
            for hook_name, _, _, _, _ in self.SESSION_HOOKS:
                await tmux_conn.async_send_command(
                    f"set-hook -u -t {project_name} {hook_name}"
                )
            # session-closedはグローバルスコープなので削除しない
        except Exception:
            # hookが存在しない場合もエラーになるが、無視する
            pass
