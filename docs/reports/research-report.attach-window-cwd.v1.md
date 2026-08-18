# attach 後追加ウィンドウの cwd + ネイティブウィンドウ調査レポート v1

調査日: 2026-08-18  
Issue: [#17](https://github.com/otolab/iTmux/issues/17)  
比較ベースライン: PR #16（`async_create_window()` + `respawn-pane -c -k`）

## 概要

attach 済み Control Mode 下で、**iTerm2 ネイティブウィンドウ**かつ**起動時 cwd**（`new-window -c` 相当）を同時に満たす経路を候補 A〜D で調査した。

**結論**: 現行 iTerm2 Python API / tmux 3.6a の組み合わせでは、**PR #16 の `async_create_window()` + `respawn-pane -c -k` が唯一の実用解**。より素直な代替案は見つからなかった。

## 調査環境

| 項目 | 値 |
|------|-----|
| macOS | darwin 24.6.0 |
| iTerm2 | 3.6.11（`iTermServer-3.6.11`） |
| tmux | 3.6a |
| iterm2 (PyPI) | **2.20**（プロジェクト制約 `>=2.7`、調査時点の最新） |
| 検証セッション | `issue17-test`（`tmux -CC attach` 済み） |
| 再現スクリプト | `scripts/research/issue17_*.py`, `issue17_cwd_shell_test.sh` |

## 制約（再確認）

| 項目 | 内容 | 確度 |
|------|------|------|
| `TmuxConnection.async_create_window()` | 引数なし。内部 RPC は `create_window { connection_id, affinity? }` のみ | **高**（iterm2 2.20 ソース + upstream `api.proto`） |
| `new-window -c`（CC 経路） | 起動 cwd は満たすが **同一 iTerm ウィンドウ内タブ**になる | **高**（実機 + #15） |
| `default-path` | **tmux 1.9 で削除**。tmux 3.6a では `invalid option` | **高**（実機） |
| attach 前 `new-session -c` | ネイティブ + 起動 cwd を満たす | **高**（`environment.py`） |

## iterm2 ライブラリ版調査（オペレータ要望）

| バージョン | `async_create_window` cwd | `async_rpc_create_tmux_window` | 備考 |
|-----------|---------------------------|-------------------------------|------|
| 制約下限 2.7 | なし | 調査対象外（古い） | pyproject.toml |
| 最新 2.20（実機） | なし | `affinity` のみ追加、**cwd なし** | `.venv` インストール版 |
| upstream master | なし | proto `CreateWindow` に `connection_id`, `affinity` のみ | GitHub `api.proto` |

**判断**: より新しい iterm2 ライブラリ（2.20）でも cwd / create_window 対応は**入っていない**。iTerm2 アプリ本体の RPC スキーマに cwd フィールドが無いため、Python 側だけの更新では解決しない。

## 候補評価結果表

評価軸: ○=満たす / △=部分的 / ×=満たさない / —=未検証

| 候補 | ネイティブウィンドウ | 起動時 cwd | 操作数 | ちらつき・レース | 既存整合 | 保守性 | 総合 |
|------|---------------------|-----------|--------|-----------------|----------|--------|------|
| **A** default-path + async_create_window | — | — | — | — | ×（tmux 3.6 で不可） | × | **不可** |
| **B** send-keys cd | ○ | × | 2 | △（cd 未反映） | ×（#9 要件外） | △ | **不可** |
| **C** Profile API (LocalWriteOnlyProfile) | △ | × | 2 | — | × | △ | **不可** |
| **D** new-window -c | ×（タブ） | ○ | 1 | ○ | ×（#15 デグレ） | ○ | **cwd のみ可** |
| **baseline** async_create_window + respawn-pane | ○ | ○ | 2〜3 | △（pane 再起動） | ○ | △ | **採用** |

### 候補別詳細

#### A. `default-path` + `async_create_window()`

- `tmux set-option default-path` → **`invalid option: default-path`**（tmux 3.6a）
- tmux 1.9 以降削除済み。Issue 本文の候補 A は **現行 tmux では実行不能**
- 仮に存在しても `async_create_window()` が tmux `-c` を渡せない根本問題は残る

#### B. 作成後 `send-keys` で `cd`

実機（`async_create_window` 経路、`async_activate` 後）:

```json
{
  "native_window": true,
  "startup_cwd_match": false,
  "pane_path": "/private/tmp/issue17-cwd-a",
  "expected_path": "/private/tmp/issue17-cwd-b"
}
```

- `send-keys` による `cd` が **pane に反映されない**（view-mode / CC フロー制御の影響疑い）
- たとえ cd できても **起動後 cd** であり #9 の「起動時 cwd」要件を満たさない
- tmux-resurrect との整合も劣る

#### C. Session / Profile API

実機:

```json
{
  "native_window": false,
  "startup_cwd_match": false,
  "pane_path": "/private/tmp/issue17-cwd-a"
}
```

- `LocalWriteOnlyProfile.set_custom_directory` は **新規セッション起動時**の initial directory 用
- `Session.async_set_profile_properties` は **実行中 pane の cwd を変更しない**（プロファイルコピーのみ）
- `TmuxConnection.async_create_window()` は `profile_customizations` を受け取れない

#### D. `new-window -c` + 経路切り分け

| 経路 | ネイティブ | 起動 cwd | 備考 |
|------|-----------|---------|------|
| `async_send_command("new-window -c")` | × | ○ | iTerm window 15820 の tab 1→2 に追加 |
| `subprocess tmux new-window -c` | × | ○ | API 経路と同一結果 |
| `itmux add`（現 bridge.py cwd 分岐） | × | ○ | tab 追加を確認 |

- iTerm2 設定 `NoSyncNewWindowFromTmuxOpensTmux=0` でも CC 下の `new-window -c` はタブ化
- **cwd だけ必要なら D は最良**だが、#15 で棄却された「タブ化デグレ」が再発

#### baseline. PR #16（`async_create_window` + `respawn-pane -c -k`）

実機:

```json
{
  "native_window": true,
  "startup_cwd_match": true,
  "pane_path": "/private/tmp/issue17-cwd-a"
}
```

- ネイティブウィンドウ + 起動 cwd を**同時に満たす唯一の経路**
- `-k` による pane 再起動で短いちらつき・レース余地あり（#14 で許容されたトレードオフ）
- `async_activate` による view-mode 防止と併用（既存 bridge.py）

## E. 上流機能要望の要否

| 観点 | 判断 |
|------|------|
| 要否 | **推奨する**（ただし iTmux 単独では実装不可） |
| 内容 | `TmuxRequest.CreateWindow` に `start_directory`（または tmux `-c` 相当）を追加 |
| 期待効果 | `respawn-pane -k` 不要化、操作 1 回化、ちらつき低減 |
| 優先度 | 中 — 現行 workaround は動作するが、設計上の歪みが残る |
| 代替 | 上流対応まで PR #16 方針を正とする |

## なぜ `respawn-pane` が現実解か（制約の整理）

1. **ネイティブウィンドウ作成**は iTerm2 RPC `async_create_window()` のみが確実（`new-window -c` はタブ）
2. **起動時 cwd**は tmux `-c` 付き window/pane 作成が必要（`send-keys cd` は要件外かつ CC 下で不安定）
3. **API に cwd 引数がない**ため、window 作成後に `respawn-pane -c -k` で pane を `-c` 相当に作り直すのが唯一の橋渡し
4. **`default-path` は使えない**（tmux 1.9+ 削除）
5. **Profile API は tmux pane 起動後には cwd を変えられない**

## 実装方針（本 Issue スコープ外・参考）

- **採用**: PR #16 方針を維持（#15 マージ後の正本）
- **リスク**: respawn ちらつき、view-mode レース（`async_activate` + sleep で緩和済み）
- **フォロー**: iTerm2 upstream に `CreateWindow.start_directory` 要望。対応後は respawn 経路を削除可能

## 再現手順

```bash
# 1. テスト用 config
export ITMUX_CONFIG_PATH=/path/to/config.json  # cwd 付き project 定義

# 2. CC attach
itmux open issue17-test

# 3. シェルベース（D 系）
scripts/research/issue17_cwd_shell_test.sh issue17-test

# 4. API ベース（baseline / B / C）— iTerm2 内で venv python 実行
.venv/bin/python scripts/research/issue17_async_create_test.py issue17-test
.venv/bin/python scripts/research/issue17_bc_test.py issue17-test
```

結果 JSON: `/tmp/issue17-cwd-shell-results.json`, `/tmp/issue17-async-create-results.json`, `/tmp/issue17-bc-results.json`

## 未検証・保留

- iTerm2 設定「Open tmux windows as native tabs in a new window」を **全組み合わせ**で網羅したマトリクス（代表環境では `new-window -c` はいずれもタブ）
- 候補 C を **window 作成前**に Profile を注入する経路（API 上存在しない）
- マルチモニタ / `window_size` 復元との組み合わせ（respawn 後の resize は既存 `set_window_size` で対応、追加検証は任意）

## 関連

- #15 / PR #16 — 暫定 respawn-pane 解
- #9 — 起動時 cwd 要件
- #14 — respawn 方針
- `docs/ARCHITECTURE.md` cwd 節（PR #16 マージ後に更新予定）
