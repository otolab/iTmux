# iTmux 使い方ガイド

iTmuxは、iTerm2とtmuxを組み合わせて、プロジェクト単位でターミナルウィンドウを一括管理するツールです。

## 目次

- [セットアップ](#セットアップ)
  - [iTerm2の推奨設定](#iterm2の推奨設定)
- [基本概念](#基本概念)
- [基本的な使い方](#基本的な使い方)
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
# または、環境変数を使って省略形
itmux close
```

**動作**:
1. `my-project`に属する全ウィンドウを検索
2. **現在の状態を自動保存**（ウィンドウサイズ、セッションリスト）
3. 各ウィンドウをデタッチ
4. iTerm2のウィンドウは閉じる
5. tmuxセッションはバックグラウンドで継続
6. 環境変数 `ITMUX_PROJECT` をクリア

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

# パターン3: 環境変数を使って省略
itmux add
# → $ITMUX_PROJECT に新しいセッションを追加
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
# → 環境変数 ITMUX_PROJECT=webapp が設定される

# 作業中に新しいウィンドウが必要になった
itmux add monitoring
# → webappプロジェクトに monitoring セッションを追加

# プロジェクトを閉じる
itmux close
# → monitoring セッションも含めて config.json に保存される
```

### 6. 環境変数の活用

iTmuxは `ITMUX_PROJECT` 環境変数でアクティブなプロジェクトを追跡します。

```bash
# プロジェクトを開くと環境変数が設定される
itmux open webapp
# → export ITMUX_PROJECT=webapp

# 現在のプロジェクトを確認
echo $ITMUX_PROJECT
# → webapp

# 環境変数があればプロジェクト名を省略可能
itmux add           # webapp にセッションを追加
itmux close         # webapp を閉じる

# プロジェクトを閉じると環境変数がクリアされる
itmux close
# → unset ITMUX_PROJECT
```

**メリット**:
- タイプ量が減る
- 現在のプロジェクトが明確
- シェル環境に統合しやすい

## プロジェクト定義

### 最小構成

```json
{
  "projects": {
    "simple-project": {
      "tmux_windows": [
        {
          "name": "main"
        }
      ]
    }
  }
}
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
# → 環境変数 ITMUX_PROJECT=webapp が設定される

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
# → 環境変数 ITMUX_PROJECT がクリアされる

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
# → ITMUX_PROJECT=project-a
# ... 作業 ...

# プロジェクトBに切り替え
itmux close          # project-aを自動保存して閉じる
itmux open project-b
# → ITMUX_PROJECT=project-b
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
