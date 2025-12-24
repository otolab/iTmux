# iTmux

iTerm2 + tmux orchestration tool for project-based window management.

## 概要

iTmuxは、iTerm2のPython APIとtmuxのControl Modeを組み合わせて、プロジェクトごとのターミナルウィンドウセットを管理するツールです。

## 主要機能

- `itmux open <project>`: プロジェクトのウィンドウセットを開く/復元
- `itmux close <project>`: プロジェクトの状態を保存してデタッチ
- `itmux list`: 管理中のプロジェクト一覧

## 技術スタック

- Python（uvで管理）
- iTerm2 Python API
- tmux（バックエンド）

## 前提条件

### 必須のiTerm2設定

iTmuxを使用するには、iTerm2で以下の設定を有効にする必要があります：

**"Automatically bury the tmux client session after connecting"**

設定場所: `iTerm2 > Settings > General > tmux`

この設定により、tmux Control Mode接続時に作成されるgatewayウィンドウが自動的に非表示になります。

### 必須のソフトウェア

- iTerm2 (macOS)
- tmux
- Python 3.12+

## 開発

### セットアップ

```bash
# 依存関係のインストール
uv sync
```

### テスト

#### Unit Tests

モックを使用したユニットテストを実行します。

```bash
# 全Unit Testsを実行
uv run pytest -m "not e2e" -v

# カバレッジ付きで実行
uv run pytest -m "not e2e" --cov=src/itmux --cov-report=term-missing
```

#### E2E Tests

実際のiTerm2とtmux環境を使用した統合テストを実行します。

**前提条件:**

1. **iTerm2 Python APIを有効化**
   - iTerm2 > Settings > General > Magic
   - "Enable Python API" にチェックを入れる
   - 初回接続時にセキュリティ確認ダイアログが表示される場合があります

2. **iTerm2が実行中であること**

3. **tmuxがインストールされていること**
   ```bash
   brew install tmux
   ```

**実行方法:**

```bash
# E2Eテストのみ実行
uv run pytest tests/e2e/ -v

# 全テスト（Unit + E2E）を実行
uv run pytest tests/ -v
```

**注意:** E2Eテストは実環境を必要とするため、環境が整っていない場合は自動的にスキップされます。CI環境では実行されません。

**トラブルシューティング:**

テストがスキップされる場合：
```bash
# 詳細なスキップ理由を確認
uv run pytest tests/e2e/ -vv
```

一般的な問題：
- `iTerm2 Python API is not enabled`: Settings > General > Magic で API を有効化してください
- `tmux is not installed`: `brew install tmux` でインストールしてください
- `iterm2 module is not available`: `uv sync` で依存関係を再インストールしてください

## ドキュメント

詳細な仕様やアーキテクチャについては、以下を参照してください：

- [AGENTS.md](./AGENTS.md) - プロジェクトインデックス
- [docs/ideas/](./docs/ideas/) - 設計ドキュメント

## ライセンス

MIT
