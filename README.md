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
- iTerm2 Python API が有効になっていること
- iTerm2が実行中であること
- tmuxがインストールされていること

```bash
# E2Eテストのみ実行
uv run pytest tests/e2e/ -v

# 全テスト（Unit + E2E）を実行
uv run pytest tests/ -v
```

**注意:** E2Eテストは実環境を必要とするため、環境が整っていない場合は自動的にスキップされます。CI環境では実行されません。

## ドキュメント

詳細な仕様やアーキテクチャについては、以下を参照してください：

- [AGENTS.md](./AGENTS.md) - プロジェクトインデックス
- [docs/ideas/](./docs/ideas/) - 設計ドキュメント

## ライセンス

MIT
