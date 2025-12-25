# ゲートウェイウィンドウ仕様レポート v1

調査日: 2025-12-26
対象: iTerm2 Control Mode ゲートウェイウィンドウの仕様と実装方針

## 概要

iTmuxでは、iTerm2のControl Mode (`tmux -CC`) を使用してtmuxと統合する。このControl Modeでは「ゲートウェイウィンドウ」と呼ばれる特殊なウィンドウが作成される。このレポートでは、ゲートウェイウィンドウの仕様と適切な扱い方を文書化する。

## ゲートウェイウィンドウとは

### 定義

```python
gateway = await iterm2.Window.async_create(
    self.connection,
    command=f"/opt/homebrew/bin/tmux -CC new-session -A -s {project_name} -n {first_window_name}"
)
```

**ゲートウェイウィンドウ**とは、`tmux -CC` コマンドを実行するために作成されるiTerm2ウィンドウのこと。

### 役割

1. **Control Modeプロセスの実行環境**
   - `tmux -CC` プロセスを実行する
   - iTerm2とtmuxサーバー間の通信を仲介する

2. **TmuxConnectionの基盤**
   - このウィンドウ（のセッション）を通じてTmuxConnectionが確立される
   - ゲートウェイが閉じられると、TmuxConnectionも切断される

3. **セッションの永続化**
   - ゲートウェイが生き続ける限り、tmuxセッションとの接続が維持される

## iTerm2のAuto Bury機能

### 設定

**Preferences > General > tmux**:
- `Automatically bury the tmux client session after connecting`

この設定を有効にすると：

1. **自動埋葬**
   - `tmux -CC` 接続確立後、ゲートウェイセッションが自動的に埋葬される
   - セッションは「Buried Sessions」リストに移動する

2. **画面から非表示**
   - ゲートウェイウィンドウはユーザーの画面から見えなくなる
   - しかしプロセスは裏で生き続ける

3. **tmuxウィンドウの表示**
   - tmuxの各ウィンドウは、通常のiTerm2ウィンドウとして表示される
   - これらは独立したウィンドウとして操作可能

### 仕組み

```
tmux -CC 実行
    ↓
Control Mode確立
    ↓
Auto Bury発動（自動）
    ↓
ゲートウェイウィンドウ → Buried Sessionsへ移動
実際のtmuxウィンドウ → 画面に表示
```

## Gateway と TmuxConnection の関係

### 重要な区別

**Gateway Window:**
- `tmux -CC new-session -A -s {project_name} -n {first_window_name}` を実行する iTerm2 window
- Auto Bury により自動的に埋葬される
- `tmux -CC` プロセスが動き続ける

**Window 0（最初の tmux window）:**
- `tmux -CC` コマンドで作成される最初の tmux window（`-n {first_window_name}` で指定）
- Gateway とは**別の iTerm2 window** として表示される
- ユーザーが操作・閉じることができる通常のウィンドウ

**TmuxConnection:**
- tmux session との通信チャネル（iTerm2 API オブジェクト）
- Gateway の `tmux -CC` プロセスを通じて確立される
- **Window 0 を閉じた後も、この session と通信するために必要**

### TmuxConnection 取得の実装

**問題:**
- Window 0 が閉じられると、その iTerm2 window から TmuxConnection を直接取得できない
- しかし他の tmux window を操作するために TmuxConnection が必要

**解決策（session_manager.py:19-49）:**

```python
async def get_tmux_connection(self, project_name: str) -> iterm2.TmuxConnection:
    """プロジェクトのTmuxConnectionを取得."""
    # 全てのTmuxConnectionを取得
    tmux_conns = await iterm2.async_get_tmux_connections(self.connection)

    # 各connectionのsession nameを確認して一致するものを探す
    for conn in tmux_conns:
        result = await conn.async_send_command("display-message -p '#{session_name}'")
        session_name = result.strip()

        if session_name == project_name:
            return conn

    raise ITerm2Error(f"TmuxConnection not found for project: {project_name}")
```

**ポイント:**
- TmuxConnection は window に依存せず、session name で識別する
- `async_get_tmux_connections()` で全ての接続を取得
- tmux コマンドで session name を確認して、一致するものを返す
- これにより、どの window が開いている/閉じているかに関わらず、TmuxConnection を取得できる

## 実装における注意点

### 何もしなくて良い

Auto Bury機能が有効な場合、**コード側でゲートウェイウィンドウを隠す処理は不要**。

```python
# ❌ 不要なコード例（やってはいけない）
await gateway.async_close()  # → Control Modeセッション全体が終了してしまう
await gateway.async_set_buried(True)  # → Auto Buryで自動的に行われる
await session.async_select(False)  # → 効果なし
```

### 正しい実装

```python
async def connect_to_session(self, project_name: str, first_window_name: str = "default") -> None:
    """tmux Control Modeセッションに接続."""
    try:
        # Control Modeでtmuxセッションに接続
        gateway = await iterm2.Window.async_create(
            self.connection,
            command=f"/opt/homebrew/bin/tmux -CC new-session -A -s {project_name} -n {first_window_name}"
        )

        if not gateway:
            raise ITerm2Error("Failed to create gateway window")

        # TmuxConnection確立を待つ
        await asyncio.sleep(1.0)

        # ここで何もしない！
        # Auto Buryが自動的にゲートウェイを埋葬してくれる

    except Exception as e:
        raise ITerm2Error(f"Failed to connect to session: {e}") from e
```

## 参考ドキュメント

詳細な技術解説は以下のドキュメントを参照：

- `docs/ideas/iTerm2とtmux連携の表示改善.md`
  - セクション3: iTerm2のバージョンアップと標準機能の限界分析
  - セクション6: さらなる最適化：プロファイル設定との併用
  - セクション7: ゲートウェイセッションのライフサイクル管理

## 過去の試行錯誤と教訓

### 問題

コンテキスト圧縮前のセッションで、Auto Bury機能の存在を理解せずに作業した結果：

1. ゲートウェイウィンドウが2つ表示される問題を誤解
2. 場当たり的にウィンドウを隠す処理を試行
3. 存在しないメソッド `async_set_property()` を使用
4. エラーを起こすコードが残存

### 根本原因

**仕様を理解せずに実装を始めたこと**

- ドキュメント「iTerm2とtmux連携の表示改善.md」を最初に読んでいれば防げた
- Auto Buryの仕様を知らずに「ゲートウェイを隠さなければ」と思い込んだ

### 教訓

1. **仕様調査を先に行う**
   - 実装前に関連ドキュメントを読む
   - 既存の設計資料を確認する

2. **推測で実装しない**
   - 根拠に基づいて作業する
   - 不明な点はドキュメントで調べる、またはユーザーに質問する

3. **原則に立ち返る**
   - FOUNDATION_MODE の「本質の追求」
   - 「知らないということ」を認識する

## まとめ

- ゲートウェイウィンドウは `tmux -CC` の実行環境
- iTerm2の Auto Bury 機能により自動的に埋葬される
- コード側でゲートウェイを隠す処理は不要
- `connect_to_session()` は接続確立後に何もしなくて良い
