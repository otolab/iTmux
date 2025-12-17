# iTmux 使い方ガイド

iTmuxは、iTerm2とtmuxを組み合わせて、プロジェクト単位でターミナルウィンドウを一括管理するツールです。

## 目次

- [セットアップ](#セットアップ)
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
```

**動作**:
1. `my-project`に属する全ウィンドウを検索
2. 各ウィンドウをデタッチ
3. iTerm2のウィンドウは閉じる
4. tmuxセッションはバックグラウンドで継続

**重要**: プロセスは停止しません
- nvimで編集中のファイルはそのまま
- `npm run dev`は動き続ける
- `tail -f`も継続中

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

## プロジェクト定義

### 最小構成

```json
{
  "projects": {
    "simple-project": {
      "tmux_sessions": [
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
      "tmux_sessions": [
        {"name": "work_editor"},
        {"name": "work_server"}
      ]
    },
    "personal-project": {
      "tmux_sessions": [
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
      "tmux_sessions": [
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

# 夕方、仕事終了
itmux close webapp
# → 全てのウィンドウが閉じる
# → サーバーは動き続ける

# 翌朝、再開
itmux open webapp
# → nvimは昨日開いたファイルそのまま
# → サーバーは動き続けている
```

### 例2: 複数プロジェクトの切り替え

```bash
# プロジェクトAで作業
itmux open project-a
# ... 作業 ...

# プロジェクトBに切り替え
itmux close project-a
itmux open project-b
# ... 作業 ...

# プロジェクトAに戻る
itmux close project-b
itmux open project-a
# → 先ほどの状態がそのまま復元
```

### 例3: マルチモニタ環境

```json
{
  "projects": {
    "multi-display": {
      "tmux_sessions": [
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
