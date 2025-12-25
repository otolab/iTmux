# DRY原則調査レポート v1

調査日: 2025-12-25
対象: iTmux コードベース（リファクタリング後）

## 調査概要

リファクタリング後のコードベースに対して、DRY（Don't Repeat Yourself）原則の観点から改善可能な箇所を調査した。

## 発見された重複パターン

### 1. CLIコマンドのエラーハンドリング（重要度: 高）

**場所**: `src/itmux/cli.py`
**重複箇所**: 5箇所（open, sync, close, add, list コマンド）

**重複コード例**:
```python
# open コマンド (46-57行)
try:
    asyncio.run(_open())
    click.echo(f"✓ Opened project: {project}")
except ProjectNotFoundError as e:
    click.echo(f"✗ Error: {e}", err=True)
    sys.exit(1)
except ITerm2Error as e:
    click.echo(f"✗ iTerm2 Error: {e}", err=True)
    sys.exit(1)
except Exception as e:
    click.echo(f"✗ Unexpected error: {e}", err=True)
    sys.exit(1)

# sync コマンド (68-82行) - ほぼ同じパターン
# close コマンド (93-107行) - ほぼ同じパターン
# add コマンド (119-133行) - ほぼ同じパターン
# list コマンド (143-160行) - 若干異なる（ConfigError追加）
```

**問題点**:
- 同じ例外ハンドリングパターンが5回繰り返されている
- ValueErrorの処理がsync, close, addで重複
- コード量: 約60行の重複

**改善案**:
```python
def run_async_command(coro, success_message: str, handle_value_error: bool = False):
    """非同期コマンドを実行し、共通のエラーハンドリングを適用."""
    try:
        asyncio.run(coro)
        click.echo(success_message)
    except ValueError as e:
        if handle_value_error:
            click.echo(f"✗ Error: {e}", err=True)
            sys.exit(1)
        raise
    except ProjectNotFoundError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ITerm2Error as e:
        click.echo(f"✗ iTerm2 Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"✗ Config Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)
```

**期待される効果**:
- コード量削減: 約40行
- エラーハンドリングの一貫性向上
- 新しい例外タイプの追加が容易

---

### 2. プロジェクト名の環境変数取得（重要度: 中）

**場所**: `src/itmux/orchestrator.py`
**重複箇所**: 3箇所（sync, close, add メソッド）

**重複コード例**:
```python
# sync メソッド (119-122行)
if project_name is None:
    project_name = os.environ.get("ITMUX_PROJECT")
    if project_name is None:
        raise ValueError("No project specified and ITMUX_PROJECT not set")

# close メソッド (154-157行) - 完全に同じ
# add メソッド (185-188行) - 完全に同じ
```

**問題点**:
- 完全に同じロジックが3箇所で繰り返されている
- エラーメッセージも全て同じ

**改善案**:
```python
def _resolve_project_name(self, project_name: Optional[str]) -> str:
    """プロジェクト名を解決（引数 or 環境変数）.

    Args:
        project_name: プロジェクト名（Noneの場合は環境変数から取得）

    Returns:
        str: 解決されたプロジェクト名

    Raises:
        ValueError: プロジェクト名が指定されておらず、環境変数も未設定
    """
    if project_name is None:
        project_name = os.environ.get("ITMUX_PROJECT")
        if project_name is None:
            raise ValueError("No project specified and ITMUX_PROJECT not set")
    return project_name
```

**使用例**:
```python
async def sync(self, project_name: Optional[str] = None) -> None:
    project_name = self._resolve_project_name(project_name)
    # ...
```

**期待される効果**:
- コード量削減: 約8行
- ロジックの一元化
- 将来的な環境変数名変更が容易

---

### 3. iTerm2ウィンドウのタグ付け（重要度: 中）

**場所**: `src/itmux/iterm2/bridge.py`
**重複箇所**: 2箇所（add_window, open_project_windows メソッド）

**重複コード例**:
```python
# add_window メソッド (233-234行)
await iterm_window.async_set_variable("user.projectID", project_name)
await iterm_window.async_set_variable("user.window_name", window_name)

# open_project_windows メソッド (328-329行) - 完全に同じパターン
await iterm_window.async_set_variable("user.projectID", project_name)
await iterm_window.async_set_variable("user.window_name", window_config.name)
```

**問題点**:
- 同じタグ付けパターンが2箇所で繰り返されている
- window_manager.py にはtag_window_by_tmux_idがあるが、直接タグ付けする機能がない

**改善案**:
WindowManagerに直接タグ付けメソッドを追加:
```python
# window_manager.py
async def tag_window(
    self,
    window: iterm2.Window,
    project_name: str,
    window_name: str
) -> None:
    """iTerm2ウィンドウにプロジェクトタグを設定.

    Args:
        window: iTerm2ウィンドウ
        project_name: プロジェクト名
        window_name: ウィンドウ名
    """
    await window.async_set_variable("user.projectID", project_name)
    await window.async_set_variable("user.window_name", window_name)
```

**使用例**:
```python
# bridge.py
await self.window_manager.tag_window(iterm_window, project_name, window_name)
```

**期待される効果**:
- タグ付けロジックの一元化
- WindowManagerの責務がより明確に
- タグのキー名変更が容易

---

### 4. tmuxコマンド結果のパース（重要度: 低）

**場所**: `src/itmux/iterm2/bridge.py`
**重複箇所**: 3箇所（open_project_windows メソッド内）

**重複パターン例**:
```python
# 273-274行
result = await tmux_conn.async_send_command("list-windows -F '#{window_name}'")
existing_window_names = set(result.strip().split('\n')) if result.strip() else set()

# 281-282行
result = await tmux_conn.async_send_command("list-windows -F '#{window_index}:#{window_id}:#{window_name}'")
lines = result.strip().split('\n') if result.strip() else []

# 304-305行
result = await tmux_conn.async_send_command("list-windows -F '#{window_name}:#{window_id}'")
lines = result.strip().split('\n') if result.strip() else []
```

**問題点**:
- `result.strip().split('\n') if result.strip() else ...` パターンが3箇所
- session_manager.py (68行) にも類似パターンあり

**改善案**:
SessionManagerにユーティリティメソッドを追加:
```python
# session_manager.py
def _parse_tmux_command_output(self, result: str) -> list[str]:
    """tmuxコマンド出力を行ごとに分割.

    Args:
        result: tmuxコマンドの出力

    Returns:
        list[str]: 行のリスト（空の場合は空リスト）
    """
    return result.strip().split('\n') if result.strip() else []
```

**期待される効果**:
- パースロジックの一元化
- 空文字チェックの統一
- ただし、改善効果は小さい（コード量削減は約4行程度）

---

### 5. 例外のラップ（重要度: 低）

**場所**: `src/itmux/iterm2/bridge.py`
**重複箇所**: 5箇所

**重複パターン例**:
```python
# detach_session (91-92行)
except Exception as e:
    raise ITerm2Error(f"Failed to detach session: {e}") from e

# connect_to_session (131-132行)
except Exception as e:
    raise ITerm2Error(f"Failed to connect to session: {e}") from e

# setup_hooks (175-176行)
except Exception as e:
    raise ITerm2Error(f"Failed to setup hooks: {e}") from e

# add_window (238-239行)
except Exception as e:
    raise ITerm2Error(f"Failed to add window: {e}") from e

# open_project_windows (339-340行)
except Exception as e:
    raise ITerm2Error(f"Failed to open project windows: {e}") from e
```

**問題点**:
- 同じパターンの例外ラップが5箇所
- メッセージのテンプレートは異なるため、完全な共通化は難しい

**改善案**:
デコレータまたはコンテキストマネージャーで処理:
```python
def wrap_iterm2_error(operation: str):
    """iTerm2操作をラップして例外を変換するデコレータ."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                raise ITerm2Error(f"Failed to {operation}: {e}") from e
        return wrapper
    return decorator

# 使用例
@wrap_iterm2_error("detach session")
async def detach_session(self, project_name: str) -> None:
    tmux_conn = await self.session_manager.get_tmux_connection(project_name)
    await tmux_conn.async_send_command("detach-client")
    await asyncio.sleep(0.5)
```

**期待される効果**:
- 例外ハンドリングの一貫性向上
- ただし、デコレータの複雑さとトレードオフ
- 実装優先度は低い

---

### 6. hook削除コマンド（重要度: 極小）

**場所**: `src/itmux/tmux/hook_manager.py`
**重複箇所**: 3箇所（remove_hooks メソッド内）

**重複パターン例**:
```python
# 70-72行
await tmux_conn.async_send_command(
    f"set-hook -u -t {project_name} after-new-window"
)
# 73-75行
await tmux_conn.async_send_command(
    f"set-hook -u -t {project_name} window-unlinked"
)
# 76-78行
await tmux_conn.async_send_command(
    f"set-hook -u -t {project_name} after-rename-window"
)
```

**問題点**:
- 同じパターンが3回繰り返されている

**改善案**:
```python
async def remove_hooks(self, tmux_conn: iterm2.TmuxConnection, project_name: str) -> None:
    """プロジェクトのtmuxセッションからhookを削除."""
    try:
        hook_names = ["after-new-window", "window-unlinked", "after-rename-window"]
        for hook_name in hook_names:
            await tmux_conn.async_send_command(
                f"set-hook -u -t {project_name} {hook_name}"
            )
    except Exception:
        pass
```

**期待される効果**:
- わずかなコード量削減（約3行）
- setup_hooksとの対称性向上
- ただし、改善効果は極めて小さい

---

## マジックナンバー・文字列リテラルの重複

### 7. ユーザー変数のキー名（重要度: 低）

**場所**: 複数ファイル
- `bridge.py`: "user.projectID", "user.window_name"
- `window_manager.py`: "user.projectID", "user.window_name"

**問題点**:
- 文字列リテラルが複数箇所に散在
- タイポのリスク

**改善案**:
定数として定義:
```python
# constants.py（新規作成）
# User variable keys
USER_VAR_PROJECT_ID = "user.projectID"
USER_VAR_WINDOW_NAME = "user.window_name"
```

**期待される効果**:
- タイポ防止
- キー名変更が容易
- ただし、使用箇所が少ないため優先度は低い

---

### 8. デフォルト値・タイムアウト値（重要度: 極小）

**場所**:
- `bridge.py`: asyncio.sleep(0.5), asyncio.sleep(1.0)
- `orchestrator.py`: "default" ウィンドウ名

**問題点**:
- マジックナンバーが直接記述されている
- 意味が不明確

**改善案**:
```python
# constants.py
# Wait times
WINDOW_CREATION_WAIT = 0.5  # seconds
TMUX_CONNECTION_WAIT = 1.0  # seconds

# Default values
DEFAULT_WINDOW_NAME = "default"
```

**期待される効果**:
- 意図の明確化
- 値の調整が容易
- ただし、使用箇所が少ないため優先度は極めて低い

---

## 優先度付き改善提案まとめ

### 優先度: 高（実施推奨）

1. **CLIコマンドのエラーハンドリング統一**
   - 改善効果: 大（約40行削減、保守性向上）
   - 実装コスト: 小
   - リスク: 低

### 優先度: 中（検討推奨）

2. **プロジェクト名の環境変数取得を共通化**
   - 改善効果: 中（約8行削減、ロジック一元化）
   - 実装コスト: 小
   - リスク: 低

3. **iTerm2ウィンドウのタグ付けを共通化**
   - 改善効果: 中（責務の明確化、保守性向上）
   - 実装コスト: 小
   - リスク: 低

### 優先度: 低（必要に応じて検討）

4. **tmuxコマンド結果のパース統一**
   - 改善効果: 小（約4行削減）
   - 実装コスト: 小
   - リスク: 低

5. **例外のラップ統一（デコレータ化）**
   - 改善効果: 中（一貫性向上）
   - 実装コスト: 中（デコレータ実装）
   - リスク: 中（可読性低下の可能性）

6. **hook削除コマンドのループ化**
   - 改善効果: 極小（約3行削減）
   - 実装コスト: 小
   - リスク: 低

7. **ユーザー変数キー名の定数化**
   - 改善効果: 小（タイポ防止）
   - 実装コスト: 小
   - リスク: 極小

8. **デフォルト値・タイムアウト値の定数化**
   - 改善効果: 極小（意図の明確化）
   - 実装コスト: 小
   - リスク: 極小

---

## 推奨実装順序

1. CLIコマンドのエラーハンドリング統一（最優先）
2. プロジェクト名の環境変数取得を共通化
3. iTerm2ウィンドウのタグ付けを共通化

上記3つを実施すると、約50行のコード削減と保守性の大幅な向上が期待できる。

---

## 発見されなかったDRY違反

以下の観点では、重大なDRY違反は発見されなかった：

- **マネージャークラス間の重複**: 各マネージャーは単一責任の原則に従っており、重複は最小限
- **モデル定義の重複**: Pydanticモデルは適切に分離されている
- **設定ファイル処理**: ConfigManagerに一元化されている

リファクタリング後のコードベースは概ね良好な状態である。

---

## 調査の制限事項

- テストコードは調査対象外
- config.pyは詳細調査未実施（今回の調査範囲外）
- 実行時パフォーマンスへの影響は未評価

---

## 結論

リファクタリング後のコードベースには、いくつかのDRY原則違反が存在するが、いずれも局所的で改善可能な範囲である。特にCLI層のエラーハンドリングとOrchestrator層の環境変数処理が最も改善効果が高い。

優先度「高」の3つの改善を実施することを推奨する。
