"""tmux hookの管理."""

import os
import iterm2


class HookManager:
    """tmuxセッションのhookを管理するクラス.

    プロジェクトの自動同期のため、window作成・削除・名前変更時のhookを設定します。
    """

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
        # hookから実行されるコマンドにPATHを含める
        # uvコマンドが見つかるように環境変数を設定
        current_path = os.environ.get("PATH", "")
        # ログファイルに出力（エスケープを避けるためシンプルに）
        hook_command = f"PATH={current_path} {itmux_command} sync {project_name} >> ~/.itmux/hook.log 2>&1 || true"

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

        # window名変更時のhook（セッションスコープ）
        await tmux_conn.async_send_command(
            f"set-hook -t {project_name} after-rename-window \"run-shell -b '{hook_command}'\""
        )

        # session終了時のhook（グローバルスコープ）
        # シンプルに、このプロジェクトのsyncを実行
        # 既にセッションが終了しているため、sync内でセッション存在チェックが走り、
        # プロジェクトが自動削除される
        await tmux_conn.async_send_command(
            f"set-hook -ag session-closed \"run-shell -b '{hook_command}'\""
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
            await tmux_conn.async_send_command(
                f"set-hook -u -t {project_name} after-rename-window"
            )
            # session-closedはグローバルスコープなので削除しない
        except Exception:
            # hookが存在しない場合もエラーになるが、無視する
            pass
