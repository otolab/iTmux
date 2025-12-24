# TmuxConnection再設計

> **⚠️ この設計は取り消されました (2025-12-19)**
>
> Gateway永続化による複雑さとiTerm2 API不安定性の問題により、この設計は採用されませんでした。
> 最終的に、iTerm2の「Automatically bury the tmux client session after connecting」設定に依存し、
> 都度実行（ad-hoc execution）方式を採用しました。
>
> 詳細は以下のコミット履歴を参照してください。

**作成日**: 2025-12-18
**目的**: TmuxConnectionアプローチの問題を解決し、安定した実装に改善する

## 問題の整理

### 現在の実装の問題点

1. **gatewayを隠す操作とTmuxConnection使い回しの干渉**
   - `gateway_session.async_set_buried(True)`でgatewayを隠している
   - しかしTmuxConnectionはgateway sessionを通じて通信する必要がある
   - buryすることでWebSocket接続が不安定になる可能性

2. **長時間waitループによるタイムアウト**
   - NewSessionMonitorで5秒×4セッション = 20秒以上の待機
   - WebSocket接続がタイムアウト（exit code 137）

3. **個別検証の困難さ**
   - `open_project_sessions()`が全てを一度に実行
   - 個別の機能（1セッション作成）を検証できない

## 新しい設計方針

### 1. Gatewayの扱い

**従来**: gatewayを作成→bury→すぐに不可視化
**新方針**: gatewayを堂々と開いておき、tmux control serverとして常駐させる

#### Gateway管理の仕組み

```python
# ~/.itmux/gateway.json に保存
{
  "gateway_session_id": "w0t0p0:ABC123...",
  "connection_id": "tmux-conn-xyz",
  "created_at": "2025-12-18T10:30:00"
}
```

#### Gateway取得/作成のロジック

```python
async def get_or_create_gateway(self) -> tuple[iterm2.Session, iterm2.TmuxConnection]:
    """既存gatewayを取得、なければ新規作成.

    Returns:
        tuple[iterm2.Session, iterm2.TmuxConnection]: (gateway session, tmux connection)
    """
    # 1. gateway.jsonから既存gateway情報を読む
    gateway_info = self._load_gateway_info()

    if gateway_info:
        # 2. session IDで既存gatewayを取得
        session = self.app.get_session_by_id(gateway_info["gateway_session_id"])

        if session and await session.async_is_alive():
            # 3. TmuxConnectionを取得
            tmux_conns = await iterm2.async_get_tmux_connections(self.connection)
            for conn in tmux_conns:
                if conn.connection_id == gateway_info["connection_id"]:
                    return session, conn

    # 4. 既存gatewayがない、または無効 → 新規作成
    gateway = await iterm2.Window.async_create(
        self.connection,
        command="/opt/homebrew/bin/tmux -CC"
    )
    gateway_session = gateway.current_tab.current_session

    # 5. TmuxConnection取得
    await asyncio.sleep(0.5)
    tmux_conns = await iterm2.async_get_tmux_connections(self.connection)
    tmux_conn = tmux_conns[-1]  # 最新の接続

    # 6. 情報を保存
    self._save_gateway_info({
        "gateway_session_id": gateway_session.session_id,
        "connection_id": tmux_conn.connection_id,
        "created_at": datetime.now().isoformat()
    })

    return gateway_session, tmux_conn
```

### 2. 最小単位のAPI設計

個別に検証可能な関数構成：

#### 2.1 Gateway管理API

```python
async def get_or_create_gateway(self) -> tuple[iterm2.Session, iterm2.TmuxConnection]:
    """既存gatewayを取得、なければ新規作成.

    Returns:
        tuple[iterm2.Session, iterm2.TmuxConnection]: (gateway session, tmux connection)
    """
    # 前述の実装
    pass

async def close_gateway(self) -> None:
    """Gatewayを明示的にクローズし、情報をクリア.

    全てのtmuxセッションがdetachされる点に注意
    """
    gateway_info = self._load_gateway_info()
    if gateway_info:
        session = self.app.get_session_by_id(gateway_info["gateway_session_id"])
        if session:
            window, tab = self.app.get_window_and_tab_for_session(session)
            if window:
                await window.async_close()

    self._clear_gateway_info()

async def get_gateway_status(self) -> Optional[dict]:
    """Gateway状態を確認.

    Returns:
        Optional[dict]: Gateway情報（alive=True/False付き）、なければNone
    """
    gateway_info = self._load_gateway_info()
    if not gateway_info:
        return None

    session = self.app.get_session_by_id(gateway_info["gateway_session_id"])
    is_alive = session and await session.async_is_alive()

    return {
        **gateway_info,
        "alive": is_alive
    }
```

#### 2.2 単一セッション操作

```python
async def attach_single_session_via_gateway(
    self,
    tmux_conn: iterm2.TmuxConnection,
    project_name: str,
    session_name: str,
) -> str:
    """gateway経由で既存tmuxセッションに1つだけattach.

    Args:
        tmux_conn: 使用するTmuxConnection
        project_name: プロジェクト名
        session_name: tmuxセッション名

    Returns:
        str: 作成されたウィンドウID
    """
    async with iterm2.NewSessionMonitor(self.connection) as monitor:
        # コマンド送信
        await tmux_conn.async_send_command(f"attach-session -t {session_name}")

        # セッション作成を待つ
        new_session_id = await asyncio.wait_for(
            monitor.async_get(), timeout=5.0
        )

    # Windowを取得してタグ付け
    await asyncio.sleep(2.0)
    app = await iterm2.async_get_app(self.connection)
    session = app.get_session_by_id(new_session_id)
    window, tab = app.get_window_and_tab_for_session(session)

    await window.async_set_variable("user.projectID", project_name)
    await window.async_set_variable("user.tmux_session", session_name)

    return window.window_id
```

```python
async def create_single_session_via_gateway(
    self,
    tmux_conn: iterm2.TmuxConnection,
    project_name: str,
    session_name: str,
) -> str:
    """gateway経由で新規tmuxセッションを1つだけ作成.

    (同様の実装、new-session -s を使用)
    """
    pass
```

#### 2.2 複数セッション一括操作

```python
async def open_project_sessions(
    self,
    project_name: str,
    session_configs: list[SessionConfig],
) -> list[str]:
    """プロジェクトの全セッションを開く.

    内部で get_or_create_gateway() と attach/create_single_session を使用
    """
    # 1. Gateway取得/作成
    gateway_session, tmux_conn = await self.get_or_create_gateway()

    # 2. 各セッションを個別に開く
    window_ids = []
    for session_config in session_configs:
        if self._tmux_has_session(session_config.name):
            window_id = await self.attach_single_session_via_gateway(
                tmux_conn, project_name, session_config.name
            )
        else:
            window_id = await self.create_single_session_via_gateway(
                tmux_conn, project_name, session_config.name
            )
        window_ids.append(window_id)

    return window_ids
```

### 3. Gateway永続化

#### 3.1 ファイル構造

```
~/.itmux/
├── config.json          # プロジェクト設定
└── gateway.json         # Gateway情報
```

#### 3.2 Gateway情報の管理

```python
def _load_gateway_info(self) -> Optional[dict]:
    """Gateway情報を読み込み."""
    gateway_path = Path.home() / ".itmux" / "gateway.json"
    if gateway_path.exists():
        return json.loads(gateway_path.read_text())
    return None

def _save_gateway_info(self, info: dict) -> None:
    """Gateway情報を保存."""
    gateway_path = Path.home() / ".itmux" / "gateway.json"
    gateway_path.write_text(json.dumps(info, indent=2))

def _clear_gateway_info(self) -> None:
    """Gateway情報をクリア."""
    gateway_path = Path.home() / ".itmux" / "gateway.json"
    if gateway_path.exists():
        gateway_path.unlink()
```

### 4. テスト戦略

#### 4.1 個別機能の検証

```python
# 0. Gateway状態確認
status = await bridge.get_gateway_status()
print(f"Gateway Status: {status}")

# 1. Gateway作成/取得のテスト
gateway_session, tmux_conn = await bridge.get_or_create_gateway()
print(f"Gateway Session ID: {gateway_session.session_id}")
print(f"TmuxConnection ID: {tmux_conn.connection_id}")

# 2. 単一セッション作成のテスト
window_id = await bridge.create_single_session_via_gateway(
    tmux_conn, "test-project", "test-session-1"
)
print(f"Created window: {window_id}")

# 3. 単一セッションattachのテスト
window_id = await bridge.attach_single_session_via_gateway(
    tmux_conn, "test-project", "test-session-1"
)
print(f"Attached window: {window_id}")
```

#### 4.2 統合テスト

```python
# 複数セッション一括開放
window_ids = await bridge.open_project_sessions(
    "test-project",
    [
        SessionConfig(name="test-session-1"),
        SessionConfig(name="test-session-2"),
        SessionConfig(name="test-session-3"),
    ]
)
```

## 期待される改善

1. **安定性**: gatewayをburyしないことで、WebSocket接続が安定
2. **効率**: gateway再利用により、複数回の操作でも高速
3. **検証性**: 最小単位のAPIで個別に機能を検証可能
4. **保守性**: gateway管理が明確で、問題の切り分けが容易

## 実装手順

1. `_load_gateway_info()`, `_save_gateway_info()`, `_clear_gateway_info()` を実装
2. `get_or_create_gateway()` を実装
3. `attach_single_session_via_gateway()` を実装
4. `create_single_session_via_gateway()` を実装
5. `open_project_sessions()` を上記を使って書き直し
6. 個別に各関数をテスト
7. 統合テスト

## iTerm2設定情報（2025-12-18調査）

### 利用可能な設定

**Preferences > General > tmux**:
- `Automatically bury the tmux client session after connecting` - 存在確認
  - このオプションをONにすると、tmux -CC接続後に自動的にgatewayセッションがburyされる

**見つからなかった設定**:
- `Open tmux windows as native tabs in a new window` - バージョンによっては存在しない可能性
  - 古いドキュメントには記載があるが、現在のiTerm2では削除または名称変更された可能性

## 注意事項

- Gateway windowは通常のウィンドウとして表示される（不可視化しない）
- Gateway windowを誤って閉じると、全てのtmuxセッションがdetachされる
- Gateway情報ファイルは手動削除も可能（次回起動時に再作成）
- tmux -CCを実行すると、デフォルトでtmuxが自動的に番号セッション（0など）を作成する
