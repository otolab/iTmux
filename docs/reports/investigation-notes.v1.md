# 調査が必要な項目

作成日: 2025-12-26

## 1. ITMUX_PROJECT 環境変数の問題 ✅ 解決

**問題:**
- orchestrator.py:129 で `os.environ["ITMUX_PROJECT"] = project_name` を設定
- Python process内でのみ有効で、次の `itmux add` 実行時には消失
- `itmux add` でプロジェクト名を省略できない

**解決策（2025-12-26 実装）:**
tmux session名から自動検出する方式に変更

```python
def _resolve_project_name(self, project_name: Optional[str]) -> str:
    if project_name is None:
        # 1. tmux内で実行されている場合、session名を取得
        if os.environ.get("TMUX"):
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{session_name}"],
                capture_output=True, text=True, check=True
            )
            project_name = result.stdout.strip()
            if project_name:
                return project_name

        # 2. 環境変数から取得（後方互換性）
        project_name = os.environ.get("ITMUX_PROJECT")
        if project_name is None:
            raise ValueError("No project specified and ITMUX_PROJECT not set")

    return project_name
```

**効果:**
- tmux session内で `itmux add` を実行すると、session名（=project名）を自動検出
- プロジェクト名の省略が可能に
- 複数プロジェクトを開いていても、それぞれのsession内で正しく動作

## 2. hookの永続性

**疑問:**
- tmuxセッションをdetachしたとき、hookは残るのか？
- 次回attachしたとき、hookは再設定する必要があるのか？

**現状:**
- `open` のたびに `setup_hooks()` を呼んでいる（orchestrator.py:126）
- 冪等性があるのか不明

**調査項目:**
- [ ] tmuxのhookがsessionに永続化される仕様を確認
- [ ] detach/attach時のhook動作を検証
- [ ] `set-hook` の冪等性を確認（同じhookを複数回設定したらどうなるか）

## 3. session-closed hookの `-ag` オプション

**疑問:**
- session-closedで使われている `set-hook -ag`（hook_manager.py:53）
- 他のhookは `-t {project_name}` でセッションスコープなのに、なぜsession-closedだけ `-ag`（append, global）なのか？

**現状のコード:**
```python
# セッションスコープ
await tmux_conn.async_send_command(
    f"set-hook -t {project_name} after-new-window \"...\""
)

# グローバルスコープ + append
await tmux_conn.async_send_command(
    f"set-hook -ag session-closed \"...\""
)
```

**調査項目:**
- [ ] session-closedがセッションスコープで設定できない理由を確認
- [ ] `-a`（append）の必要性を確認（複数プロジェクトで上書きされないため？）
- [ ] グローバルhookの削除タイミングを検討（現在は削除していない）

## 4. window_idsの使い道

**現状:**
- `open_project_windows()` が window_ids のリストを返している（bridge.py:307）
- orchestrator.py:118 では戻り値を受け取っていない
- 単に取れたから返しているが、実際には使っていない

**将来の用途:**
- ウィンドウサイズの復元で使う可能性
- 現時点では使う予定なし

**対応:**
- 将来の拡張のため、現状のまま保持
- 特に調査の必要なし
