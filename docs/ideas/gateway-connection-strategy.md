# Gateway/Connection 管理戦略

**最終更新**: 2025-12-24
**ステータス**: 実装中（RecursionError対応が必要）

## 方針の確定

### 最新の方針：一つのgateway/connectionを維持して使い回す

**決定理由**：
- Window停止時の挙動が奇妙なため、都度作成方式を諦めた
- 複数プロジェクトを開く際のパフォーマンス向上
- gatewayウィンドウの表示/非表示の制御が安定する

### 以前の試行錯誤

1. **都度作成方式**：各セッションごとにgatewayを作成・破棄
   - ❌ Window停止時の挙動が不安定
   - ❌ パフォーマンスが悪い
   - ❌ gatewayウィンドウが何度も表示される

2. **永続化方式（現在）**：一つのgatewayを作成して使い回す
   - ✅ 一度作成したgatewayを複数セッションで共有
   - ✅ `~/.itmux/gateway.json`でconnection_idを永続化
   - ✅ パフォーマンスが良い

## 実装の概要

### アーキテクチャ

```
┌──────────────────────────────────────────┐
│ iTerm2                                   │
│                                          │
│  ┌────────────────┐                     │
│  │ Gateway Window │ (buried)            │
│  │ tmux -CC       │                     │
│  └────────┬───────┘                     │
│           │                              │
│           │ TmuxConnection               │
│           │                              │
│  ┌────────┴───────┐  ┌──────────────┐  │
│  │ Session Window │  │ Session Win  │  │
│  │ (test_session1)│  │ (session2)   │  │
│  └────────────────┘  └──────────────┘  │
└──────────────────────────────────────────┘
        │
        │ ~/.itmux/gateway.json
        └──────────────────────────────────
               {
                 "connection_id": "tmux",
                 "created_at": "2025-12-24..."
               }
```

### 主要API

#### 1. `get_or_create_gateway()`

```python
async def get_or_create_gateway(self) -> tuple[Optional[iterm2.Session], iterm2.TmuxConnection]:
    """既存gatewayを取得、なければ新規作成."""
    # 1. gateway.jsonから既存gateway情報を読む
    # 2. connection_idで既存TmuxConnectionを取得
    # 3. あれば再利用、なければ新規作成
    # 4. 新規作成時はgateway.jsonに保存
```

**特徴**：
- gateway.jsonでconnection_idを永続化
- 既存connectionがあれば再利用（健全性チェックなし）
- gatewayセッション自体は返さない（使わない）

#### 2. `open_project_sessions()`

```python
async def open_project_sessions(
    self,
    project_name: str,
    session_configs: list[SessionConfig],
) -> list[str]:
    """プロジェクトの全セッションを一つのgateway経由で開く."""
    # 1. Gateway取得/作成
    gateway_session, tmux_conn = await self.get_or_create_gateway()

    # 2. 各セッションを個別に開く
    for session_config in session_configs:
        if session_exists:
            window_id = await self.attach_single_session_via_gateway(...)
        else:
            window_id = await self.create_single_session_via_gateway(...)
```

**特徴**：
- 一つのgatewayで複数セッションを処理
- sessionベースからconnectionベースへの移行

#### 3. `attach_single_session_via_gateway()`

```python
async def attach_single_session_via_gateway(
    self,
    tmux_conn: iterm2.TmuxConnection,
    project_name: str,
    session_name: str,
    window_size: Optional[WindowSize] = None,
) -> str:
    """gateway経由で既存tmuxセッションに1つだけattach."""
    async with iterm2.NewSessionMonitor(self.connection) as monitor:
        await tmux_conn.async_send_command(f"attach-session -t {session_name}")
        new_session_id = await monitor.async_get()

    # Windowを取得してタグ付け
    app = await iterm2.async_get_app(self.connection)
    session = app.get_session_by_id(new_session_id)
    window, tab = app.get_window_and_tab_for_session(session)

    await window.async_set_variable("user.projectID", project_name)
    await window.async_set_variable("user.tmux_session", session_name)
```

**特徴**：
- TmuxConnection.async_send_command()を使用
- 個別のgateway作成・破棄が不要
- NewSessionMonitorでウィンドウ作成を監視

### iTerm2設定の前提条件

**必須設定**：`iTerm2 > Settings > General > tmux`
- ✅ `Automatically bury the tmux client session after connecting`

この設定により、tmux -CC接続時に作成されるgatewayウィンドウが自動的に非表示（buried）になります。

## 現在の問題

### RecursionError発生

**発生箇所**：`get_or_create_gateway()` > `Window.async_create()`

```python
gateway = await iterm2.Window.async_create(
    self.connection,
    command="/opt/homebrew/bin/tmux -CC new-session -A -s __gateway-connection"
)
```

**エラー内容**：
```
RecursionError: maximum recursion depth exceeded
at iterm2.app.async_refresh() > _async_handle_layout_change() > async_refresh_focus()
```

**原因**：
iTerm2 Python APIの既知の不安定性。tmux -CCとの統合時に`async_refresh()`が無限ループに陥る。

## 解決策の候補

### 案1：Window.async_create()を使わない

gateway作成を別の方法で行う：
- 手動でtmuxセッションを作成しておく
- 既存セッションへのアタッチのみを行う

### 案2：sessionベースに戻す

connectionベースを諦めて、元のsessionベースの実装に戻す：
- 各セッションごとにgatewayを作成
- `async_send_text()`でコマンド送信
- gatewayはクリーンアップ

### 案3：iTerm2 APIの別の使い方を探る

- `Window.async_create()`以外のgateway作成方法
- Python API以外のアプローチ（AppleScript等）

## 次のステップ

1. RecursionErrorの根本原因を特定
2. 解決策を選択・実装
3. 動作確認（E2Eテスト）
4. ドキュメント更新

## 参考資料

- [research.tmux-connection-redesign.v1.md](../../research.tmux-connection-redesign.v1.md) - 取り消された設計
- [iTerm2とtmux連携の表示改善.md](./iTerm2とtmux連携の表示改善.md) - 表示改善の調査
- [iTerm2 Python APIとtmux連携.md](./iTerm2%20Python%20APIとtmux連携.md) - API連携の詳細
