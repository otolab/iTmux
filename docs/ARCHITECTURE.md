# iTmux アーキテクチャ

## システム概要

iTmuxは、iTerm2のPython APIとtmuxのControl Mode（`-CC`）を統合し、既存のtmuxセッション群を「プロジェクト」として一括管理するツールです。

### 核心概念

**1プロジェクト = 1 tmuxセッション = 複数のtmuxウィンドウ**

- プロジェクト: ユーザーが定義する論理的なグループ（例: "my-project"）
- tmuxセッション: プロジェクトと1:1で対応（セッション名 = プロジェクト名）
- tmuxウィンドウ: セッション内の作業環境（1ウィンドウ = iTerm2の1ウィンドウ）
- ユーザー変数: iTerm2ウィンドウに付与されるメタデータ（`user.projectID`）

### 前提条件

#### tmux環境変数の設定（Homebrew使用時）

**macOSでHomebrewを使用してtmuxをインストールしている場合**、iTmuxのhook機能が動作するには、tmuxのグローバル環境変数`PATH`を設定することをおすすめします。

**`~/.tmux.conf`に追加（TPM初期化の後）：**
```tmux
# --- TPMの初期化 ---
run '~/.tmux/plugins/tpm/tpm'

# --- iTmux: hookからtmuxコマンドを実行するため ---
set-environment -g PATH "/opt/homebrew/bin:$PATH"
```

**技術的背景：**

1. **hookの実行環境**: tmuxの`run-shell -b`は**非ログインシェル**で起動される
2. **PATH問題**: 非ログインシェルはシェル初期化ファイル（`.zprofile`、`.bash_profile`等）を読み込まない
3. **結果**: `tmux show-environment -g PATH`が返すのはシステムデフォルトのPATHのみ（`/usr/bin:/bin:/usr/sbin:/sbin`）
4. **解決策**: tmuxのグローバル環境変数として明示的にPATHを設定する
5. **順序の重要性**: TPM初期化より後に設定することで、tmux起動時の問題を回避

この設定により、hookから実行される`itmux sync/save`がtmuxコマンドを正しく見つけられるようになります。

**注意**: システム標準のtmuxを使用している場合、この設定は不要です。

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

**基本方針：差分のみを開く（冪等性）**

```
1. ユーザー入力
   $ itmux open my-project

2. 設定読み込み
   ~/.itmux/config.json
   → tmux_windows: [
       {name: "editor", window_size: {...}},
       {name: "server", window_size: {...}},
       {name: "logs"}
     ]

3. 既存のiTerm2ウィンドウを検索（差分検出）
   existing_windows = find_windows_by_project("my-project")
   existing_window_names = set()

   for window in existing_windows:
     window_name = await window.async_get_variable("user.window_name")
     existing_window_names.add(window_name)

   # 例: ["editor", "server"] が既に開いている

4. まだ開かれていないwindowだけを開く
   windows_to_open = [
     w for w in tmux_windows
     if w.name not in existing_window_names
   ]

   # 例: ["logs"] だけを開く

5. セッションに接続してウィンドウを開く
   if windows_to_open:
     a. tmux -CC で接続
        tmux -CC new-session -A -s my-project -n logs

     b. TmuxConnection取得
        tmux_conn = get_tmux_connection("my-project")

     c. 各ウィンドウを作成/タグ付け
        for each window in windows_to_open:
          - 既存ウィンドウならタグ付けのみ
          - 新規ウィンドウなら作成してタグ付け
          - user.projectID = "my-project" 設定
          - user.window_name = "<window_name>" 設定

6. hookを設定（自動同期を有効化）
   await bridge.setup_hooks(project_name)

   - セッションスコープのhook（after-new-window等）: 上書き
   - グローバルのsession-closed: 上書き
   - 何回openしても多重登録されない（冪等性）

7. 完了
   → iTerm2に必要なウィンドウだけが開く
   → 既に開いているウィンドウはそのまま
   → 各ウィンドウに user.projectID, user.window_name タグ
   → tmux hookによる自動同期が有効化
   → tmux session内では session名からプロジェクト名を自動検出
```

### Close操作（自動同期）

**基本方針：開いているウィンドウだけを閉じる**

```
1. ユーザー入力
   $ itmux close [project]
   # project省略時はtmux session名から自動検出

2. プロジェクトのiTerm2ウィンドウを検索
   windows = find_windows_by_project("my-project")

3. ウィンドウが見つからなければ終了
   if not windows:
     return  # 何もしない

4. 同期（tmuxからconfig.jsonへ）
   tmux_windows = tmux list-windows -t my-project -F '#{window_name}'
   config.update_project("my-project", tmux_windows)

5. セッション全体をdetach
   # 1つのウィンドウをアクティブにしてDetachすれば全ウィンドウが閉じる
   windows[0].async_activate()
   await MainMenu.async_select_menu_item(connection, "tmux.Detach")

6. 完了
   → iTerm2ウィンドウは全て閉じる
   → tmuxセッションはバックグラウンド継続
   → config.jsonは現在の状態を反映
```

### Add操作（ウィンドウ追加）

```
1. ユーザー入力
   $ itmux add [project] [window-name]
   # project省略時はtmux session名から自動検出
   # window-name省略時は自動生成（例: window-1, window-2）

2. ウィンドウ名決定
   if window-name 指定あり:
     use window-name
   else:
     window-name = generate_window_name(project)
     # 例: my-project-1, my-project-2, ...

3. TmuxConnection取得
   tmux_conn = get_tmux_connection(project)

4. 新しいtmuxウィンドウを作成
   iterm_window = await tmux_conn.async_create_window()
   await tmux_conn.async_send_command(f"rename-window {window-name}")

5. iTerm2ウィンドウにタグ付け
   await iterm_window.async_set_variable("user.projectID", project)
   await iterm_window.async_set_variable("user.window_name", window-name)

6. 完了（自動同期）
   → 新しいiTerm2ウィンドウが開く
   → tmux hookが発火してconfig.jsonに自動追加される
```

### Sync操作（tmux → config.json）

**基本方針：tmuxの状態が正。iTerm2 windowには触らない**

```
1. 実行契機
   - ユーザーが直接実行: $ itmux sync [project]
   - ユーザーが全体同期: $ itmux sync --all
   - tmux hookから自動実行:
     * after-new-window: ウィンドウ作成時 → itmux sync {project}
     * window-unlinked: ウィンドウ削除時 → itmux sync {project}
     * after-rename-window: ウィンドウ名変更時 → itmux sync {project}
     * session-closed: セッション終了時 → itmux sync --all

2. sync --all の場合（全プロジェクトチェック）
   for project_name in config.list_projects():
     if not tmux has-session -t project_name:
       config.delete_project(project_name)
   return

3. プロジェクト名決定（単一プロジェクト同期の場合）
   project_name = 引数 or tmux session名

4. tmuxセッション存在確認
   if not tmux has-session -t project_name:
     # セッション終了 → プロジェクトを削除
     config.delete_project(project_name)
     return

5. tmuxからウィンドウリスト取得（iTerm2 API不使用）
   result = tmux list-windows -t project_name -F '#{window_name}'
   windows = parse(result)
   # 例: ["editor", "server", "logs"]

6. config.jsonに保存
   config.update_project(project_name, windows)

7. tmux-resurrect保存（オプション）
   if ~/.tmux/plugins/tmux-resurrect/scripts/save.sh exists:
     # tmuxセッションの状態を保存（プロセス、ペイン、ディレクトリ等）
     run save.sh
   # tmux-continuumの代替として自動保存を実現

8. 完了
   → config.jsonがtmuxの現在状態を反映
   → iTerm2 windowには一切触らない
   → tmux-resurrectによるセッション状態も保存
```

**重要な設計判断：**
- syncはtmuxコマンドで直接情報を取得する（iTerm2 TmuxConnection不要）
- これにより、tmux hookから呼ばれた時も動作する
- 新しいiTerm2 Connectionコンテキストでも問題なく動作

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

## コマンド体系

### 基本コマンド

```bash
# ヘルプ表示
itmux
itmux --help

# プロジェクト一覧
itmux list
```

### プロジェクト操作

```bash
# プロジェクトを開く
itmux open <project>
# → tmux session名が <project> になる
# → config.jsonのセッションを一括アタッチ

# プロジェクトを閉じる
itmux close [project]
# → project省略時はtmux session名から自動検出
# → 現在の状態を自動保存（ウィンドウサイズ、セッションリスト）

# 現在のプロジェクト名を確認
itmux current
# → tmux session名を表示
```

### セッション追加

```bash
# パターン1: プロジェクトとセッション名を指定
itmux add <project> <session-name>
# → 指定プロジェクトに、指定名のセッション追加
# → config.json更新

# パターン2: プロジェクト指定、セッション名は自動生成
itmux add <project>
# → セッション名は自動生成（例: project-1, project-2）

# パターン3: tmux session内で実行（自動検出）
itmux add
# → tmux session名からプロジェクト名を自動検出
# → tmux外で実行時はエラー
```

### プロジェクト名の自動検出

```bash
# tmux session内では、session名からプロジェクト名を自動検出
$ itmux open webapp
# → tmux session名が "webapp" になる

# tmux session内で実行
$ itmux current
# → webapp

$ itmux add           # webappに追加
$ itmux close         # webappを閉じる
```

## データ構造

### 設定ファイル（`~/.itmux/config.json`）

```json
{
  "projects": {
    "my-project": {
      "tmux_windows": [
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

- tmuxウィンドウ1つ → iTerm2ネイティブウィンドウ1つ
- tmuxセッション1つ → 複数のiTerm2ウィンドウ（ウィンドウ数に応じて）
- tmux pane → iTerm2ウィンドウ内でテキストベース分割表示
- ウィンドウを閉じても、tmuxセッションは永続化

### ウィンドウを閉じる時の挙動

iTerm2のtmux統合では、×ボタンでウィンドウを閉じる時に以下の2択が提供されます：

**1. Kill（推奨）**
- 対象のtmux windowを削除
- 他のiTerm2ウィンドウは残る
- `window-unlinked` hookが発火して自動的にconfig.jsonから削除される
- **iTmuxではこちらを推奨**

**2. Detach**
- セッション全体をdetach（**全てのiTerm2ウィンドウが閉じる**）
- tmuxセッションはバックグラウンドで継続
- `itmux open`で再度全ウィンドウを復元可能

**重要な制限**：
iTerm2のtmux統合には「個別ウィンドウのdetach」という概念がありません。
- 個別操作 → Kill（tmux windowを削除）
- 全体操作 → Detach（session全体をdetach）

この制限により、「iTerm2ウィンドウだけ閉じて、tmux windowは残したまま他のウィンドウも残す」という操作はできません。

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

## tmux Hook管理

### 概要

tmuxのhook機能を使って、ウィンドウの作成・削除・名前変更を自動的にconfig.jsonに同期します。

### Hook設定の仕様

**重要な特性：**
- hookはtmux sessionに設定される（TmuxConnection = session）
- sessionが存在する限りhookは永続化される
- `set-hook`（-aなし）は上書き、`set-hook -a`は追加
- openのたびに設定しても上書きされるため多重登録されない（冪等性）

**設定されるhook：**

```python
# セッションスコープのhook（-aなしで上書き）
set-hook -t {project_name} after-new-window "run-shell -b '{itmux_command} sync {project_name}'"
set-hook -t {project_name} window-unlinked "run-shell -b '{itmux_command} sync {project_name}'"
set-hook -t {project_name} after-rename-window "run-shell -b '{itmux_command} sync {project_name}'"

# グローバルスコープのhook（-gで上書き、-agではない）
set-hook -g session-closed "run-shell -b '{itmux_command} sync --all'"
```

**sync --allの動作：**
```python
# 全プロジェクトをチェックして、セッションが存在しないものを削除
for project_name in config.list_projects():
    if not tmux_has_session(project_name):
        config.delete_project(project_name)
```

### 冪等性の確保

`open`のたびにhookを設定：

```python
# hookを設定（上書きされるため削除不要）
await bridge.setup_hooks(project_name, itmux_command)
```

これにより：
- セッションスコープのhook（`set-hook -t`）: 上書きされる
- グローバルのhook（`set-hook -g`）: 上書きされる
- 何回`open`しても、hookが重複しない（冪等性）
- 事前の削除（remove_hooks）は不要

### バックグラウンド実行

`run-shell -b` フラグでデッドロック防止：

```bash
run-shell -b '{command}'  # バックグラウンド実行
```

`-b`なしの場合：
- hookが同期的に実行される
- `itmux sync`がTmuxConnectionを取得しようとする
- 元の操作もTmuxConnectionを使用中
- デッドロック発生

### Hook削除

`close`時にセッションスコープのhookを削除：

```python
set-hook -u -t {project_name} after-new-window
set-hook -u -t {project_name} window-unlinked
set-hook -u -t {project_name} after-rename-window
# session-closedはグローバルなので削除しない
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

## tmux-resurrect統合

### 概要

iTmuxは[tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect)と統合して、tmuxセッションの永続化を実現します。

### 問題: tmux-continuumの非互換性

tmux-continuumの自動保存機能は、iTerm2のControl Mode（-CC）では動作しません。

- **原因**: tmux-continuumはControl Modeクライアントを正しく検出できない
- **参考**: [tmux-continuum issue #40](https://github.com/tmux-plugins/tmux-continuum/issues/40)
- **メンテナーの回答**: "a good chance it won't work"

### 解決策: sync時の自動保存

iTmuxは、sync操作時にtmux-resurrectの保存スクリプトを直接実行します。

```python
def _save_tmux_resurrect(self) -> None:
    """tmux-resurrectで状態を保存."""
    save_script = Path.home() / ".tmux" / "plugins" / "tmux-resurrect" / "scripts" / "save.sh"

    if save_script.exists():
        subprocess.run([str(save_script)], timeout=5)
```

### 自動保存のタイミング

sync操作は以下のタイミングで実行されるため、自動的に保存されます：

- **ウィンドウ作成**: `after-new-window` hook → `itmux sync` → resurrect保存
- **ウィンドウ削除**: `window-unlinked` hook → `itmux sync` → resurrect保存
- **ウィンドウ名変更**: `after-rename-window` hook → `itmux sync` → resurrect保存
- **プロジェクトを閉じる**: `itmux close` → `sync` → resurrect保存

これにより、tmux-continuumの5分間隔より**頻繁**に保存されます。

### 保存される内容

tmux-resurrectにより以下が保存されます：

- **実行中のプロセス**（vim、npm run devなど）
- **ペイン分割**の状態
- **カレントディレクトリ**（各ペイン）
- **ウィンドウ配置**

iTmuxのconfig.jsonとは独立して動作します：

| 保存場所 | 保存内容 | 用途 |
|---------|---------|------|
| config.json | ウィンドウ名リスト、ウィンドウサイズ | iTmux独自のプロジェクト管理 |
| resurrect/*.txt | プロセス、ペイン、ディレクトリ | tmuxセッション状態の完全復元 |

### 復元フロー

1. システム再起動後、tmux起動
2. tmux-resurrectで復元（`prefix + Ctrl-r`）
3. `itmux open <project>`でiTerm2ウィンドウを開く

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
