# iterm2 Window/Session Creation API調査レポート

**調査日**: 2025-12-18
**対象**: iTerm2 Python API v2.13
**目的**: `WindowCreationMonitor`非存在問題の解決策を特定

## 問題の概要

`src/itmux/iterm2_bridge.py:171`で使用している`iterm2.WindowCreationMonitor`がiterm2 v2.13に存在しない。

### 現在の実装（動作しない）

```python
async with iterm2.WindowCreationMonitor(self.connection) as monitor:  # ← 存在しない
    session = gateway.current_tab.current_session
    cmd = f"tmux -CC new-session -s {session_name}\n"
    await session.async_send_text(cmd)
    new_window_id = await asyncio.wait_for(monitor.async_get(), timeout=5.0)
```

## 調査結果

### 1. 利用可能なMonitorクラス（iterm2 v2.13）

- `NewSessionMonitor` ← **使用可能**
- `LayoutChangeMonitor`
- `FocusMonitor`
- `KeystrokeMonitor`
- `PromptMonitor`
- `SessionTerminationMonitor`
- `CustomControlSequenceMonitor`
- `EachSessionOnceMonitor`
- `VariableMonitor`

**結論**: `WindowCreationMonitor`は存在しないが、`NewSessionMonitor`が代替として使用可能。

### 2. NewSessionMonitor API仕様

**参照**: [Life Cycle — iTerm2 Python API](https://iterm2.com/python-api/lifecycle.html)

#### 基本的な使い方

```python
async with iterm2.NewSessionMonitor(connection) as mon:
    while True:
        session_id = await mon.async_get()
        print(f"Session ID {session_id} created")
```

#### Session IDからWindowオブジェクトを取得

```python
async with iterm2.NewSessionMonitor(connection) as mon:
    session_id = await mon.async_get()
    app = await iterm2.async_get_app(connection)
    window = await app.async_get_window_containing_session(session_id)
    session = await app.async_get_session_by_id(session_id)
```

**重要メソッド**:
- `async_get()`: 新しいセッションのIDを返す
- `app.async_get_window_containing_session(session_id)`: セッションを含むウィンドウを取得
- `app.async_get_session_by_id(session_id)`: SessionオブジェクトをIDから取得

### 3. tmux Control Mode API仕様

**参照**:
- [Tmux Integration — iTerm2 Python API](https://iterm2.com/python-api/examples/tmux.html)
- [Tmux — iTerm2 Python API](https://iterm2.com/python-api/tmux.html)

#### tmux Control Modeの仕組み

1. `tmux -CC` コマンドで"gateway session"を作成
2. このgateway sessionを通じてtmuxサーバーとやり取り
3. tmux windowはiTerm2のtabとして表示される

#### 利用可能なAPI

```python
# tmux接続の取得
tmux_conns = await iterm2.async_get_tmux_connections(connection)
tmux_conn = tmux_conns[0]  # 最初の接続を使用

# 新しいwindowを作成
window = await tmux_conn.async_create_window()

# 新しいtabを作成
tab2 = await window.async_create_tmux_tab(tmux_conn)

# tmuxサーバーに直接コマンド送信
await tmux_conn.async_send_command("new-session -s mysession")
```

**重要なプロパティ**:
- `tmux_conn.connection_id`: tmux接続のユニークID
- `tmux_conn.owning_session`: `tmux -CC`が実行されたgateway session

**制約**:
- これらのメソッドは`Transaction`内から呼び出せない

## 代替実装案

### 推奨: NewSessionMonitor を使用

```python
async def add_session(
    self,
    project_name: str,
    session_name: str,
) -> str:
    """新規tmuxセッションを作成し、プロジェクトに追加.

    Args:
        project_name: プロジェクト名
        session_name: tmuxセッション名

    Returns:
        str: 作成されたウィンドウID

    Raises:
        WindowCreationTimeoutError: セッション作成がタイムアウト
        ITerm2Error: その他のiTerm2 APIエラー
    """
    try:
        # 1. ゲートウェイウィンドウを取得
        gateway = self.app.current_terminal_window

        # 2. NewSessionMonitorで新セッション監視開始
        async with iterm2.NewSessionMonitor(self.connection) as monitor:
            # 3. tmux -CC new-session コマンド送信
            session = gateway.current_tab.current_session
            cmd = f"tmux -CC new-session -s {session_name}\n"
            await session.async_send_text(cmd)

            # 4. 新セッション作成を待つ（タイムアウト5秒）
            try:
                new_session_id = await asyncio.wait_for(
                    monitor.async_get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                raise WindowCreationTimeoutError(
                    f"Session creation timed out for: {session_name}"
                )

        # 5. セッションIDからWindowを取得
        window = await self.app.async_get_window_containing_session(new_session_id)
        new_window_id = window.window_id

        # 6. 新ウィンドウにタグ付け
        await window.async_set_variable("user.projectID", project_name)
        await window.async_set_variable("user.tmux_session", session_name)

        # 7. ゲートウェイクリーンアップ
        try:
            await gateway.async_close()
        except Exception:
            # クリーンアップ失敗は無視（ベストエフォート）
            pass

        return new_window_id

    except WindowCreationTimeoutError:
        raise
    except Exception as e:
        raise ITerm2Error(f"Failed to add session: {e}") from e
```

### 主な変更点

1. **`WindowCreationMonitor` → `NewSessionMonitor`**
   - ウィンドウではなくセッション作成を監視

2. **Window取得方法の追加**
   ```python
   window = await self.app.async_get_window_containing_session(new_session_id)
   new_window_id = window.window_id
   ```

3. **エラーメッセージの更新**
   - "Window creation" → "Session creation"

## 実装時の注意点

### 1. タイミングの問題

`tmux -CC new-session`を実行すると、以下の順序でイベントが発生：
1. 新しいセッションが作成される
2. `NewSessionMonitor`が発火
3. 新しいウィンドウが作成される

`NewSessionMonitor`はウィンドウ作成前に発火する可能性があるため、`async_get_window_containing_session()`で適切に待機する必要がある。

### 2. エラーハンドリング

- `async_get_window_containing_session()`がNoneを返す可能性を考慮
- ネットワーク遅延やiTerm2の応答遅延を考慮したタイムアウト設定

### 3. テスト戦略

- Unit Tests: モックで`NewSessionMonitor`の動作を検証
- E2E Tests: 実際のiTerm2環境で動作確認（Issue #5で実装済み）

## 参考資料

- [NewSessionMonitor — Life Cycle Documentation](https://iterm2.com/python-api/lifecycle.html)
- [Tmux Integration — iTerm2 Python API](https://iterm2.com/python-api/examples/tmux.html)
- [Tmux API Reference](https://iterm2.com/python-api/tmux.html)
- [Example Scripts](https://iterm2.com/python-api/examples/index.html)
- [iterm2 · PyPI](https://pypi.org/project/iterm2/)

## 次のステップ

1. `src/itmux/iterm2_bridge.py`の`add_session()`を修正
2. Unit Testsを更新（モックの変更）
3. E2Eテストで動作確認
4. Issue #6をクローズ
