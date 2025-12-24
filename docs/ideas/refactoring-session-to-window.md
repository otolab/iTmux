# リファクタリング計画：SessionConfig → WindowConfig

**作成日**: 2025-12-24
**目的**: tmuxの概念理解に基づいた正しい実装への修正
**ステータス**: 計画中

## 背景

### 問題の発見

tmux -CCとiTerm2統合の仕組みを調査した結果、以下の誤解が判明：

**誤った理解**：
- iTmuxプロジェクト内の複数の「セッション」（SessionConfig）を、それぞれ独立したtmuxセッションとして実装
- 各tmuxセッションごとに`tmux -CC attach-session`を実行

**正しい理解**：
- **1 iTmuxプロジェクト = 1 tmuxセッション**
- プロジェクト内の各「セッション」は**tmuxウィンドウ**
- 1つのTmuxConnection（tmux -CC接続）で複数のtmuxウィンドウを管理

### tmuxの階層構造（再確認）

```
セッション（Session）- tmuxサーバー上の最上位単位
  └─ ウィンドウ（Window）- 画面の単位（タブのようなもの）
      └─ ペイン（Pane）- 仮想terminalの最小単位
```

### iTmuxの設計意図

```
iTmuxプロジェクト: test-project
  ↓ (1対1対応)
tmuxセッション: test-project
  ├─ tmuxウィンドウ: editor   → iTerm2ウィンドウ1
  ├─ tmuxウィンドウ: server   → iTerm2ウィンドウ2
  └─ tmuxウィンドウ: logs     → iTerm2ウィンドウ3
```

**iTerm2 tmux統合（-CC）の特性**：
- 1つのtmuxウィンドウ = 1つのiTerm2ウィンドウ
- tmuxペインは使わない（1ウィンドウ = 1ペイン）
- iTerm2ウィンドウのサイズ等を復元可能

## リファクタリングの全体構成

### フェーズ構成

```
Phase 1: 準備（調査・設計）
  └─ 影響範囲の調査
  └─ 移行戦略の策定

Phase 2: モデル層の変更
  └─ SessionConfig → WindowConfig
  └─ ProjectConfig.tmux_sessions → tmux_windows
  └─ テスト修正

Phase 3: 設定ファイルの互換性対応
  └─ 読み込み時の変換処理
  └─ 保存時の新形式対応
  └─ マイグレーション機能

Phase 4: iterm2_bridge実装の修正
  └─ TmuxConnection.async_create_window()の使用
  └─ gateway管理の見直し
  └─ テスト修正

Phase 5: orchestrator実装の修正
  └─ open/close処理の見直し
  └─ テスト修正

Phase 6: ドキュメント更新
  └─ README.md
  └─ ARCHITECTURE.md
  └─ USAGE.md

Phase 7: 動作確認・統合テスト
  └─ E2Eテスト
  └─ 手動テスト
```

---

## Phase 1: 準備（調査・設計）

### 影響範囲の調査

**モデル層**：
- `src/itmux/models.py` - SessionConfig, ProjectConfig
- `src/itmux/config.py` - 設定読み書き

**実装層**：
- `src/itmux/iterm2_bridge.py` - iTerm2 API操作
- `src/itmux/orchestrator.py` - プロジェクト操作

**テスト**：
- `tests/itmux/test_models.py`
- `tests/itmux/test_config.py`
- `tests/itmux/test_iterm2_bridge.py`
- `tests/itmux/test_orchestrator.py`
- `tests/e2e/` - E2Eテスト

**設定ファイル**：
- `~/.itmux/config.json` - ユーザー設定
- テスト用設定ファイル

**ドキュメント**：
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/USAGE.md`
- `docs/ideas/*.md`

### 移行戦略

**後方互換性の方針**：
- 古い設定ファイル（`tmux_sessions`）も読み込める
- 保存時は新形式（`tmux_windows`）
- 自動マイグレーション機能を提供

**段階的な移行**：
1. モデル定義を変更（内部で両方サポート）
2. 実装を新しいモデルに合わせる
3. テストを修正
4. ドキュメント更新

---

## Phase 2: モデル層の変更

### 2.1 WindowConfigクラスの作成

**変更内容**：
```python
# Before
@dataclass
class SessionConfig:
    name: str
    window_size: Optional[WindowSize] = None

# After
@dataclass
class WindowConfig:
    name: str
    window_size: Optional[WindowSize] = None
```

**互換性対応**：
```python
# 古い名前のエイリアスを残す
SessionConfig = WindowConfig  # 非推奨、後方互換性のため
```

### 2.2 ProjectConfigの変更

**変更内容**：
```python
# Before
@dataclass
class ProjectConfig:
    name: str
    tmux_sessions: list[SessionConfig]

# After
@dataclass
class ProjectConfig:
    name: str
    tmux_windows: list[WindowConfig]

    # 後方互換性プロパティ
    @property
    def tmux_sessions(self) -> list[WindowConfig]:
        """非推奨: tmux_windowsを使用してください"""
        return self.tmux_windows
```

### 2.3 テストの修正

**対象ファイル**：
- `tests/itmux/test_models.py`

**変更内容**：
- `SessionConfig` → `WindowConfig`
- `tmux_sessions` → `tmux_windows`
- テストケース名の更新

---

## Phase 3: 設定ファイルの互換性対応

### 3.1 読み込み時の変換

**config.py の変更**：
```python
def _load_project_config(data: dict) -> ProjectConfig:
    # 古い形式（tmux_sessions）も受け入れる
    if "tmux_sessions" in data and "tmux_windows" not in data:
        data["tmux_windows"] = data.pop("tmux_sessions")

    return ProjectConfig(**data)
```

### 3.2 保存時の新形式

**変更内容**：
- 常に`tmux_windows`キーで保存
- `tmux_sessions`キーは出力しない

### 3.3 マイグレーション機能（オプション）

**CLIコマンド追加**：
```bash
itmux migrate-config
```

**機能**：
- 設定ファイルを読み込み
- 新形式で保存
- バックアップ作成

---

## Phase 4: iterm2_bridge実装の修正

### 4.1 現在の誤った実装

```python
# 各「セッション」ごとにtmux -CC attach-sessionを実行
async def attach_single_session_via_gateway(
    self,
    tmux_conn: iterm2.TmuxConnection,
    project_name: str,
    session_name: str,  # ← 実際はウィンドウ名
    ...
) -> str:
    await tmux_conn.async_send_command(f"attach-session -t {session_name}")
    # ← これが間違い
```

### 4.2 正しい実装

```python
async def open_project_windows(
    self,
    project_name: str,
    window_configs: list[WindowConfig],
) -> list[str]:
    """プロジェクトのtmuxウィンドウを開く"""
    # 1. プロジェクトのtmuxセッションに接続
    gateway_session, tmux_conn = await self.get_or_create_gateway(project_name)

    # 2. 各ウィンドウを作成
    window_ids = []
    for window_config in window_configs:
        # TmuxConnection.async_create_window()で新しいtmuxウィンドウ作成
        iterm_window = await tmux_conn.async_create_window()

        # ウィンドウ名を設定（tmux rename-window）
        await tmux_conn.async_send_command(
            f"rename-window -t {iterm_window.window_id} {window_config.name}"
        )

        # iTerm2ウィンドウにタグ付け
        await iterm_window.async_set_variable("user.projectID", project_name)
        await iterm_window.async_set_variable("user.window_name", window_config.name)

        # ウィンドウサイズ復元
        if window_config.window_size:
            await self.set_window_size(iterm_window.window_id, window_config.window_size)

        window_ids.append(iterm_window.window_id)

    return window_ids
```

### 4.3 gateway管理の見直し

**get_or_create_gateway()の変更**：
```python
async def get_or_create_gateway(
    self,
    project_name: str  # ← プロジェクト名を受け取る
) -> tuple[Optional[iterm2.Session], iterm2.TmuxConnection]:
    """プロジェクトのtmuxセッションに接続するgatewayを取得/作成"""

    # gateway.jsonの構造変更
    # {
    #   "projects": {
    #     "test-project": {
    #       "connection_id": "tmux",
    #       "session_name": "test-project",
    #       "created_at": "..."
    #     }
    #   }
    # }

    # プロジェクトごとにgateway情報を管理
    gateway_info = self._load_gateway_info(project_name)

    if gateway_info:
        # 既存接続を再利用
        tmux_conn = await iterm2.async_get_tmux_connection_by_connection_id(...)
        if tmux_conn:
            return None, tmux_conn

    # 新規作成
    gateway = await iterm2.Window.async_create(
        self.connection,
        command=f"/opt/homebrew/bin/tmux -CC new-session -A -s {project_name}"
    )
    # ...
```

### 4.4 メソッド名の変更

**変更**：
- `attach_single_session_via_gateway()` → `create_window_via_gateway()`
- `create_single_session_via_gateway()` → 削除（不要）
- `open_project_sessions()` → `open_project_windows()`

---

## Phase 5: orchestrator実装の修正

### 5.1 orchestrator.pyの変更

```python
async def open(self, project_name: str) -> None:
    # 1. プロジェクト設定取得
    project = self.config.get_project(project_name)

    # 2. プロジェクトのウィンドウを開く
    await self.bridge.open_project_windows(
        project_name,
        project.tmux_windows  # ← tmux_sessionsから変更
    )

    # 3. 環境変数設定
    os.environ["ITMUX_PROJECT"] = project_name
```

### 5.2 テストの修正

**対象ファイル**：
- `tests/itmux/test_orchestrator.py`

**変更内容**：
- `tmux_sessions` → `tmux_windows`
- メソッド名の更新

---

## Phase 6: ドキュメント更新

### 6.1 README.md

**更新内容**：
- 設定ファイルのサンプル更新
- `tmux_windows`の説明

### 6.2 ARCHITECTURE.md

**更新内容**：
- アーキテクチャ図の更新
- tmuxセッション/ウィンドウの関係説明
- TmuxConnectionの役割説明

### 6.3 USAGE.md

**更新内容**：
- 設定ファイルの書き方
- プロジェクト/セッション/ウィンドウの概念説明

### 6.4 gateway-connection-strategy.md

**更新内容**：
- 正しい理解に基づいた説明
- 実装の修正内容を反映

---

## Phase 7: 動作確認・統合テスト

### 7.1 ユニットテスト

```bash
uv run pytest -m "not e2e" -v
```

**確認項目**：
- 全テストがパス
- カバレッジが維持されている

### 7.2 E2Eテスト

```bash
uv run pytest tests/e2e/ -v
```

**確認項目**：
- プロジェクトの作成
- open/close操作
- 設定の永続化

### 7.3 手動テスト

**テストケース**：
1. 新規プロジェクト作成
2. 複数ウィンドウのプロジェクトをopen
3. ウィンドウサイズの復元確認
4. close後の再open確認
5. 古い設定ファイルの読み込み確認

---

## 実装の優先順位

### 高優先度（必須）

1. **Phase 2**: モデル層の変更
2. **Phase 3**: 設定ファイルの互換性
3. **Phase 4**: iterm2_bridge実装
4. **Phase 5**: orchestrator実装

### 中優先度（推奨）

5. **Phase 6**: ドキュメント更新
6. **Phase 7**: 動作確認

### 低優先度（オプション）

- マイグレーションCLIコマンド

---

## リスク管理

### 想定されるリスク

**1. TmuxConnection.async_create_window()の挙動が不明**
- 対策：事前に動作確認、ドキュメント調査

**2. 既存の設定ファイルが壊れる**
- 対策：後方互換性の実装、バックアップ推奨

**3. テストの大幅な修正が必要**
- 対策：段階的な修正、CI/CDでの確認

### ロールバック計画

- git commitを細かく分ける
- 各フェーズごとにテストを確認
- 問題があれば該当commitをrevert

---

## 次のステップ

1. この計画をレビュー
2. Phase 2から開始
3. 各フェーズ完了時に動作確認
4. 問題があれば計画を見直し

---

## 進捗記録

**2025-12-24**:
- 計画策定完了
- 複雑タスクモードに移行
- **Phase 2完了**: モデル層の変更
  - SessionConfig → WindowConfig にリネーム
  - ProjectConfig.tmux_sessions → tmux_windows に変更
  - test_models.py のテスト修正
  - 全テスト22個がパス（✅）
- **Phase 3完了**: 設定ファイルの互換性対応（後に削除）
  - config.py の update_project() を windows に変更
  - add_window() メソッドを追加
  - test_config.py のテスト修正
  - 全テスト41個がパス（✅）
- **後方互換性機能の削除**:
  - models.py の SessionConfig エイリアスを削除
  - config.py の変換処理と add_session() を削除
  - test_models.py, test_config.py のレガシーテストを削除
  - conftest.py, iterm2_bridge.py, orchestrator.py の SessionConfig 参照を削除
  - 全テスト41個がパス（✅）
- **Phase 4完了**: iterm2_bridge実装の修正
  - `open_project_windows()` メソッドを実装（TmuxConnection.async_create_window使用）
  - gateway管理をプロジェクト単位に変更（_load/save/clear_gateway_info）
  - `get_or_create_gateway(project_name)` に変更
  - `close_gateway(project_name)` と `get_gateway_status(project_name)` をプロジェクト対応
  - 古いメソッド削除：`attach_single_session_via_gateway()`, `create_single_session_via_gateway()`
  - orchestrator.py の修正：`open()`, `list()`, `add()`, `_generate_window_name()`
  - テストの修正：test_iterm2_bridge.py, test_orchestrator.py
  - 全テスト68個がパス（✅）
- **Phase 5スキップ**: orchestrator実装はPhase 4で同時に完了
- **Phase 6開始**: ドキュメント更新

