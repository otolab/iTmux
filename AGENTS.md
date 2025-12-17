# iTmux - Agent Index

このドキュメントは、iTmuxプロジェクトのナビゲーションインデックスです。

## プロジェクト概要

iTmuxは、iTerm2のPython APIとtmuxのControl Modeを統合し、プロジェクトベースのターミナルウィンドウ管理を実現するツールです。

## ディレクトリ構造

```
iTmux/
├── docs/              # ドキュメント
│   └── ideas/        # 設計・調査ドキュメント
├── src/              # ソースコード（uvプロジェクト）
│   └── itmux/        # メインパッケージ
├── scripts/          # ランナースクリプト
├── .itmux/           # ユーザー設定（~/.itmux/）
└── tests/            # テスト
```

## 重要なドキュメント

### 設計ドキュメント

- [iTerm2 Python APIとtmux連携.md](./docs/ideas/iTerm2%20Python%20API%E3%81%A8tmux%E9%80%A3%E6%90%BA.md)
  - iTerm2 Python APIとtmuxの統合に関する詳細な調査・設計書
  - オーケストレーションアーキテクチャの全体像
  - 実装パターンとコード例

### 開発ガイド

- README.md - プロジェクト概要
- CLAUDE.md - Claude Code用設定

## 実装の核心要素

### データモデル

- プロジェクト定義: JSON形式（`~/.itmux/projects/`）
- tmuxセッションとの1:1マッピング
- ユーザー変数（`user.projectID`）による識別

### 技術的特徴

1. **非同期API**: asyncioベースのiTerm2 Python API
2. **永続化**: tmux Control Mode（`-CC`）による状態保持
3. **動的タグ付け**: WindowCreationMonitorによるウィンドウ識別
4. **安全なデタッチ**: `tmux.Detach`メニュー項目のプログラム実行

## コマンド構造

```bash
itmux open <project>     # プロジェクトを開く/復元
itmux close <project>    # プロジェクトをデタッチ
itmux list              # プロジェクト一覧
```

## 開発環境

- Python: uvで管理
- 実行: `scripts/itmux` ランナースクリプト経由
- テスト: pytest

## Issue管理

プロジェクトはGitHub Issueベースで管理されています。

- [Issue #1](https://github.com/otolab/iTmux/issues/1): プロジェクト初期セットアップ
