# **iTerm2とtmux \-CCモードのPython API制御における「View-Mode」遷移の技術的機序に関する包括的分析報告書**

## **1\. 序論：統合環境における状態同期の複雑性**

現代の開発環境において、ターミナルマルチプレクサであるtmuxと、macOS上の高機能ターミナルエミュレータであるiTerm2の統合（Integration）は、CLI（Command Line Interface）の生産性を飛躍的に向上させる重要な技術スタックとなっている。特に、iTerm2が提供する「Control Mode（-CCモード）」は、tmuxのセッション管理能力とiTerm2のネイティブGUIを融合させ、従来のテキストベースのペイン管理をOSネイティブのウィンドウやタブとして操作することを可能にしている。さらに、iTerm2がバージョン3.3以降で強化したPython APIは、この統合環境をプログラムによって外部から制御・自動化する道を開いた。

しかし、この高度な統合は、異なるプロセス間（iTerm2プロセス、Pythonスクリプトランタイム、tmuxサーバープロセス）での複雑な状態同期と通信プロトコル（Control Mode Protocol）の上に成り立っている。本報告書は、ユーザーから提起された「TmuxConnection.async\_create\_window()を実行した際、起動したtmuxウィンドウが意図せずView-Mode（コピーモード）に入ってしまう」という特異な現象について、その技術的背景、プロトコルレベルでの挙動、および根本的な発生機序を包括的に分析するものである。

この現象は、単なるアプリケーションの不具合（バグ）というよりも、非同期通信におけるフロー制御（Flow Control）、初期化シーケンスにおける競合（Race Condition）、そしてtmux独自のバッファリングメカニズムが複合的に作用した結果である可能性が高い。本分析では、提供された技術資料に基づき、iTerm2とtmux間の通信プロトコルの詳細、ウィンドウ生成時のライフサイクル、および「View-Mode」と認識される状態の内部定義を解明し、開発者やシステムエンジニアがこの挙動を深く理解し、適切な制御実装を行うための理論的基盤を提供する。

### **1.1 報告書の構成と範囲**

本報告書は以下の構成で展開される。

* **第2章：システムアーキテクチャ分析** \- iTerm2 Python APIとtmux Control Modeの通信構造、およびTmuxConnectionクラスの役割について詳述する。  
* **第3章：ウィンドウ生成のライフサイクル** \- async\_create\_window()呼び出しから実際にウィンドウが表示されるまでの内部プロセスを時系列で追跡する。  
* **第4章：「View-Mode」の技術的定義と発生機序** \- ユーザーが観測する「View-Mode」の実体と、それがControl Modeプロトコルにおける「フロー制御（Pause）」とどのようにリンクしているかを分析する。  
* **第5章：複合的要因の検討** \- シェル初期化、ウィンドウリサイズ、エスケープシーケンスなどが及ぼす影響について考察する。  
* **第6章：診断と緩和策** \- ログ解析手法と、APIレベルでの具体的な回避策を提示する。

## ---

**2\. システムアーキテクチャ分析：Python APIとControl Modeの融合**

当該事象の機序を解明するためには、iTerm2、Pythonランタイム、そしてtmuxサーバーがどのように連携し、制御権を受け渡しているかを理解する必要がある。ここでは、その通信基盤となるアーキテクチャを詳細に解説する。

### **2.1 iTerm2 Python APIの非同期通信モデル**

iTerm2のPython APIは、従来のAppleScriptによる制御とは異なり、GoogleのProtocol Buffers（Protobuf）とWebSocketを用いた双方向かつ高速なRPC（Remote Procedure Call）メカニズムを採用している1。

ユーザーが実行するPythonスクリプトは、iTerm2アプリケーション内部ではなく、独立したプロセスとして起動する。このスクリプトはiterm2モジュールを介してiTerm2本体とWebSocket接続を確立し、コマンドの送信とイベントの受信を行う。TmuxConnection.async\_create\_window()のようなメソッドは、Pythonのasyncioライブラリを活用した非同期関数として設計されており、ネットワークI/O（iTerm2へのリクエスト送信と完了通知の待機）が発生してもメインスレッドをブロックしない構造となっている1。

| コンポーネント | 役割 | 通信方式 | 備考 |
| :---- | :---- | :---- | :---- |
| **Python Script** | ユーザーロジックの実行 | WebSocket / Protobuf | asyncioイベントループ上で動作 |
| **iTerm2 App** | ターミナルエミュレーション | Unix Domain Socket / Pipe | tmuxとの仲介役、描画エンジン |
| **tmux Server** | セッション・ウィンドウ管理 | Control Mode Protocol | バックグラウンドで全状態を保持 |

### **2.2 tmux Control Mode (-CC) の独自プロトコル**

通常のtmuxは、端末エミュレータ上に自身のUI（ステータスラインやペイン境界線）を文字として描画する。しかし、-CCフラグ（Control Mode）で起動されたtmuxは、描画を行わず、代わりに機械可読な独自プロトコルを用いてクライアント（iTerm2）と対話する3。

このプロトコルはテキストベースであり、tmuxの状態変化（ウィンドウの追加、ペインの出力更新、モード変更など）を「通知（Notification）」として非同期に送信する。iTerm2はこの通知をパースし、自身のネイティブUI（ウィンドウやタブ）にマッピングして描画する。つまり、ユーザーが見ているウィンドウはiTerm2のものだが、その実体と制御権はtmuxサーバーにあるという「二重構造」が形成されている。

#### **Control Modeプロトコルの基本構造**

Control Modeでは、tmuxからの出力は以下のような形式をとる3：

* **コマンド応答:** %begin と %end（または %error）で囲まれたブロック。  
* **非同期通知:** % で始まる行（例: %output, %window-add, %session-changed）。

TmuxConnectionオブジェクトは、このプロトコルのストリームを監視し、Pythonオブジェクト（WindowやTab）の状態をリアルタイムに更新する役割を担っている2。

### **2.3 TmuxConnection クラスの役割**

資料 2 および 2 に示されるように、TmuxConnection クラスはiTerm2と特定のtmuxセッション間の接続を抽象化したものである。async\_create\_window() メソッドは、単にiTerm2に命令を送るだけでなく、その結果としてtmuxから返される %window-add 通知を待ち受け、対応するiTerm2の Window オブジェクトを特定して返却するという複雑なステートマシンを内包している。

この「待ち受け」の間に、tmux側からのデータストリームの状態によっては、APIの完了復帰とウィンドウの初期状態確定の間に微細なタイムラグや競合が生じる余地がある。

## ---

**3\. ウィンドウ生成のライフサイクルと「View-Mode」の発生点**

問題の現象である「View-Modeへの遷移」がどのタイミングで発生しているかを特定するため、async\_create\_window() 実行時の内部プロセスを詳細に追跡する。

### **3.1 async\_create\_window() の実行シーケンス**

Pythonスクリプトが await connection.async\_create\_window() を呼び出した際、内部では以下の手順が進行する。

1. **RPCリクエスト:** PythonスクリプトからiTerm2へ、「tmuxセッションXに新規ウィンドウを作成せよ」というRPCが送信される。  
2. **tmuxコマンド発行:** iTerm2は、管理下のtmuxプロセスに対して標準入力経由で new-window コマンドを送信する3。  
3. **サーバー処理:** tmuxサーバーは新しい仮想端末（PTY）を割り当て、デフォルトシェル（zshやbash）を起動する。同時に .zshrc などの設定ファイルが読み込まれ、初期プロンプトや起動メッセージが出力される。  
4. **通知の返信:** tmuxはiTerm2に対し、%window-add @\<id\>（ウィンドウ作成通知）と、%output %\<pane-id\>...（初期出力データ）を送信する。  
5. **オブジェクト化:** iTerm2は通知を受けてネイティブウィンドウを開き、Python側に完了を通知する。Pythonの await が解除され、Window オブジェクトが返される。

### **3.2 「View-Mode」の実体：Copy ModeとPaused状態**

ユーザーが報告している「View-Mode」とは、iTerm2およびtmuxにおける「コピーモード（Copy Mode）」を指していると考えられる。iTerm2のControl Mode統合において、このモードは以下のような特徴を持つ6：

* **視覚的特徴:** ウィンドウ右上に「Copy Mode」インジケータが表示される、またはウィンドウの枠線（Border）が黄色や特定の色に変化する（設定による）8。  
* **操作的特徴:** 新しい出力があっても自動的にスクロール（追従）せず、ユーザーは矢印キー等で履歴を閲覧できる。  
* **発生条件:** ユーザーが明示的に操作（Prefix \+ \[ やマウススクロール）した場合のほか、**tmuxからの通知によって自動的に遷移する場合**がある。

この「自動的な遷移」こそが、本件の核心的なメカニズムである。Control Modeにおいて、View-Mode（コピーモード）への遷移は、単なるユーザーインターフェースの変更ではなく、プロトコル上の「データフロー制御」と密接に関連している。

## ---

**4\. 発生機序の解明：Control Modeにおけるフロー制御メカニズム**

調査資料 3 の詳細な分析により、この現象の最も有力な原因は、tmux Control Mode独自の**フロー制御（Flow Control）**、特に **pause-after フラグと %pause 通知** の相互作用にあると結論付けられる。

### **4.1 pause-after と %pause のメカニズム**

Control Modeはテキストベースのプロトコルであるため、ターミナル内のプログラムが大量のテキストを高速に出力した場合（例: cat で巨大なログを表示、複雑な起動スクリプトの実行）、tmuxとiTerm2間の通信パイプが詰まる恐れがある。これを防ぐため、tmuxには強力なフロー制御機能が実装されている。

* **pause-after 設定:** iTerm2はtmuxに接続する際、refresh-client \-f pause-after=N コマンドを使用し、「N秒以上バッファが滞留したら転送を一時停止せよ」という指示を出すことができる4。  
* **%pause 通知:** 特定のペインの出力バッファが閾値を超えた場合、tmuxはデータの送信を停止し、iTerm2に対して %pause %\<pane-id\> という通知を送る。  
* **iTerm2の挙動:** %pause を受信したiTerm2は、そのペインのリアルタイム更新を停止する。ユーザー視点では、これは\*\*「画面がフリーズした」あるいは「勝手にコピーモード（履歴閲覧モード）に入った」状態\*\*として認識される。

### **4.2 初期化時の「出力バースト」によるトリガー**

async\_create\_window() で新規ウィンドウを作成した直後は、以下の要因により一時的な「出力バースト（Output Burst）」が発生しやすいタイミングである。

1. **シェルの初期化:** 現代的な開発環境（Zsh \+ Oh-My-Zsh, Powerlevel10kなど）では、起動時に複雑なプロンプト描画、Gitステータスの取得、システム情報の表示（neofetch等）が行われ、大量のエスケープシーケンスとテキストが瞬時に出力される10。  
2. **非同期処理のラグ:** Python API経由でウィンドウを作成する場合、iTerm2がウィンドウのUIコンポーネントを準備し、描画パイプラインを確立するまでの間に、tmux側では既にシェルの出力が完了し、バッファに蓄積されている可能性がある。  
3. **トリガーの発動:** iTerm2が描画準備を完了してデータを受け入れる前に、tmux側のバッファが pause-after の閾値を超過すると、tmuxは安全策として %pause を発行する。これにより、ウィンドウが表示された瞬間には既に「Paused（＝View-Mode）」状態となっているのである。

### **4.3 refresh-client \-A による復帰プロセス**

通常、このPaused状態は、ユーザーがスクロールバーを操作するか、キー入力を行うことで解除される。iTerm2はユーザーのアクションを検知すると、tmuxに対して refresh-client \-A %\<pane-id\>:continue（または同様の再開コマンド）を送信し、%continue 通知と共にリアルタイム更新モード（入力モード）へ復帰する3。

しかし、Pythonスクリプトによる自動実行の場合、ウィンドウ作成直後にユーザーの物理的な操作が介在しないため、スクリプトが明示的に介入しない限り、ウィンドウはPaused（View-Mode）のまま放置されることになる。これが、報告されている現象の正体である。

以下の表は、通常のウィンドウ作成と、View-Mode現象が発生する場合のプロトコルシーケンスの比較である。

| シーケンス | 通常の挙動 (Normal Behavior) | View-Mode現象 (Anomaly) |
| :---- | :---- | :---- |
| **1\. Request** | new-window 送信 | new-window 送信 |
| **2\. Response** | %window-add @1 受信 | %window-add @1 受信 |
| **3\. Processing** | シェル起動処理開始 | シェル起動処理開始（大量出力発生） |
| **4\. Data Stream** | %output %1... (適度な量) | %output %1... (バッファ上限接近) |
| **5\. Flow Control** | 発生せず | **tmuxが %pause %1 を送信** |
| **6\. iTerm2 State** | リアルタイム更新モード (Active) | **更新停止モード (Paused / View-Mode)** |
| **7\. User View** | プロンプトが表示され点滅 | 黄色い枠線等が表示され、更新停止 |

## ---

**5\. その他の複合的要因と技術的検証**

フロー制御以外にも、いくつかの技術的要因がこの現象を誘発、あるいは悪化させている可能性がある。これらの要因も排除せず検討する必要がある。

### **5.1 ウィンドウリサイズに伴うレイアウト競合 (Resize Race Condition)**

資料 11 では、tmux \-CC モードにおいて、新規ウィンドウ作成時のサイズ決定に関する問題が報告されている。iTerm2のプロファイル設定サイズと、tmuxセッションが現時点で保持しているサイズが異なる場合、ウィンドウ作成直後にリサイズイベントが発生する。

もし、ウィンドウ作成直後にiTerm2がウィンドウサイズを変更（リサイズ）しようとし、その過程でtmux側からの出力位置とiTerm2側のビューポートサイズに不整合が生じると、iTerm2は「現在表示しているのは最新の行ではない（スクロールアップした状態である）」と誤認する可能性がある。iTerm2は、ビューポートが最下部にない場合、自動的にコピーモード（View-Mode）のUIを表示する仕様となっているため、これが原因でView-Modeに入ったように見えるケースが考えられる。

### **5.2 マウスレポートモードの干渉**

資料 12 によれば、.tmux.conf で set \-g mouse on が設定されている場合、マウスイベントの扱いが変わる。Python API経由でウィンドウを作成した際、OSのマウスカーソル位置が偶然新規ウィンドウ上にあると、iTerm2が意図しないスクロールイベントを送信してしまう可能性がある。Control Mode下のtmuxは、スクロールイベントを受け取ると即座にコピーモードへ遷移する仕様を持つため、これがトリガーとなっている可能性も否定できない。

### **5.3 代替画面バッファ (Alternate Screen) の誤判定**

VimやLessなどが使用する「代替画面バッファ（Alternate Screen）」への遷移シーケンスにおいて、Control Modeプロトコル上のハンドリングにバグがある場合、iTerm2がモードを誤認することがある14。特にシェル起動時に実行されるスクリプト（例えば tput smcup を使用するもの）がある場合、画面クリアとバッファ切り替えのタイミングでView-Modeフラグが誤って立つ挙動が過去に観測されている。

## ---

**6\. 診断手法と解決策：エンジニアリングアプローチ**

以上の分析に基づき、この現象を確実に診断し、解消するための具体的なアプローチを提示する。

### **6.1 診断：Control Modeログの確認**

まず、この現象がフロー制御（%pause）によるものか、その他の要因によるものかを確定させるために、iTerm2のデバッグログ機能を使用することが推奨される。

* **手順:** iTerm2で tmux \-CC 接続中、メニューの Shell \> tmux \> Toggle Logging（またはダッシュボードで L キー）を有効にする15。  
* **確認事項:** ログファイル内で、new-window コマンド送信直後に %pause %\<pane-id\> という通知が記録されているかを確認する。これが存在すれば、原因は間違いなくフロー制御である。  
* **補足:** %pane-mode-changed という通知がある場合は、tmux内部で明示的にコピーモードへの遷移コマンドが実行されている（設定ファイルのフックなどが原因）ことを示唆する。

### **6.2 解決策1：APIレベルでの強制アクティベーション**

最も安全かつ効果的な対策は、Pythonスクリプト側でウィンドウ作成完了を検知した後、明示的にそのウィンドウをアクティブ化し、再開シグナルを送ることである。

async\_create\_window() はウィンドウオブジェクトを返すが、この時点ではまだiTerm2の内部ステートが完全に同期していない可能性がある。以下のコードパターンのように、ウィンドウ取得後に async\_activate() を呼び出すことで、iTerm2に強制的にフォーカスを当てさせ、Paused状態からの復帰（%continue要求）を誘発させることができる16。

Python

import iterm2  
import asyncio

async def main(connection):  
    app \= await iterm2.async\_get\_app(connection)  
      
    \# tmux接続の取得（例）  
    tmux\_conns \= await iterm2.async\_get\_tmux\_connections(connection)  
    if not tmux\_conns:  
        return  
    tmux\_conn \= tmux\_conns

    \# ウィンドウ作成  
    new\_window \= await tmux\_conn.async\_create\_window()  
      
    if new\_window:  
        \# 【対策】作成直後に少し待機し、明示的にアクティブ化する  
        \# これによりiTerm2はフォーカスイベントを処理し、  
        \# 必要に応じてtmuxへrefresh-clientコマンドを送信してPaused状態を解除する  
        await asyncio.sleep(0.1)   
        await new\_window.async\_activate()  
          
        \# さらに念を入れる場合、Escキー等を送ってコピーモードを強制解除する  
        \# ただし、通常の入力モードで送るとシェルにキーが渡るため注意が必要  
        \# await tmux\_conn.async\_send\_command(f"send-keys \-t {new\_window.window\_id} \-X cancel")

iterm2.run\_until\_complete(main)

### **6.3 解決策2：シェル初期化プロセスの軽量化**

根本的な原因が「初期出力のバースト」にある場合、.zshrc や .bashrc の見直しが最も効果的である。

* **対話的実行の判定:** if\]; then... などの条件分岐を用い、tmux内での起動時には重い処理（neofetchや画像表示など）をスキップする、あるいは遅延実行させる。  
* **tmux設定:** .tmux.conf において set \-g history-limit を適切に設定する（極端に大きいとバッファ処理が重くなる場合があるが、逆に小さすぎるとすぐに溢れる）。一般的には 10000〜50000 行程度が推奨される17。

### **6.4 解決策3：Control Mode設定の調整（上級者向け）**

iTerm2の設定により、Control Mode接続時の挙動を調整することも可能である。

* **Preferences \> Advanced:** 「Chunk size for tmux output」などの隠し設定が存在する場合、バッファリングの粒度を調整することで %pause の発生頻度を変えられる可能性があるが、副作用も大きいため慎重な検証が必要である。

## ---

**7\. 結論**

iTerm2とtmux \-CCモードのPython API制御において async\_create\_window() 実行時に発生する「View-Mode」遷移現象は、**Control Modeプロトコルに実装されたフロー制御（Flow Control）メカニズムが、ウィンドウ生成時の出力バーストに反応して発動した結果**であると結論付けられる。

iTerm2は、データ転送の遅延やバッファ溢れを防ぐためにtmuxから送信される %pause 通知を忠実に処理し、該当ペインの更新を停止する。この「停止状態」が、UI上ではコピーモード（View-Mode）として表現されている。これは不具合ではなく、ネットワーク透過性を考慮したtmux Control Modeの設計思想に基づく正常な挙動（Safety Mechanism）であるが、自動化スクリプトにおいては予期せぬ停止として顕在化する。

開発者は、この挙動が「プロトコルレベルでのバッファリング制御」に起因することを理解し、スクリプト側での明示的なアクティベーション（async\_activate）や、シェル初期化プロセスの最適化を通じて、この競合状態を回避する設計を行うことが求められる。

### **引用文献・参照ID**

* iTerm2 Python API 仕様: 2  
* tmux Control Mode プロトコル詳細: 3  
* iTerm2 設定およびView-Mode仕様: 6  
* 関連する不具合とリサイズ問題: 11

以上

#### **引用文献**

1. Example Script — iTerm2 Python API 0.26 documentation, 1月 7, 2026にアクセス、 [https://iterm2.com/python-api/tutorial/example.html](https://iterm2.com/python-api/tutorial/example.html)  
2. Tmux — iTerm2 Python API 0.26 documentation, 1月 7, 2026にアクセス、 [https://iterm2.com/python-api/tmux.html](https://iterm2.com/python-api/tmux.html)  
3. Tmux control mode protocol documentation \- AMP Code, 1月 7, 2026にアクセス、 [https://ampcode.com/threads/T-f02e59f8-e474-493d-9558-11fddf823672?q=tmux](https://ampcode.com/threads/T-f02e59f8-e474-493d-9558-11fddf823672?q=tmux)  
4. Control Mode · tmux/tmux Wiki \- GitHub, 1月 7, 2026にアクセス、 [https://github.com/tmux/tmux/wiki/Control-Mode](https://github.com/tmux/tmux/wiki/Control-Mode)  
5. How to use tmux control mode? \- TmuxAI, 1月 7, 2026にアクセス、 [https://tmuxai.dev/tmux-control-mode/](https://tmuxai.dev/tmux-control-mode/)  
6. Copy Mode \- Documentation \- iTerm2 \- macOS Terminal Replacement, 1月 7, 2026にアクセス、 [https://iterm2.com/documentation-copymode.html](https://iterm2.com/documentation-copymode.html)  
7. tmux Copy and Paste Methods With and Without the Mouse | Baeldung on Linux, 1月 7, 2026にアクセス、 [https://www.baeldung.com/linux/tmux-copy-paste-keyboard-mouse](https://www.baeldung.com/linux/tmux-copy-paste-keyboard-mouse)  
8. Is it possible to change the pane backgroundcolor when in copy mode? \#634 \- GitHub, 1月 7, 2026にアクセス、 [https://github.com/tmux/tmux/issues/634](https://github.com/tmux/tmux/issues/634)  
9. TMUX change status bar in Copy Mode... \- Reddit, 1月 7, 2026にアクセス、 [https://www.reddit.com/r/tmux/comments/1g19wtp/tmux\_change\_status\_bar\_in\_copy\_mode/](https://www.reddit.com/r/tmux/comments/1g19wtp/tmux_change_status_bar_in_copy_mode/)  
10. Customizing Your Terminal with Oh My Zsh Themes and Plugins \- OpenReplay Blog, 1月 7, 2026にアクセス、 [https://blog.openreplay.com/customizing-terminal-oh-my-zsh-themes-plugins/](https://blog.openreplay.com/customizing-terminal-oh-my-zsh-themes-plugins/)  
11. Starting new tmux session in native tab unexpectedly resizes window (\#6551) · Issue · gnachman/iterm2 \- GitLab, 1月 7, 2026にアクセス、 [https://gitlab.com/gnachman/iterm2/-/issues/6551](https://gitlab.com/gnachman/iterm2/-/issues/6551)  
12. Getting back old copy paste behaviour in tmux, with mouse \- Stack Overflow, 1月 7, 2026にアクセス、 [https://stackoverflow.com/questions/17445100/getting-back-old-copy-paste-behaviour-in-tmux-with-mouse](https://stackoverflow.com/questions/17445100/getting-back-old-copy-paste-behaviour-in-tmux-with-mouse)  
13. Scroll in tmux but don't enter copy mode? \- Super User, 1月 7, 2026にアクセス、 [https://superuser.com/questions/552257/scroll-in-tmux-but-dont-enter-copy-mode](https://superuser.com/questions/552257/scroll-in-tmux-but-dont-enter-copy-mode)  
14. Tmux – The Essentials (2019) \- Hacker News, 1月 7, 2026にアクセス、 [https://news.ycombinator.com/item?id=43261600](https://news.ycombinator.com/item?id=43261600)  
15. tmux Integration \- Documentation \- iTerm2 \- macOS Terminal Replacement, 1月 7, 2026にアクセス、 [https://iterm2.com/documentation-tmux-integration.html](https://iterm2.com/documentation-tmux-integration.html)  
16. Window — iTerm2 Python API 0.26 documentation, 1月 7, 2026にアクセス、 [https://iterm2.com/python-api/window.html](https://iterm2.com/python-api/window.html)  
17. How I Learned TMUX & Became A Workflow Ninja | by M. Hammad Hassan \- Medium, 1月 7, 2026にアクセス、 [https://medium.com/@hammad.ai/how-i-learned-tmux-became-a-workflow-ninja-7d33cc796793](https://medium.com/@hammad.ai/how-i-learned-tmux-became-a-workflow-ninja-7d33cc796793)  
18. App — iTerm2 Python API 0.26 documentation, 1月 7, 2026にアクセス、 [https://iterm2.com/python-api/app.html](https://iterm2.com/python-api/app.html)  
19. iTerm2/api/library/python/iterm2/iterm2/\_\_init\_\_.py at master \- GitHub, 1月 7, 2026にアクセス、 [https://github.com/gnachman/iTerm2/blob/master/api/library/python/iterm2/iterm2/\_\_init\_\_.py](https://github.com/gnachman/iTerm2/blob/master/api/library/python/iterm2/iterm2/__init__.py)  
20. General Preferences \- Documentation \- iTerm2 \- macOS Terminal Replacement, 1月 7, 2026にアクセス、 [https://iterm2.com/documentation-preferences-general.html](https://iterm2.com/documentation-preferences-general.html)  
21. Preferences \- Documentation \- iTerm2 \- macOS Terminal Replacement, 1月 7, 2026にアクセス、 [https://iterm2.com/3.0/documentation-preferences.html](https://iterm2.com/3.0/documentation-preferences.html)  
22. iTerm2 tmux Integration \- trzsz, 1月 7, 2026にアクセス、 [https://trzsz.github.io/tmuxcc.html](https://trzsz.github.io/tmuxcc.html)  
23. ranger \- Linux Manuals (1) \- SysTutorials, 1月 7, 2026にアクセス、 [https://www.systutorials.com/docs/linux/man/1-ranger/](https://www.systutorials.com/docs/linux/man/1-ranger/)  
24. How to set the color of tmux copy-mode's highlight? \- Stack Overflow, 1月 7, 2026にアクセス、 [https://stackoverflow.com/questions/39327292/how-to-set-the-color-of-tmux-copy-modes-highlight](https://stackoverflow.com/questions/39327292/how-to-set-the-color-of-tmux-copy-modes-highlight)  
25. New windows are always created with the first window's path · Issue \#90 · tmux-plugins/tmux-resurrect \- GitHub, 1月 7, 2026にアクセス、 [https://github.com/tmux-plugins/tmux-resurrect/issues/90](https://github.com/tmux-plugins/tmux-resurrect/issues/90)