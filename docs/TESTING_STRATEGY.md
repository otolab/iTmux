# iTmux テスト戦略

## 概要

iTmuxは3層のテスト戦略を採用します：
1. **Unit Tests**: 個別モジュールの動作検証（モック使用）
2. **Integration Tests**: コンポーネント間連携の検証（部分的な実環境）
3. **E2E Tests**: エンドツーエンドのユーザーシナリオ検証（完全な実環境）

## テストピラミッド

```
        /\
       /  \     E2E Tests (少数、重要シナリオのみ)
      /────\
     /      \   Integration Tests (中程度)
    /────────\
   /          \ Unit Tests (多数、高速)
  /────────────\
```

**基本方針**:
- Unit Tests: 高速、多数、モック使用
- Integration Tests: 中速、中程度、部分的な実環境
- E2E Tests: 低速、少数、完全な実環境

## 各層の詳細

### 1. Unit Tests（単体テスト）

**目的**: 個別モジュールの機能を独立して検証

**対象**:

#### 1.1 データ層（models.py） ✅ 完了
- **テストファイル**: `tests/itmux/test_models.py`
- **テスト内容**:
  - バリデーションルール（正の整数、命名規則、重複チェック）
  - JSON変換（model_dump, model_validate）
  - エッジケース（空文字列、不正文字、負数）
- **モック**: 不要（純粋な関数）
- **実施済み**: 22テスト、カバレッジ98%

#### 1.2 設定管理層（config.py） ✅ 完了
- **テストファイル**: `tests/itmux/test_config.py`
- **テスト内容**:
  - ファイルI/O（load, save）
  - API操作（get_project, list_projects, update_project, add_session）
  - エラーハンドリング（ファイル不在、JSONパースエラー）
- **モック**: ファイルシステムのみ（`tmp_path`フィクスチャ）
- **実施済み**: 19テスト、カバレッジ92%

#### 1.3 iTerm2ブリッジ層（iterm2_bridge.py） ← 次の実装対象
- **テストファイル**: `tests/itmux/test_iterm2_bridge.py`
- **テスト内容**:
  - `attach_session()`: ゲートウェイ作成、タグ付け、クリーンアップ
  - `add_session()`: 新規セッション作成
  - `detach_session()`: デタッチ実行
  - `find_windows_by_project()`: プロジェクトIDでフィルタリング
  - `set_window_size()`: ウィンドウサイズ変更
- **モック戦略**:
  - `iterm2.Connection`: モック（RPC通信を模倣）
  - `iterm2.App`: モック（ウィンドウ一覧を返す）
  - `iterm2.Window`: モック（変数設定、サイズ変更）
  - `iterm2.Session`: モック（コマンド送信）
  - `iterm2.WindowCreationMonitor`: モック（新ウィンドウID返却）
- **テスト方針**:
  - iTerm2 APIの呼び出しパターンを検証
  - タイムアウト処理を検証
  - エラーハンドリング（RPCException）を検証
- **カバレッジ目標**: 90%以上

#### 1.4 オーケストレーター層（orchestrator.py） ← 後で実装
- **テストファイル**: `tests/itmux/test_orchestrator.py`
- **テスト内容**:
  - `open()`: プロジェクトオープンロジック
  - `close()`: クローズ + 自動同期ロジック
  - `add()`: セッション追加ロジック
  - `list()`: プロジェクト一覧表示
- **モック戦略**:
  - `ConfigManager`: モック（設定読み込み/保存）
  - `ITerm2Bridge`: モック（ブリッジメソッド呼び出し）
  - `subprocess`: モック（tmuxコマンド実行）
- **テスト方針**:
  - ビジネスロジックの正確性を検証
  - コンポーネント呼び出し順序を検証
  - エラー伝播を検証
- **カバレッジ目標**: 90%以上

### 2. Integration Tests（統合テスト）

**目的**: 複数コンポーネントの連携を検証

**対象**:

#### 2.1 Config + Models（データ層統合） ✅ 部分的に完了
- **既存のテスト**: `test_config.py` の一部（save/load往復テスト）
- **追加検証項目**:
  - 複雑なプロジェクト構成の保存・復元
  - 大量セッションのパフォーマンス
  - 並行アクセス（複数プロセスからの読み書き）

#### 2.2 ITerm2Bridge + iTerm2 API（ブリッジ層統合）
- **テストファイル**: `tests/integration/test_iterm2_integration.py`
- **テスト内容**:
  - 実際のiTerm2インスタンスとの通信
  - ウィンドウ作成・タグ付け・検索
  - tmux -CC コマンドの実行
  - WindowCreationMonitorの実動作
- **実行環境**:
  - iTerm2が起動していること（必須）
  - Python APIが有効であること（必須）
  - tmuxがインストールされていること（必須）
- **テスト方針**:
  - `@pytest.mark.integration` でマーク
  - CI/CDではスキップ（ローカル開発者のみ実行）
  - テスト後のクリーンアップ（作成したウィンドウを削除）
- **実行方法**:
  ```bash
  pytest tests/integration/ -v -m integration
  ```

#### 2.3 Orchestrator + Config + ITerm2Bridge（全層統合）
- **テストファイル**: `tests/integration/test_orchestrator_integration.py`
- **テスト内容**:
  - open: 設定読み込み → ブリッジ呼び出し → ウィンドウ作成
  - close: ウィンドウ検索 → デタッチ → 設定保存
  - add: 新規セッション作成 → 設定追加
- **実行環境**:
  - iTerm2 + tmux + テスト用設定ファイル
- **テスト方針**:
  - 実際のtmuxセッションを作成・削除
  - テスト用プロジェクト設定を使用（`~/.itmux/test_config.json`）
  - 既存設定を汚染しない

### 3. E2E Tests（エンドツーエンドテスト）

**目的**: ユーザーシナリオ全体を検証

**対象**:

#### 3.1 基本ワークフロー
- **テストファイル**: `tests/e2e/test_basic_workflow.py`
- **シナリオ**:
  ```python
  # 1. プロジェクト作成
  # 設定ファイルに新規プロジェクトを追加

  # 2. プロジェクトを開く
  $ itmux open test-project
  # → 3つのtmuxセッションが開く
  # → 各ウィンドウに user.projectID タグ
  # → 環境変数 ITMUX_PROJECT=test-project

  # 3. セッションを追加
  $ itmux add monitoring
  # → 新しいウィンドウが開く
  # → config.jsonに追加される

  # 4. プロジェクトを閉じる
  $ itmux close
  # → 全ウィンドウがデタッチ
  # → config.jsonに現在の状態が保存される
  # → 環境変数クリア

  # 5. プロジェクトを再度開く
  $ itmux open test-project
  # → monitoring含めて全セッションが復元
  ```

#### 3.2 エラーケース
- **テストファイル**: `tests/e2e/test_error_scenarios.py`
- **シナリオ**:
  - 存在しないプロジェクトをopen → エラーメッセージ
  - tmuxセッションが既に削除されている → スキップ
  - iTerm2が起動していない → 明確なエラー
  - 設定ファイルが壊れている → 修復提案

#### 3.3 複雑なシナリオ
- **テストファイル**: `tests/e2e/test_advanced_scenarios.py`
- **シナリオ**:
  - 複数プロジェクトの切り替え
  - セッション削除の自動検出
  - ウィンドウサイズ変更の保存
  - マルチモニタ環境（手動テストのみ）

**実行環境**:
- iTerm2 + tmux + 完全な設定
- 実際のユーザー環境に近い状態

**テスト方針**:
- `@pytest.mark.e2e` でマーク
- CI/CDでは基本的にスキップ
- リリース前に手動実行
- 実行時間が長い（数分）

## テスト実行戦略

### ローカル開発時

```bash
# 高速フィードバック（Unit Tests のみ）
pytest tests/itmux/ -v

# Unit Tests + カバレッジ
pytest tests/itmux/ --cov=itmux --cov-report=term-missing

# Integration Tests を含む
pytest tests/ -v -m "not e2e"

# 全テスト（E2E含む、時間がかかる）
pytest tests/ -v
```

### CI/CD

```yaml
# GitHub Actions での例
- name: Run Unit Tests
  run: pytest tests/itmux/ --cov=itmux --cov-report=xml

# Integration/E2E はスキップ（環境依存のため）
```

### リリース前

```bash
# 全テストを手動実行
pytest tests/ -v --cov=itmux

# E2Eテストを個別に実行
pytest tests/e2e/ -v -s
```

## モック戦略

### iTerm2 API のモック

iTerm2 Python APIは非同期で複雑なため、以下の方針でモックします。

#### モック対象

1. **`iterm2.Connection`**
   - RPC通信をシミュレート
   - `async_get_app()` でモックAppを返す

2. **`iterm2.App`**
   - `windows` プロパティでモックウィンドウリストを返す
   - `async_select_menu_item()` を記録

3. **`iterm2.Window`**
   - `window_id`, `current_tab`, `async_set_variable()` をモック
   - `async_activate()`, `async_close()` を記録

4. **`iterm2.Session`**
   - `async_send_text()` を記録（送信コマンドを検証）

5. **`iterm2.WindowCreationMonitor`**
   - `async_get()` で予め設定したウィンドウIDを返す

#### モック実装例

```python
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_iterm2_connection():
    """iTerm2 Connection のモック."""
    connection = AsyncMock()
    app = AsyncMock()

    # モックウィンドウ
    mock_window = AsyncMock()
    mock_window.window_id = "test-window-id"
    mock_window.async_set_variable = AsyncMock()
    mock_window.async_close = AsyncMock()

    app.windows = [mock_window]
    app.get_window_by_id = MagicMock(return_value=mock_window)

    connection.async_get_app = AsyncMock(return_value=app)

    return connection, app, mock_window
```

### tmux コマンドのモック

```python
@pytest.fixture
def mock_subprocess():
    """subprocess のモック."""
    with patch('subprocess.run') as mock_run:
        # has-session: 成功を返す
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        yield mock_run
```

## テストデータ管理

### フィクスチャの階層

```python
# tests/conftest.py - 全テスト共通
@pytest.fixture
def sample_window_size():
    return WindowSize(columns=200, lines=60)

# tests/itmux/conftest.py - Unit Tests 用
@pytest.fixture
def temp_config_file(tmp_path):
    return tmp_path / "config.json"

# tests/integration/conftest.py - Integration Tests 用
@pytest.fixture
def real_iterm2_connection():
    """実際のiTerm2接続（統合テスト用）."""
    async def _get_connection():
        connection = await iterm2.Connection.async_create()
        yield connection
        await connection.async_close()
    return _get_connection

# tests/e2e/conftest.py - E2E Tests 用
@pytest.fixture
def test_project_config():
    """テスト用プロジェクト設定."""
    return {
        "name": "e2e-test-project",
        "tmux_sessions": [...]
    }
```

## カバレッジ目標

| モジュール | Unit Tests | Integration Tests | 合計目標 |
|-----------|-----------|------------------|---------|
| models.py | 98% ✅ | - | 98% |
| exceptions.py | 100% ✅ | - | 100% |
| config.py | 92% ✅ | +3% | 95% |
| iterm2_bridge.py | 90% | +5% | 95% |
| orchestrator.py | 90% | +5% | 95% |
| cli.py | 80% | - | 80% |
| **全体** | **85%** | **+5%** | **90%** |

## テストの優先順位

### Phase 1: 基盤（完了 ✅）
- [x] models.py: Unit Tests
- [x] config.py: Unit Tests

### Phase 2: ブリッジ層（次）
- [ ] iterm2_bridge.py: Unit Tests（モック使用）
- [ ] iterm2_bridge.py: Integration Tests（実iTerm2）

### Phase 3: オーケストレーター層
- [ ] orchestrator.py: Unit Tests（モック使用）
- [ ] orchestrator.py: Integration Tests（実環境）

### Phase 4: エンドツーエンド
- [ ] CLI: 基本ワークフローのE2Eテスト
- [ ] CLI: エラーケースのE2Eテスト

## 継続的改善

### メトリクス収集
- カバレッジレポート（Codecov連携）
- テスト実行時間のトラッキング
- フレーク率（不安定なテスト）のモニタリング

### リファクタリング指針
- カバレッジ < 85% のモジュールは優先的に改善
- 実行時間 > 1秒 のUnit Testはモック強化
- フレーク率 > 5% のテストは書き直し

## まとめ

iTmuxのテスト戦略は3層構造：

1. **Unit Tests**: 高速・多数・モック使用（開発の基盤）
2. **Integration Tests**: 中速・中程度・部分実環境（コンポーネント連携検証）
3. **E2E Tests**: 低速・少数・完全実環境（リリース前検証）

この戦略により、開発速度を維持しつつ、品質を担保します。
