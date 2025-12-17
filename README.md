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

## ドキュメント

詳細な仕様やアーキテクチャについては、以下を参照してください：

- [AGENTS.md](./AGENTS.md) - プロジェクトインデックス
- [docs/ideas/](./docs/ideas/) - 設計ドキュメント

## ライセンス

MIT
