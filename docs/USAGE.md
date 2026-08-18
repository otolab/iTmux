# iTmux 使い方ガイド

iTmuxは、iTerm2とtmuxを組み合わせて、プロジェクト単位でターミナルウィンドウを一括管理するツールです。

## 目次

- [セットアップ](#セットアップ)
  - [iTerm2の推奨設定](#iterm2の推奨設定)
  - [tmux-resurrect統合](#tmux-resurrect統合)
- [基本概念](#基本概念)
- [基本的な使い方](#基本的な使い方)
- [プロジェクト設定の変更（config）](#プロジェクト設定の変更config)
- [プロジェクト定義](#プロジェクト定義)
- [実践例](#実践例)
- [トラブルシューティング](#トラブルシューティング)

## セットアップ

### 前提条件

- macOS
- iTerm2（Build 3.3+）
- tmux（2.6+）
- Python 3.12+

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/otolab/iTmux.git
cd iTmux

# 依存関係をインストール
uv sync

# スクリプトにパスを通す（オプション）
export PATH="$PATH:$(pwd)/scripts"
```

### iTerm2 Python APIの有効化

1. iTerm2を起動
2. メニュー: **iTerm2 > Preferences > General > Magic**
3. **Enable Python API** にチェック

### おすすめのtmux設定（Homebrew使用時）

**macOSでHomebrewを使用してtmuxをインストールしている場合**、iTmuxのhook機能（自動同期・自動保存）を動作させるため、`~/.tmux.conf`に以下の設定を追加することをおすすめします：

```tmux
# --- プラグイン設定 ---
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'tmux-plugins/tmux-resurrect'
# ... 他のプラグイン設定 ...

# --- TPMの初期化（必ず末尾に記述） ---
run '~/.tmux/plugins/tpm/tpm'

# --- iTmux: hookからtmuxコマンドを実行するため、Homebrewのパスを追加 ---
# 重要: TPM初期化の後に書くこと
set-environment -g PATH "/opt/homebrew/bin:$PATH"
```

**理由**:
- tmuxの`run-shell`は非ログインシェルで起動されるため、シェル初期化ファイル（`.zprofile`、`.bash_profile`等）が読み込まれません
- hookから実行される`itmux sync/save`がtmuxコマンドを使うため、PATHの設定が必要

**設定手順**:

1. `~/.tmux.conf`を編集して上記の設定を追加
   - **重要**: TPM初期化（`run '~/.tmux/plugins/tpm/tpm'`）**より後**に書くこと
2. tmuxサーバーを再起動：
   ```bash
   tmux kill-server
   ```
3. iTmuxを使用して新しいプロジェクトを開く

**注意**:
- この設定は**Homebrew使用時のみ**必要です。システム標準のtmuxや、他の方法でインストールしたtmuxを使用している場合は不要です
- Intel Mac（`/usr/local/bin`）の場合は、パスを環境に合わせて調整してください
- 環境によっては、この設定がtmux起動時の問題を引き起こす場合があります。その場合は、この設定を削除してください

### iTerm2の推奨設定

#### tmux統合の自動埋葬

**Settings > General > tmux**で以下を有効化：

- ☑ **Automatically bury the tmux client session after connecting**

これにより、ゲートウェイセッションが自動的に非表示になります。

#### ウィンドウを閉じる時の挙動

iTerm2でtmuxウィンドウを×ボタンで閉じる時、以下のダイアログが表示されます：

**Kill（推奨）または Detach を選択**

iTmuxでは **Kill** を推奨します：

- **Kill**: 対象のウィンドウだけを削除（他のウィンドウは残る）
  - 自動的にconfig.jsonから削除される
  - **iTmuxではこちらを推奨**

- **Detach**: プロジェクト全体をdetach（全ウィンドウが閉じる）
  - `itmux close`と同じ動作
  - `itmux open`で再度全ウィンドウを復元可能

**注意**: iTerm2のtmux統合には「個別ウィンドウのdetach」という概念がありません。個別操作はKill、全体操作はDetachのみです。

### tmux-resurrect統合

iTmuxは[tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect)と統合して、tmuxセッションの永続化を実現します。

#### インストール（オプション）

```bash
# TPM (Tmux Plugin Manager)をインストール
git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm

# ~/.tmux.confに追加
cat >> ~/.tmux.conf <<'EOF'
# プラグイン設定
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'tmux-plugins/tmux-resurrect'

# TPMの初期化（必ず末尾に記述）
run '~/.tmux/plugins/tpm/tpm'
EOF

# プラグインをインストール
tmux source ~/.tmux.conf
# tmux内で prefix + I を押してインストール
```

#### 自動保存

**tmux-continuumは不要です。**

iTmuxが以下のタイミングで自動的に保存します：

- ウィンドウ作成時（`itmux add`、hook経由）
- ウィンドウ削除時（×ボタン、hook経由）
- ウィンドウ名変更時（hook経由）
- プロジェクトを閉じる時（`itmux close`）

#### 復元

システム再起動後、tmux-resurrectで保存された状態を復元できます：

```bash
# tmux起動後、prefix + Ctrl-r で復元
# または手動で復元スクリプトを実行
~/.tmux/plugins/tmux-resurrect/scripts/restore.sh
```

復元後、`itmux open`でiTerm2ウィンドウを開き直すことができます。

#### 保存される内容

- **実行中のプロセス**（vim、npm run devなど）
- **ペイン分割**の状態
- **カレントディレクトリ**
- **ウィンドウ配置**

#### 制限事項

tmux-continuumの自動保存は、iTerm2のControl Mode（-CC）では動作しません。これはtmux-continuumのアーキテクチャ上の制限です。

iTmuxはこの制限を回避するため、sync操作時にtmux-resurrectの保存スクリプトを直接実行します。

参考: [tmux-continuum issue #40](https://github.com/tmux-plugins/tmux-continuum/issues/40)

## 基本概念

### プロジェクト

**プロジェクト**は、関連する複数のtmuxセッションをグループ化したものです。

例: "my-project"というプロジェクトに以下の3つのセッションを紐付け
- `my_editor`: エディタ用
- `my_server`: 開発サーバー用
- `my_logs`: ログ監視用

### tmuxセッション

**tmuxセッション**は、独立した作業環境です。iTerm2の1つのウィンドウに対応します。

セッションには以下が保存されます：
- 実行中のプロセス（nvim、npm run devなど）
- カレントディレクトリ
- シェル履歴
- ウィンドウ/ペイン構成

### tmux Control Mode（-CC）

iTerm2とtmuxを統合するモードです。

- tmuxセッション → iTerm2ネイティブウィンドウとして表示
- ウィンドウを閉じても、tmuxセッションは保持される
- 翌日でも同じ状態で復元可能

## 基本的な使い方

### 1. プロジェクトを定義する

設定ファイルを作成: `~/.itmux/config.json`

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
        },
        {
          "name": "my_logs",
          "window_size": {
            "columns": 250,
            "lines": 80
          }
        }
      ]
    }
  }
}
```

### 2. プロジェクトを開く

```bash
itmux open my-project
```

**動作**:
1. 設定ファイルから`my-project`の定義を読み込み
2. 各tmuxセッション（`my_editor`, `my_server`, `my_logs`）に接続
3. iTerm2に3つのウィンドウが開く
4. 各ウィンドウのサイズを復元

**初回実行時**:
- tmuxセッションが存在しない場合は自動作成
- 空のシェルが起動するので、手動で作業環境を構築

**2回目以降**:
- 既存のtmuxセッションにアタッチ
- 前回の作業状態がそのまま復元される

### 3. プロジェクトを閉じる

```bash
itmux close my-project
# または、tmux セッション内ではプロジェクト名を省略
itmux close
```

**動作**:
1. `my-project`に属する全ウィンドウを検索
2. **現在の状態を自動保存**（ウィンドウサイズ、セッションリスト）
3. 各ウィンドウをデタッチ
4. iTerm2のウィンドウは閉じる
5. tmuxセッションはバックグラウンドで継続

**重要**: プロセスは停止しません
- nvimで編集中のファイルはそのまま
- `npm run dev`は動き続ける
- `tail -f`も継続中

**自動同期**: close時に現在の状態が `config.json` に保存されます
- 追加したセッションも自動的に保存
- ウィンドウサイズの変更も反映
- 次回 `open` 時に同じ状態で復元

### 4. プロジェクト一覧

```bash
itmux list
```

**出力例**:
```
Projects:
  my-project (3 sessions, open)
    - my_editor (200x60)
    - my_server (120x40)
    - my_logs (250x80)

  side-project (1 session, closed)
    - side_main
```

### 5. セッションを追加する

プロジェクトに新しいtmuxセッションを追加します。

```bash
# パターン1: プロジェクト名とセッション名を明示的に指定
itmux add my-project my_monitoring

# パターン2: セッション名を自動生成
itmux add my-project
# → 自動的に my-project-1, my-project-2 などが割り当てられる

# パターン3: tmux セッション内で実行（プロジェクト名を自動検出）
itmux add
# → 現在の tmux session 名（= プロジェクト名）に新しいセッションを追加
```

**動作**:
1. 新しいtmuxセッションを作成
2. iTerm2ウィンドウとして開く
3. プロジェクトに紐付け（`user.projectID` タグ付け）
4. `config.json` に自動的に追加

**使用例**:
```bash
# プロジェクトを開いた状態で
itmux open webapp

# 作業中に新しいウィンドウが必要になった（tmux session 内で実行）
itmux add monitoring
# → webapp プロジェクトに monitoring セッションを追加

# プロジェクトを閉じる
itmux close
# → monitoring セッションも含めて config.json に保存される
```

### 6. プロジェクト名の自動検出

iTmuxはtmux session内で実行すると、session名から自動的にプロジェクト名を検出します。

```bash
# プロジェクトを開く（tmux session名 = プロジェクト名）
itmux open webapp

# tmux session内では、プロジェクト名を省略可能
itmux add           # webapp にウィンドウを追加
itmux close         # webapp を閉じる
itmux sync          # webapp を同期

# 現在のプロジェクト名を確認
itmux current
# → webapp
```

**動作の仕組み**:
- `itmux open webapp` → tmux session名が `webapp` になる
- tmux session内で `itmux add` などを実行 → session名から `webapp` を自動検出
- プロジェクト名を明示的に指定することも可能: `itmux add other-project`

**メリット**:
- タイプ量が減る
- 現在のプロジェクトが明確（`itmux current` で確認）
- 複数プロジェクトを開いていても、各session内で正しく動作

## プロジェクト設定の変更（config）

`config.json` を手編集せず、CLI からプロジェクト設定を閲覧・変更できます。**設定の変更は CLI を第一選択肢**としてください（iTerm2 接続は不要です）。

### 設定の表示

```bash
itmux config show my-project
```

**出力例**:
```
Project: my-project
Name: my-project
Description: 開発用のメインプロジェクト
Cwd: /Users/me/Develop/my-project
Windows:
  - editor
  - server
```

### 作業ディレクトリ（cwd）の設定

プロジェクトごとのデフォルト作業ディレクトリを設定します（`~` 展開・絶対パスへの正規化あり）。

```bash
# cwd を設定
itmux config set cwd my-project ~/Develop/my-project

# cwd を削除
itmux config unset cwd my-project
```

**エラー時の挙動**:
- 存在しないパス: `✗ Config Error: Directory does not exist: ...`
- ファイルを指定した場合: `✗ Config Error: Not a directory: ...`
- プロジェクトが存在しない: `✗ Error: Project '...' not found`

存在しないディレクトリを先に config に書きたい場合は、手編集（下記）も利用できます。CLI 経由では、ディレクトリを作成してから `config set cwd` を実行してください。

### 手編集（上級者向け）

CLI で対応していない項目や、一括編集が必要な場合のみ `config.json` を直接編集します。

```bash
mkdir -p ~/.itmux
nvim ~/.itmux/config.json
```

## プロジェクト定義

### 命名規則

**プロジェクト名の制約**:

tmuxセッション名として使用されるため、以下の文字は使用できません：
- `:` (コロン) - tmuxのターゲット指定構文で使用
- `.` (ドット) - tmuxが自動的にアンダースコアに変換

**使用可能な文字**:
- 英数字
- `-` (ハイフン)
- `_` (アンダースコア)
- `/` (スラッシュ)
- `@` (アットマーク)

**推奨される命名例**:
```
my-project              # ハイフン区切り
my_project              # アンダースコア区切り
systems-track@karte     # @で組織を表現
karte/systems-track     # /で階層を表現
```

### 最小構成

```json
{
  "projects": {
    "simple-project": {
      "name": "simple-project",
      "tmux_windows": [
        {
          "name": "main"
        }
      ]
    }
  }
}
```

### プロジェクトの説明

プロジェクトには説明文を追加できます（オプション）：

```bash
# 説明は itmux config show で確認可能（設定は現状 JSON 手編集）
itmux config show my-project
```

JSON で直接編集する場合：

```json
{
  "projects": {
    "my-project": {
      "name": "my-project",
      "description": "開発用のメインプロジェクト",
      "tmux_windows": [
        {
          "name": "editor"
        }
      ]
    }
  }
}
```

説明は `itmux list` コマンドで表示されます：

```
Projects:
  my-project (1 windows) - 開発用のメインプロジェクト
    - editor
```

### ウィンドウサイズ指定

```json
{
  "name": "my_editor",
  "window_size": {
    "columns": 200,
    "lines": 60
  }
}
```

- `columns`: 列数（横幅）
- `lines`: 行数（縦幅）

省略した場合、デフォルトサイズで開きます。

### 作業ディレクトリ（cwd）

プロジェクトごとにデフォルトの作業ディレクトリを設定できます。

```bash
itmux config set cwd my-project ~/Develop/my-project
itmux config show my-project   # Cwd: /Users/me/Develop/my-project
itmux config unset cwd my-project
```

JSON で直接編集する場合（`~` は読み込み時に展開されます）：

```json
{
  "projects": {
    "my-project": {
      "name": "my-project",
      "cwd": "/Users/me/Develop/my-project",
      "tmux_windows": [
        {"name": "editor"}
      ]
    }
  }
}
```

**注意**:
- `itmux open` / `itmux add` 時に、設定した cwd でシェルが起動します（新規ウィンドウ）
- 全ウィンドウが既に開いている状態で `itmux open` した場合は、セッションのデフォルト cwd を更新し、全ペインを再起動して cwd を反映します
- tmux-resurrect 復元後は `itmux open` で config の cwd が再適用されます
- 既存ペインの再起動（`respawn-pane -k`）により、実行中のプロセス（vim 等）は終了します

### プロジェクト環境変数（environments）

プロジェクトごとにシェル環境変数を定義できます。`itmux open` 時に tmux セッションスコープへ適用され、新規ペインのシェルで利用できます。

```json
{
  "projects": {
    "my-project": {
      "name": "my-project",
      "environments": {
        "NODE_ENV": "development",
        "FOO": "bar"
      },
      "tmux_windows": [
        {"name": "editor"}
      ]
    }
  }
}
```

```bash
itmux open my-project
# 新規ウィンドウのシェルで確認
echo $NODE_ENV  # → development
```

**注意**:
- `environments` 未指定時は従来どおり（後方互換）
- tmux-resurrect 復元後は `itmux open` で config の値が再適用される
- 復元直後から存在していたシェルは tmux の仕様上、再起動するまで値が変わらない場合がある

### 複数プロジェクト

```json
{
  "projects": {
    "work-project": {
      "tmux_windows": [
        {"name": "work_editor"},
        {"name": "work_server"}
      ]
    },
    "personal-project": {
      "tmux_windows": [
        {"name": "personal_main"}
      ]
    }
  }
}
```

## 実践例

### 例1: Web開発プロジェクト

```json
{
  "projects": {
    "webapp": {
      "tmux_windows": [
        {
          "name": "webapp_editor",
          "window_size": {"columns": 220, "lines": 65}
        },
        {
          "name": "webapp_frontend",
          "window_size": {"columns": 140, "lines": 45}
        },
        {
          "name": "webapp_backend",
          "window_size": {"columns": 140, "lines": 45}
        },
        {
          "name": "webapp_logs",
          "window_size": {"columns": 180, "lines": 50}
        }
      ]
    }
  }
}
```

**使い方**:
```bash
# 朝、仕事開始
itmux open webapp

# [webapp_editor ウィンドウ]
cd ~/work/webapp
nvim .

# [webapp_frontend ウィンドウ]
cd ~/work/webapp/frontend
npm run dev

# [webapp_backend ウィンドウ]
cd ~/work/webapp/backend
python manage.py runserver

# [webapp_logs ウィンドウ]
cd ~/work/webapp
tail -f logs/app.log

# 作業中、一時的な監視ウィンドウが必要になった
itmux add monitoring
# → webappプロジェクトに monitoring セッションが追加される

# [monitoring ウィンドウ]
htop

# 夕方、仕事終了
itmux close
# → 全てのウィンドウが閉じる（monitoring含む）
# → サーバーは動き続ける
# → config.jsonに現在の状態が自動保存される

# 翌朝、再開
itmux open webapp
# → nvimは昨日開いたファイルそのまま
# → サーバーは動き続けている
# → monitoring セッションも復元される（htopは終了しているので空のシェル）
```

### 例2: 複数プロジェクトの切り替え

```bash
# プロジェクトAで作業
itmux open project-a
# ... 作業 ...

# プロジェクトBに切り替え
itmux close          # project-aを自動保存して閉じる
itmux open project-b
# ... 作業 ...

# プロジェクトAに戻る
itmux close          # project-bを自動保存して閉じる
itmux open project-a
# → 先ほどの状態がそのまま復元
```

### 例3: マルチモニタ環境

```json
{
  "projects": {
    "multi-display": {
      "tmux_windows": [
        {
          "name": "main_editor",
          "window_size": {"columns": 250, "lines": 70}
        },
        {
          "name": "sub_monitor_1",
          "window_size": {"columns": 180, "lines": 50}
        },
        {
          "name": "sub_monitor_2",
          "window_size": {"columns": 180, "lines": 50}
        }
      ]
    }
  }
}
```

各ウィンドウを異なるモニタに配置して使用できます。

## トラブルシューティング

### ウィンドウが開かない

**原因1: tmuxが起動していない**
```bash
# tmuxサーバーを確認
tmux list-sessions
```

**原因2: iTerm2 Python APIが無効**
- iTerm2 > Preferences > General > Magic
- "Enable Python API" にチェック

### セッションが見つからない

```bash
# tmuxセッション一覧を確認
tmux list-sessions

# セッションが存在しない場合、手動作成
tmux new-session -s my_editor
```

### ウィンドウサイズが正しく復元されない

**対処法1: tmuxコマンドで手動調整**
```bash
# セッション内で実行
tmux resize-window -x 200 -y 60
```

**対処法2: 設定ファイルを確認**
- `window_size`の値が正しいか確認
- フォントサイズとの兼ね合いで調整が必要な場合あり

### プロジェクトを閉じてもプロセスが残る

**これは正常な動作です**

iTmuxはウィンドウを閉じるだけで、tmuxセッション（とその中のプロセス）は保持します。

プロセスを停止したい場合：
```bash
# セッション内でプロセスを停止（Ctrl-C など）
# または、セッションごと削除
tmux kill-session -t my_server
```

### セッションを削除したい

tmuxセッションを終了すると、次回の `close` 時に自動的に削除されます。

```bash
# パターン1: セッション内で exit
exit
# → tmuxセッションが終了

# パターン2: tmux kill-session
tmux kill-session -t my_monitoring
# → セッションが削除される

# プロジェクトを閉じる
itmux close
# → 終了したセッションは config.json から自動的に削除される
# → 存在するセッションのみが保存される
```

**重要**: iTmuxは常に現在の状態をそのまま保存します
- 追加したセッション → 自動的に追加
- 削除したセッション → 自動的に削除
- 変更したウィンドウサイズ → 自動的に更新

### 設定ファイルの場所

デフォルト: `~/.itmux/config.json`

設定の変更は **`itmux config`** コマンドを優先してください（[プロジェクト設定の変更](#プロジェクト設定の変更config) を参照）。手編集が必要な場合：

```bash
# ディレクトリ作成
mkdir -p ~/.itmux

# 設定ファイル編集
nvim ~/.itmux/config.json
```

### デバッグモード

```bash
# 詳細ログを出力（将来実装予定）
itmux --verbose open my-project
```

## ヒントとベストプラクティス

### セッション命名規則

プロジェクト名をプレフィックスに：
```
my_project_editor
my_project_server
my_project_logs
```

利点：
- `tmux list-sessions`で見やすい
- 他のtmuxセッションと混同しない

### ウィンドウサイズの決め方

現在のウィンドウサイズを確認：
```bash
# tmuxセッション内で実行
tmux display-message -p '#{window_width}x#{window_height}'
```

出力例: `200x60`

この値を`config.json`に設定します。

### プロファイル切り替え（将来実装予定）

本番環境とdev環境で背景色を変える等は、Phase 2で実装予定です。

## さらなる情報

- [アーキテクチャドキュメント](./ARCHITECTURE.md)
- [設計アイデア](./ideas/)
- [GitHub Issues](https://github.com/otolab/iTmux/issues)
