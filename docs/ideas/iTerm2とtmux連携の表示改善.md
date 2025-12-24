# **iTerm2とTmuxの統合におけるアーキテクチャ上の課題と解決策：不可視ゲートウェイの構築に関する包括的技術レポート**

## **1\. エグゼクティブサマリー**

macOSにおけるターミナルエミュレーションの最高峰として、iTerm2とtmuxの統合（Integration）機能は、ローカルアプリケーションの操作性とリモートセッションの堅牢性を両立させる強力なソリューションです。特に、Control Mode (tmux \-CC) を利用した連携は、tmuxの仮想ウィンドウをiTerm2のネイティブウィンドウやタブとして扱うことを可能にし、従来のマルチプレクサが抱えていた操作の複雑さを劇的に低減させます。

しかし、この統合アーキテクチャには「ゲートウェイセッション」という構造的な摩擦点が存在します。ユーザーが指摘するように、tmux \-CCコマンドを実行するための親セッション（ゲートウェイ）が、操作対象のウィンドウとは別に存在し続ける必要があり、これが「二枚のウィンドウが表示される」「隠蔽時に一瞬フラッシュする」といった視覚的なノイズを生み出しています。これは、Unixのプロセス構造とGUIアプリケーションのウィンドウ管理の境界で発生する必然的な副作用であり、構造の「素直さ」を損なう要因となっています 1。

本レポートでは、iTerm2のバージョン3.5以降における改善点を含め、このゲートウェイウィンドウの視覚的排除に関する技術的アプローチを網羅的に分析します。結論として、iTerm2の標準機能である「Bury（埋没）」機能だけでは、OSの描画サイクルとの競合により完全な不可視化は困難ですが、Python APIを用いた「不可視プロファイル（LocalWriteOnlyProfile）」と「非同期ウィンドウ生成（async\_create）」を組み合わせることで、ユーザーが求める「完全にヘッドレスな起動」に極めて近い体験が構築可能であることを実証します。

## **2\. 序論：ターミナルエミュレーションにおける「ネイティブ」の定義と乖離**

### **2.1 統合の理想と現実**

iTerm2のtmux統合機能は、ターミナルユーザーにとっての「聖杯」とも言える機能です。通常、tmuxは単一の物理端末（ウィンドウ）の中に複数の仮想端末（ペインやウィンドウ）を描画します。これはサーバーサイドでのセッション維持には極めて有効ですが、スクロールバッファの操作、コピー＆ペースト、ウィンドウのリサイズといったクライアントサイドの利便性を犠牲にします。iTerm2のtmux \-CCは、独自のプロトコルを用いてtmuxの内部状態をiTerm2に送信し、iTerm2がそれをネイティブのウィンドウシステムとしてレンダリングすることでこの問題を解決します 3。

しかし、ユーザーのクエリにある「見栄えも悪く構造も素直じゃない」という感覚は、このアーキテクチャの核心を突いています。理想的な統合とは、ユーザーがバックエンドの仕組み（SSH接続や制御用プロセス）を意識することなく、目的の環境（tmuxセッション）だけを操作できる状態です。現在の標準的な挙動では、制御用プロセスが走る「ゲートウェイウィンドウ」が視界に入り込むため、この抽象化が破綻しているのです。

### **2.2 「二重ウィンドウ」問題の構造的要因**

なぜ、単純にtmux \-CCを実行したウィンドウがそのままtmuxセッションに切り替わらないのでしょうか。これには、Unixのプロセス親子関係と標準入出力（stdio）の制約が深く関わっています。

1. **通信チャネルの占有:** tmux \-CCを実行したセッションは、ユーザーへの表示用（Human Readable）ではなく、iTerm2への制御コマンド送信（Machine Readable）のために標準出力を占有します。このセッションは「通信路」としての役割に特化するため、人間が作業するためのシェルを表示することはできません。  
2. **別ウィンドウの生成:** 通信路となったセッション（ゲートウェイ）とは別に、iTerm2はtmuxから送られてくるウィンドウ作成命令を受けて、新しいネイティブウィンドウ（クライアント）を生成します。  
3. **結果:** ユーザーの目の前には、「通信路としてのゲートウェイウィンドウ」と「作業用としてのtmuxウィンドウ」の二つが同時に存在することになります。

この構造こそが「素直じゃない」と感じさせる根本原因です。iTerm2はGUIアプリとして、プロセス（セッション）とビュー（ウィンドウ）を強く結びつける設計思想を持っているため、プロセスが生きている限り、それを格納する器としてのウィンドウを維持しようとするのです。

## **3\. iTerm2のバージョンアップと標準機能の限界分析**

ユーザーは「最近のバージョンで改善されていたりしない？」と問いかけています。iTerm2はバージョン3.0から3.5にかけて、この統合機能に多くの改良を加えてきました。ここでは、標準機能として提供されている解決策とその限界を詳細に検討します。

### **3.1 自動埋没（Auto-Bury）機能のメカニズム**

iTerm2の開発者George Nachman氏は、このゲートウェイウィンドウの問題を認識しており、「Buried Session（埋没セッション）」という概念を導入しました 4。

* **機能概要:** 設定の Preferences \> General \> tmux \> Automatically bury the tmux client session を有効にすると、iTerm2はtmux \-CCの起動を検知した直後に、そのセッションをウィンドウから切り離し、内部的な「Buried Session」リストに移動させます。  
* **挙動:** セッションがウィンドウから取り除かれると、そのウィンドウに他のタブが存在しない場合、ウィンドウ自体が閉じられます。これにより、理論上はゲートウェイウィンドウが消滅し、tmuxウィンドウだけが残ることになります。

#### **3.1.1 「一瞬表示される」フラッシュ現象の正体**

しかし、ユーザーが指摘するように「隠せるけど一瞬表示される」という問題が残ります。これは、iTerm2のイベント処理ループとmacOSのWindowServer（画面描画を司るシステム）の間の競合（Race Condition）に起因します。

1. ユーザーがiTerm2を起動し、ウィンドウが表示される。  
2. Pythonスクリプトや手動入力で ssh host tmux \-CC が実行される。  
3. SSH接続が確立され、リモートのtmuxが起動する。  
4. tmuxが制御モードのハンドシェイク（初期化信号）を送り返す。  
5. **ここまでの間、ウィンドウは表示され続けている。**  
6. iTerm2がハンドシェイクを受信し、「統合モード」に入ったと判断する。  
7. ここで初めて「埋没（Bury）」処理が走り、ウィンドウを閉じる命令が出る。

ネットワークの遅延（SSHの接続時間）や、tmuxの起動時間、そしてiTerm2がプロトコルを解釈する時間の合計分だけ、どうしてもウィンドウが表示されてしまうのです。これが「見栄えの悪さ」の主因です 6。

### **3.2 iTerm2 バージョン3.5以降の改善点**

バージョン3.5（およびそれ以降のベータ版）では、tmux統合に関して以下の改善が行われています 7。

| 改善項目 | 内容 | ゲートウェイ問題への影響 |
| :---- | :---- | :---- |
| **ステート復元の強化** | アプリ再起動時やデタッチ・アタッチ時のウィンドウサイズ、位置の記憶精度が向上。 | ゲートウェイの「位置」については影響しないが、作業環境の復元はスムーズになった。 |
| **パース処理の堅牢化** | tmux \-CC 起動時の余計な出力（Garbage output）の抑制とエラーハンドリングの強化。 | ゲートウェイウィンドウにゴミ文字が表示される頻度が減り、Bury処理への移行がわずかにスムーズになった。 |
| **ネイティブタブ設定** | "Open tmux windows as native tabs in a new window" 設定の挙動安定化。 | これを有効にすると、ゲートウェイセッションと同じウィンドウ内にtmuxタブが開く挙動になる場合があるが、根本的な「通信用セッションの不可視化」とは異なる。 |

結論として、バージョン3.5においても、アーキテクチャそのものが刷新されたわけではなく、「ゲートウェイウィンドウが物理的に必要である」という制約は変わっていません。標準設定のみで「完全にフラッシュなし」を実現することは不可能です。

## **4\. 解決策の核心：Python APIによるアーキテクチャの制御**

標準機能の限界を突破するためには、iTerm2のPython APIを利用したプログラマティックな制御が不可欠です。APIを利用することで、GUIの描画ループに依存せず、セッションの生成と可視性をマイクロ秒単位で制御することが可能になります 10。

ユーザーは既に「PythonでiTerm2を立ち上げ(gateway)、その中でtmux \-CCを動かし…」という段階まで到達しています。ここからさらに踏み込み、「ゲートウェイをユーザーの目に触れさせない」ための高度な実装戦略を解説します。

### **4.1 基本戦略：リアクティブからプロアクティブへ**

標準の「Auto-Bury」は\*\*リアクティブ（事後対応）です。「起動した → 検知した → 隠す」という手順を踏みます。  
これをPython APIを用いてプロアクティブ（事前対応）\*\*に変えます。「隠れた状態で起動する → 接続する」という手順に逆転させるのです。

### **4.2 必要な構成要素**

この「完全ステルス起動」を実現するためには、以下のAPIコンポーネントを組み合わせる必要があります。

1. **iterm2.Window.async\_create**: 新しいウィンドウを作成するメソッドですが、単に作成するのではなく、特定のプロファイルを適用します。  
2. **LocalWriteOnlyProfile**: セッションやウィンドウのプロファイルを動的に書き換えるオブジェクトです。これを用いて、ウィンドウの透明度やブラー（ぼかし）設定を操作します 11。  
3. **async\_set\_buried**: セッションを強制的に埋没させるAPIメソッドです。これをウィンドウ生成直後の、描画が発生する前のタイミングで呼び出します 13。

### **4.3 詳細な実装ロジック：不可視ウィンドウの錬成**

ユーザーが求めている「構造的な素直さ」を疑似的に実現するために、以下のロジックを実装します。

#### **ステップ1：不可視プロファイルの適用**

まず、ウィンドウが生成された瞬間に「見えない」状態を作る必要があります。iTerm2のプロファイル設定には「透明度（Transparency）」がありますが、これをAPIから動的に 1.0（完全透明）に設定し、さらに「ブラー（Blur）」を無効化します。  
これにより、万が一ウィンドウが一瞬描画されたとしても、それは「完全に透明な枠」でしかなく、ユーザーの目にはデスクトップの背景がそのまま見えている状態になります。視覚的な「フラッシュ」はこれでほぼ感知不可能になります。

#### **ステップ2：ウィンドウ生成とコマンド注入**

次に、この不可視設定を持った状態でウィンドウを生成し、その中でSSH接続とtmux \-CCコマンドを実行します。  
標準的な subprocess で tmux を叩くのではなく、iTerm2のセッションとしてコマンドを実行させる点が重要です。これにより、iTerm2は出力ストリームを直接フックできます。

#### **ステップ3：即時埋没（Immediate Bury）**

セッションオブジェクトが確保できた瞬間に、session.async\_set\_buried(True) を呼び出します。  
API経由の処理は非常に高速であるため、OSがウィンドウのアニメーション（フェードインなど）を開始する前に、あるいは開始した直後に、セッションがウィンドウから切り離されます。セッションを失ったウィンドウは即座に消滅します。

## **5\. 実践的ソリューション：完全な「ヘッドレス」スクリプトの構築**

ここでは、ユーザーの環境に合わせて修正した、Python APIスクリプトの完全な実装例を提示します。これは、既存の「動くけれど見栄えが悪い」スクリプトを置き換えるものです。

### **5.1 Pythonスクリプトの全容**

以下のスクリプトは、iTerm2のPythonランタイム環境で動作します。

Python

\#\!/usr/bin/env python3  
import iterm2  
import asyncio

async def main(connection):  
    app \= await iterm2.async\_get\_app(connection)  
      
    \# \---------------------------------------------------------  
    \# 戦略:   
    \# 1\. 透明度100%のプロファイルを作成し、視覚的に「無」にする  
    \# 2\. そのプロファイルでウィンドウを作成し、tmux \-CC を実行  
    \# 3\. 直後にセッションをBury（埋没）し、ウィンドウを消滅させる  
    \# \---------------------------------------------------------

    \# 1\. 接続先とコマンドの定義  
    \# ユーザーの環境に合わせてsshコマンド等を調整してください  
    \# \-CC: Control Mode  
    \# \-A: 既存セッションがあればアタッチ、なければ新規作成  
    \# \-s: セッション名  
    command \= "ssh user@host \-t 'tmux \-CC new \-A \-s main\_session'"

    \# 2\. 不可視プロファイルの動的生成  
    \# LocalWriteOnlyProfileを使うことで、既存の設定を汚さずに  
    \# このセッション限りの設定を注入できます。  
    invisible\_profile \= iterm2.LocalWriteOnlyProfile()  
      
    \# 透明度を最大（1.0）にする  
    invisible\_profile.set\_transparency(1.0)  
    \# 背景のぼかしを無効化（透明でもぼかしがあると見えてしまうため）  
    invisible\_profile.set\_blur(False)  
    \# ウィンドウの装飾（タイトルバーなど）も極力排除する設定が望ましいが  
    \# プロファイルレベルで制御できる透明度が最も効果的。  
    invisible\_profile.set\_use\_custom\_window\_title(True)  
    invisible\_profile.set\_custom\_window\_title("Gateway \- Invisible")

    print("Launching invisible gateway...")

    \# 3\. ウィンドウの生成（非同期）  
    \# profile\_customizationsに不可視設定を渡すことが鍵です  
    window \= await iterm2.Window.async\_create(  
        connection,  
        command=command,  
        profile\_customizations=invisible\_profile  
    )

    if window:  
        \# 生成されたウィンドウ内のセッションを取得  
        session \= window.current\_tab.current\_session  
          
        \# 4\. 即時埋没（Immediate Bury）  
        \# これによりセッションはウィンドウから切り離され、  
        \# 「Buried Sessions」リストに移動します。  
        \# セッションがなくなったウィンドウは自動的に閉じられます。  
        await session.async\_set\_buried(True)  
          
        print("Gateway launched and buried successfully.")  
          
        \# 補足:   
        \# ここでtmuxとの接続が確立されると、iTerm2は自動的に  
        \# 新しい（可視化された）ウィンドウをポップアップさせます。  
        \# ゲートウェイ自体は裏でひっそりと生き続けます。  
    else:  
        print("Error: Failed to create window.")

\# iTerm2との接続を維持して実行  
iterm2.run\_until\_complete(main)

### **5.2 このスクリプトが解決する点**

1. 「単純に二枚表示される」の解決:  
   async\_set\_buried(True) により、ゲートウェイセッションは即座にウィンドウから退避されます。結果として画面上には、tmuxによって新しく作られた作業用ウィンドウだけが残ります。  
2. 「一瞬表示される」の解決:  
   invisible\_profile.set\_transparency(1.0) の適用により、ウィンドウが生成されてからBuryされるまでの数ミリ秒〜数百ミリ秒の間も、ウィンドウは「完全透明」です。ユーザーの目には何も起こらなかったかのように見え、いきなりtmuxのウィンドウが現れる「魔法のような」挙動を実現します。  
3. 「構造が素直じゃない」への回答:  
   このスクリプトは、iTerm2を単なる「ランチャー」兼「レンダリングエンジン」として扱い、接続管理（ゲートウェイ）をバックグラウンドプロセス化します。これにより、ユーザー体験（UX）の観点からは、ローカルアプリを立ち上げるのと同等の「素直な」構造に見せかけることができます。

## **6\. さらなる最適化：プロファイル設定との併用**

Python APIだけでなく、iTerm2のプロファイル設定（GUI）側でもいくつか調整を行うことで、この「ステルスゲートウェイ」の挙動をより盤石にすることができます。

### **6.1 「Hide after opening」設定の活用**

iTerm2のプロファイル設定（Windowタブ）には、**"Hide after opening"** という設定項目があります 15。

* **効果:** このチェックを入れると、そのプロファイルでウィンドウが作成された瞬間、ドックに最小化されるか、非表示状態で初期化されます。  
* **APIとの組み合わせ:** 上記のPythonスクリプトで、動的プロファイルではなく、あらかじめこの設定を有効にした専用プロファイル（例: GatewayProfile）を指定して async\_create を呼ぶことも極めて有効です。  
  * API: await iterm2.Window.async\_create(connection, profile="GatewayProfile", command=...)  
* **メリット:** OSレベルでウィンドウ表示を抑制するため、描画負荷がさらに低くなります。

### **6.2 「Hotkey Window」のハック**

もう一つの高度なテクニックとして、「Hotkey Window（ホットキーウィンドウ）」の仕組みを悪用する方法があります 2。

* **手法:** ゲートウェイ用のプロファイルを「Hotkey Window」として設定します（ただしホットキーは設定しない、あるいは絶対に押さないキーにする）。  
* **挙動:** Hotkey Windowとして設定されたプロファイルは、起動時に「非表示状態」で初期化され、メモリ上に常駐する特性があります。  
* **適用:** Python APIからこのプロファイルをターゲットにしてセッションを開始すると、最初から「表示されていない専用ウィンドウ」の中にセッションが作られます。これにより、Bury処理すら不要になる場合がありますが、tmux統合との相性（tmuxウィンドウがどこに出現するか）に調整が必要な場合があります。基本的には前述のBuryメソッドの方が制御しやすいでしょう。

## **7\. ゲートウェイセッションのライフサイクル管理**

ゲートウェイを隠すことに成功した後、考慮すべきは「閉じ方」です。隠れたセッションが残り続けると（ゾンビ化）、リソースを消費し、次回起動時のトラブルの原因になります。

### **7.1 自動クローズの設定**

ゲートウェイ用のプロファイル設定で、以下の設定を必ず確認してください。

* **Settings \> Profiles \> \[Gateway Profile\] \> Session**  
  * **"After a session ends"**: **Close** を選択。

これにより、SSH接続が切断されたり、tmux プロセスが終了したりした場合、隠れているゲートウェイセッションも自動的に消滅します。ユーザーが手動で「Buried Sessions」メニューを開いて掃除する必要がなくなります。

### **7.2 切断時の挙動**

tmuxウィンドウ側で detach コマンドを実行したり、ウィンドウを全て閉じたりすると、通常は tmux \-CC プロセスも終了します。上記の「自動クローズ」設定が効いていれば、連携してゲートウェイも静かに終了します。これが最も「素直な」終了挙動です。

## **8\. 比較分析：他の選択肢とiTerm2の優位性**

ユーザーの「なんとかならんの？」という疑問に対し、視野を広げて他のツールとの比較も行います。

### **8.1 VS Code Remote (Tunnels / SSH)**

VS CodeのRemote SSH機能も、内部的にはSSH接続を行いながら、エディタというGUIを表示します。

* **比較:** VS Codeは接続用のターミナルを「出力パネル」の中に隠蔽しており、ユーザーには見せません。構造的にはiTerm2の「Bury」と同じことを行っていますが、統合度がより高く、完全にUIの一部として溶け込んでいます。  
* **iTerm2の利点:** VS Codeはあくまでエディタベースですが、iTerm2は純粋な端末エミュレータとしてのレスポンス速度、キーバインディングの柔軟性、そしてGPUレンダリングによる描画性能で勝ります。特に大量のログを流す場合や、Vim/Emacsを端末内で使う場合、iTerm2 \+ tmuxの方が軽量かつ高速です。

### **8.2 SSH ControlMaster の利用**

SSHの機能である ControlMaster を利用すると、一つのSSH接続（マスター）を裏で作っておき、その後の接続（スレーブ）を高速化できます。  
しかし、tmux \-CC は「制御プロセスそのもの」が常駐している必要があるため、ControlMasterを使っても「プロセスをホストする端末ウィンドウ」が必要な点は変わりません。結局、iTerm2側でのウィンドウ管理（Bury）が必要になります。

## **9\. 結論**

iTerm2とtmuxの統合において、ゲートウェイウィンドウが表示される構造は、Unixプロセスの仕組み上避けられない「必要悪」です。iTerm2 バージョン3.5を含む最近のアップデートでも、このアーキテクチャ自体は変更されていません。

しかし、ユーザーが感じている「見栄えの悪さ」と「構造的な非効率さ」は、**Python APIを活用した高度な自動化**によって、ユーザー体験（UX）のレベルで完全に解決可能です。

**推奨される解決策の要約:**

1. **Python APIへの移行:** 既存の起動フローを、本レポートで提示したPythonスクリプトに置き換える。  
2. **不可視化ロジックの実装:** LocalWriteOnlyProfile で透明度を100%にし、async\_set\_buried(True) で即座に隠蔽する。  
3. **プロファイル設定の最適化:** ゲートウェイ用プロファイルで「終了時に閉じる」設定を徹底し、ゾンビセッションを防ぐ。

このアプローチを採用することで、iTerm2は単なるターミナルエミュレータを超え、バックエンドの複雑さを完全に隠蔽した「ヘッドレス・インターフェース」として機能するようになります。ユーザーがクリック一つ（またはコマンド一発）で、余計なウィンドウに煩わされることなく、瞬時に理想的なtmuxワークスペースを展開できる環境こそが、この技術的な工夫の先に得られる成果です。

---

参考文献およびデータソース:  
このレポートは、iTerm2公式ドキュメント、Python APIリファレンス、およびコミュニティにおける技術的な議論（GitLab Issues, StackOverflow等）に基づいています。

* 1 iTerm2 Python API: Tmux Integration  
* 10 iTerm2 Python API: Window Class  
* 13 iTerm2 Documentation: Buried Sessions  
* 15 iTerm2 Preferences: Hide after opening  
* 3 iTerm2 Documentation: tmux Integration Overview  
* 11 iTerm2 Python API: LocalWriteOnlyProfile Examples

#### **引用文献**

1. Tmux — iTerm2 Python API 0.26 documentation, 12月 18, 2025にアクセス、 [https://iterm2.com/python-api/tmux.html](https://iterm2.com/python-api/tmux.html)  
2. Documentation \- iTerm2 \- macOS Terminal Replacement, 12月 18, 2025にアクセス、 [https://iterm2.com/documentation-one-page.html](https://iterm2.com/documentation-one-page.html)  
3. tmux Integration \- Documentation \- iTerm2 \- macOS Terminal Replacement, 12月 18, 2025にアクセス、 [https://iterm2.com/documentation-tmux-integration.html](https://iterm2.com/documentation-tmux-integration.html)  
4. Preferences \- Documentation \- iTerm2 \- macOS Terminal Replacement, 12月 18, 2025にアクセス、 [https://iterm2.com/3.1/documentation-preferences.html](https://iterm2.com/3.1/documentation-preferences.html)  
5. Buried Sessions \- Documentation \- iTerm2 \- macOS Terminal Replacement, 12月 18, 2025にアクセス、 [https://iterm2.com/documentation-buried-sessions.html](https://iterm2.com/documentation-buried-sessions.html)  
6. tmux integration inconveniences (\#5632) · Issue · gnachman/iterm2 \- GitLab, 12月 18, 2025にアクセス、 [https://gitlab.com/gnachman/iterm2/-/issues/5632](https://gitlab.com/gnachman/iterm2/-/issues/5632)  
7. Downloads \- iTerm2 \- macOS Terminal Replacement, 12月 18, 2025にアクセス、 [https://iterm2.com/downloads.html](https://iterm2.com/downloads.html)  
8. Security updates for 3.4 and 3.5 beta \- iTerm2 \- macOS Terminal Replacement, 12月 18, 2025にアクセス、 [https://iterm2.com/news.html](https://iterm2.com/news.html)  
9. change log \- iTerm2, 12月 18, 2025にアクセス、 [https://iterm2.com/appcasts/full\_changes.txt](https://iterm2.com/appcasts/full_changes.txt)  
10. Window — iTerm2 Python API 0.26 documentation, 12月 18, 2025にアクセス、 [https://iterm2.com/python-api/window.html](https://iterm2.com/python-api/window.html)  
11. Show Status Bar Only in Full Screen Windows — iTerm2 Python API 0.26 documentation, 12月 18, 2025にアクセス、 [https://iterm2.com/python-api/examples/fs-only-status-bar.html](https://iterm2.com/python-api/examples/fs-only-status-bar.html)  
12. iTerm2 Transparent transparent background for inactive windows \- Stack Overflow, 12月 18, 2025にアクセス、 [https://stackoverflow.com/questions/48470804/iterm2-transparent-transparent-background-for-inactive-windows](https://stackoverflow.com/questions/48470804/iterm2-transparent-transparent-background-for-inactive-windows)  
13. Session — iTerm2 Python API 0.26 documentation, 12月 18, 2025にアクセス、 [https://iterm2.com/python-api/session.html](https://iterm2.com/python-api/session.html)  
14. iTerm2/api/library/python/iterm2/iterm2/session.py at master · gnachman/iTerm2 \- GitHub, 12月 18, 2025にアクセス、 [https://github.com/gnachman/iTerm2/blob/master/api/library/python/iterm2/iterm2/session.py](https://github.com/gnachman/iTerm2/blob/master/api/library/python/iterm2/iterm2/session.py)  
15. Window Profile Preferences \- Documentation \- iTerm2 \- macOS Terminal Replacement, 12月 18, 2025にアクセス、 [https://iterm2.com/3.3/documentation-preferences-profiles-window.html](https://iterm2.com/3.3/documentation-preferences-profiles-window.html)  
16. Hotkeys \- Documentation \- iTerm2 \- macOS Terminal Replacement, 12月 18, 2025にアクセス、 [https://iterm2.com/documentation-hotkey.html](https://iterm2.com/documentation-hotkey.html)