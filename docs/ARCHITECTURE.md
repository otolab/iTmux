# iTmux アーキテクチャ

## システム概要

iTmuxは、iTerm2のPython APIとtmuxのControl Mode（`-CC`）を統合し、既存のtmuxセッション群を「プロジェクト」として一括管理するツールです。

### 核心概念

**1プロジェクト = 複数のtmuxセッション**

- プロジェクト: ユーザーが定義する論理的なグループ（例: "my-project"）
- tmuxセッション: 独立した作業環境（1セッション = iTerm2の1ウィンドウ）
- ユーザー変数: iTerm2ウィンドウに付与されるメタデータ（`user.projectID`）

## システムアーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│                    iTerm2 Application                    │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
│  │ Window 1  │  │ Window 2  │  │ Window 3  │           │
│  │ (my_edit) │  │ (my_serv) │  │ (my_logs) │           │
│  │           │  │           │  │           │           │
│  │ user.     │  │ user.     │  │ user.     │           │
│  │ projectID │  │ projectID │  │ projectID │           │
│  │ ="my-    │  │ ="my-    │  │ ="my-    │           │
│  │  project" │  │  project" │  │  project" │           │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘           │
│        │              │              │                  │
└────────┼──────────────┼──────────────┼──────────────────┘
         │              │              │
         │ tmux -CC     │ tmux -CC     │ tmux -CC
         │              │              │
┌────────▼──────────────▼──────────────▼──────────────────┐
│              tmux Server (localhost)                     │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
│  │ Session   │  │ Session   │  │ Session   │           │
│  │ my_editor │  │ my_server │  │ my_logs   │           │
│  │           │  │           │  │           │           │
│  │ nvim .    │  │ npm run   │  │ tail -f   │           │
│  │           │  │ dev       │  │ app.log   │           │
│  └───────────┘  └───────────┘  └───────────┘           │
└──────────────────────────────────────────────────────────┘
         ▲              ▲              ▲
         └──────────────┴──────────────┘
                iTmux Orchestrator
              (Python + iterm2 API)
```

## データフロー

### Open操作

```
1. ユーザー入力
   $ itmux open my-project

2. 設定読み込み
   ~/.itmux/config.json
   → sessions: [my_editor, my_server, my_logs]

3. 各セッションに対して処理
   for each session:
     a. tmuxセッション存在確認
        tmux has-session -t <session_name>

     b. iTerm2ウィンドウ作成（ゲートウェイ）
        iterm2.Window.async_create()

     c. tmux -CC 起動
        tmux -CC attach-session -t <session_name>

     d. WindowCreationMonitor で新ウィンドウ監視
        → user.projectID = "my-project" タグ付け
        → user.tmux_session = "<session_name>" タグ付け

     e. ウィンドウサイズ復元
        tmux resize-window -t <session> -x <cols> -y <lines>

     f. ゲートウェイウィンドウクリーンアップ
        gateway_window.async_close()

4. 完了
   → iTerm2に3つのウィンドウが開く
   → 各ウィンドウに user.projectID タグ
```

### Close操作

```
1. ユーザー入力
   $ itmux close my-project

2. プロジェクトに属するウィンドウ検索
   for window in app.windows:
     if window.user.projectID == "my-project":
       target_windows.append(window)

3. （オプション）現在のウィンドウサイズ保存
   for window in target_windows:
     size = get_window_size(window)
     update_config(session_name, size)

4. 各ウィンドウをデタッチ
   for window in target_windows:
     window.async_activate()
     app.async_select_menu_item("tmux.Detach")
     await sleep(0.5)

5. 完了
   → iTerm2ウィンドウは閉じる
   → tmuxセッションはバックグラウンド継続
```

## コンポーネント構成

```
src/itmux/
├── cli.py              # CLIエントリポイント
├── config.py           # 設定管理
├── orchestrator.py     # コアロジック
├── iterm2_bridge.py    # iTerm2 API連携
└── models.py           # データモデル
```

### 各コンポーネントの役割

#### `cli.py`
- Clickベースのコマンドラインインターフェース
- `open`, `close`, `list` コマンドの定義
- orchestratorへの処理委譲

#### `config.py`
- `~/.itmux/config.json` の読み込み/保存
- JSON ↔ Pythonデータクラスのマッピング
- プロジェクト/セッション設定の取得

#### `orchestrator.py`
- プロジェクトのopen/close/listロジック
- iTerm2ブリッジとの連携
- WindowCreationMonitorによる動的タグ付け
- ウィンドウサイズ復元処理

#### `iterm2_bridge.py`
- iTerm2 Python APIの非同期呼び出しラッパー
- RPC通信のエラーハンドリング
- ウィンドウ/セッション操作の抽象化

#### `models.py`
- データクラス定義
  - `ProjectConfig`
  - `SessionConfig`
  - `WindowSize`

## データ構造

### 設定ファイル（`~/.itmux/config.json`）

```json
{
  "projects": {
    "my-project": {
      "tmux_sessions": [
        {
          "name": "my_editor",
          "window_size": {
            "columns": 200,
            "lines": 60
          }
        },
        {
          "name": "my_server",
          "window_size": {
            "columns": 120,
            "lines": 40
          }
        }
      ]
    }
  }
}
```

### Pythonデータモデル

```python
@dataclass
class WindowSize:
    columns: int
    lines: int

@dataclass
class SessionConfig:
    name: str
    window_size: Optional[WindowSize] = None

@dataclass
class ProjectConfig:
    name: str
    sessions: list[SessionConfig]
```

## iTerm2 Python API統合

### 主要クラス

- **`iterm2.App`**: アプリケーション全体（シングルトン）
- **`iterm2.Window`**: OSレベルのウィンドウ
- **`iterm2.Session`**: ペイン（シェルが動作）
- **`iterm2.TmuxConnection`**: tmux -CC接続
- **`iterm2.WindowCreationMonitor`**: ウィンドウ生成イベント監視

### ユーザー定義変数

iTerm2ウィンドウに付与するメタデータ：

| 変数名 | 用途 | 例 |
|--------|------|-----|
| `user.projectID` | プロジェクト識別子 | `"my-project"` |
| `user.tmux_session` | tmuxセッション名 | `"my_editor"` |
| `user.managed` | iTmux管理フラグ | `"true"` |

### 非同期処理パターン

```python
async def main(connection):
    app = await iterm2.async_get_app(connection)

    # WindowCreationMonitorパターン
    async with iterm2.WindowCreationMonitor(connection) as monitor:
        # tmuxコマンド送信
        await gateway_session.async_send_text(command)

        # 新規ウィンドウの出現を待つ
        window_id = await asyncio.wait_for(
            monitor.async_get(),
            timeout=5.0
        )

        # ウィンドウにタグ付け
        window = app.get_window_by_id(window_id)
        await window.async_set_variable("user.projectID", project_name)
```

## tmux Control Mode（-CC）

### 特性

- tmuxセッション1つ → iTerm2ネイティブウィンドウ1つ
- ウィンドウを閉じても、tmuxセッションは永続化
- デタッチ = iTerm2ウィンドウだけ閉じる（セッション保持）
- Kill = セッションごと終了（状態破棄）

### 主要コマンド

```bash
# 新規作成またはアタッチ（冪等性）
tmux -CC new-session -A -s <session_name>

# アタッチのみ
tmux -CC attach-session -t <session_name>

# セッション存在確認
tmux has-session -t <session_name>

# ウィンドウサイズ変更
tmux resize-window -t <session_name> -x <columns> -y <lines>
```

### デタッチ方法

iTerm2メニュー項目をプログラム実行：
```python
await app.async_select_menu_item("tmux.Detach")
```

## エラーハンドリング

### タイムアウト対策

```python
try:
    window_id = await asyncio.wait_for(
        monitor.async_get(),
        timeout=5.0
    )
except asyncio.TimeoutError:
    # ウィンドウ生成タイムアウト
    logger.warning("Window creation timeout")
```

### RPC例外処理

```python
try:
    await window.async_set_variable("user.projectID", name)
except iterm2.RPCException as e:
    logger.error(f"Failed to set variable: {e}")
```

## パフォーマンス考慮

### 並列処理

複数セッションの処理は順次実行（tmux -CCの制約）：
```python
# セッションごとに逐次処理
for session in sessions:
    await attach_session(session)
```

### 変数取得の最適化

大量のウィンドウがある場合、並列化：
```python
# 並列で変数取得
tasks = [
    window.async_get_variable("user.projectID")
    for window in app.windows
]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

## セキュリティ

- 設定ファイル: `~/.itmux/config.json` (ユーザーホームディレクトリ)
- パーミッション: 644（読み取り可能）
- 機密情報: 設定ファイルには含めない（tmuxセッション名のみ）

## 将来の拡張

### Phase 2以降で検討

- プロファイル切り替え（背景色など）
- ウィンドウ位置の記憶・復元
- セッション自動作成機能（tmuxinator的）
- リモートtmux対応（SSH経由）
- 複数tmuxサーバー対応
