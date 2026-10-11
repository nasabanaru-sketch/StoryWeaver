# StoryWeaver Live — 完全ローカル構築 実装計画書

- **作成日**: 2026-10-03
- **ステータス**: 承認待ち
- **対象マシン**: ThinkPad X1 Extreme (RTX 3080 Laptop 16GB / RAM 32GB / Windows)

> [!IMPORTANT]
> 本計画書は `Attached_doc/storyweaver_live.md` の仕様を実現するための **全工程ロードマップ** です。
> 各 Phase の末尾に **Phase Gate（関門チェック）** を設けています。
> Gate を通過できない場合は **次の Phase に進まず、必ず問題を解決** してください。

---

## 現在の環境スナップショット (2026-10-03 確認済み)

| 項目 | 状態 |
| :--- | :--- |
| GPU | NVIDIA GeForce RTX 3080 Laptop GPU — **16,384 MiB** ✅ |
| NVIDIA Driver | 610.47 ✅ |
| RAM | 約 32 GB (空き ≈ 18 GB) ✅ |
| ディスク空き (C:) | 約 130 GB ✅ （モデル合計 ≈ 15 GB 必要） |
| Python | 3.11.6 ✅ |
| Pinokio | **未インストール** 🔴 → Phase 1 で導入 |
| Ollama | **未インストール** 🔴 → Phase 2 で導入 |

---

## 全体フロー図

```mermaid
graph LR
    P1["Phase 1\nComfyUI 基盤構築\n(Pinokio + モデル配置)"]
    G1{{"🚧 Gate 1\nComfyUI で\nテスト画像生成"}}
    P2["Phase 2\nOllama 導入\n(LLM ローカル稼働)"]
    G2{{"🚧 Gate 2\nOllama で\nJSON 生成確認"}}
    P3["Phase 3\nComfyUI 画像生成基盤刷新\n(Mage-Flow / FLUX.2 Klein)\n+ 条件付きFaceDetailer"]
    G3{{"🚧 Gate 3\n人物転生・動的構図\np95 ≤ 30s / VRAM ≤ 13GB"}}
    P4["Phase 4\nFastAPI\nオーケストレーター構築"]
    G4{{"🚧 Gate 4\nAPI 単体テスト\n全エンドポイント正常"}}
    P5["Phase 5\nフロントエンド UI\n構築・接続"]
    G5{{"🚧 Gate 5\nブラウザから\nEnd-to-End 生成成功"}}
    P6["Phase 6\n展示本番チューニング\n& リハーサル"]
    G6{{"🚧 Gate 6\n連続10回生成\nOOM・ハングなし"}}

    P1 --> G1 --> P2 --> G2 --> P3 --> G3 --> P4 --> G4 --> P5 --> G5 --> P6 --> G6
```

---

## VRAM 配分計画（常に意識すること）

> [!IMPORTANT]
> **2026-10-10 改訂（Phase 3 アーキテクチャ刷新）**:
> 従来の「ComfyUI + Ollama 常時同時ロード（合計 14.4 GB / マージン 0.1 GB の極限状態）」を撤廃し、**Ollama 直列化・即時アンロード（`keep_alive: 0`）** を採用しました。
> これにより、LLM 推論時と画像生成時で GPU メモリを排他利用し、展示中の OOM リスクを根本から排除しています。

```
【フェーズ A: LLM シーン生成時 (Ollama)】
┌─────────────────────────────────────────────────────┐
│  OS / ディスプレイドライバ             :  1.5 GB    │
│  Ollama: gemma4:e2b (または qwen2.5:3b):  2.2 GB    │
│  ─── 使用量合計 ───────────────────── :  3.7 GB    │
│  安全マージン                          : 12.6 GB    │
└─────────────────────────────────────────────────────┘
  ※ keep_alive: 0 により、JSON 生成直後に VRAM からモデルを即時解放

【フェーズ B: アニメ画像生成時 (ComfyUI)】
┌─────────────────────────────────────────────────────┐
│  OS / ディスプレイドライバ             :  1.5 GB    │
│  ComfyUI:                                           │
│    - Option A: Mage-Flow-Edit-Turbo (Int8)          │
│        (DiT 4.16GB + Qwen3-VL 8.88GB 動的オフロード):  9.3 GB    │
│        + 条件付き FaceDetailer (発火時のみ) :  0.4 GB    │
│        + VAE / 一時バッファ                 :  1.2 GB    │
│    - Option B: FLUX.2 Klein 4B (Distilled FP8)      │
│        (Klein 4B FP8 4.3GB + Qwen3 4B 4.2GB):  7.8 GB    │
│        + 条件付き FaceDetailer (発火時のみ) :  0.4 GB    │
│        + VAE / 一時バッファ                 :  1.0 GB    │
│  ─── 小計 (OS 含むピーク) ─────────── : 10.7〜12.4 GB│
│  安全マージン                          :  3.9〜 5.6 GB│
└─────────────────────────────────────────────────────┘
  RTX 3080 16GB の安全上限 14.5 GB に対し、常時 3.9 GB 以上の動的バッファを確保
```

> [!CAUTION]
> 全 Phase を通じて `nvidia-smi` で VRAM 使用量を常に確認する習慣をつけてください。
> **14.5 GB を超えたら危険域** です。

> [!TIP]
> 詳細なメモリ測定基準、モデル別 VRAM 解析、Ollama 直列化の設計根拠は [phase3_revision_plan.md](file:///c:/antigravity/StoryWeaver/docs/plans/phase3_revision_plan.md) を参照してください。

---

---

# Phase 1: ComfyUI 基盤構築（Pinokio 経由）

**目的**: Pinokio をインストールし、ComfyUI を起動して「テキストからアニメ画像を1枚生成できる」状態にする。

## Step 1-1: Pinokio のインストール

1. ブラウザで https://pinokio.computer にアクセスし、**Windows 版インストーラー** をダウンロード
2. インストーラーを実行し、デフォルト設定でインストール
3. Pinokio を起動する

### ✅ 確認ポイント
- Pinokio のホーム画面（ダッシュボード）がブラウザに表示されること

## Step 1-2: Pinokio 上で ComfyUI をインストール

1. Pinokio のダッシュボードで **「Discover」** タブをクリック
2. 検索窓に **「ComfyUI」** と入力
3. **ComfyUI** を見つけて **「Download」→「Install」** をクリック
4. インストールが完了するまで待つ（数分〜10分程度）

### ✅ 確認ポイント
- Pinokio のアプリ一覧に **ComfyUI** が表示される
- 「Start」ボタンが有効になっている

## Step 1-3: ComfyUI の初回起動テスト

1. Pinokio から ComfyUI の **「Start」** をクリック
2. ブラウザで **`http://localhost:8188`** が自動的に開くのを確認

### ✅ 確認ポイント
- ComfyUI の Web UI が表示される（ノードベースのキャンバスが見える）
- 右上にキュー（Queue Prompt）ボタンがある

## Step 1-4: ComfyUI Manager のインストール

ComfyUI Manager は、後でカスタムノード（InstantID 等）を簡単にインストールするために **必須** です。

1. ComfyUI の Web UI で上部メニューを確認
2. もし **「Manager」** ボタンが既にあれば → この Step はスキップ
3. なければ Pinokio の ComfyUI 設定ページで「ComfyUI-Manager」を追加インストール

> [!TIP]
> Pinokio 経由でインストールした場合、ComfyUI Manager が最初から含まれていることが多いです。
> 上部に「Manager」ボタンがあればOK。

### ✅ 確認ポイント
- ComfyUI 画面上部に **「Manager」** ボタンが表示される

## Step 1-5: Animagine XL v3.1 (FP8) チェックポイントの配置

**ここが最も重要なモデル配置です。** FP8 版を使うことで VRAM を大幅に節約します。

1. **ダウンロード先**: Civitai または Hugging Face から `animagineXL_v31.safetensors` の **FP8 量子化版** を入手
   - 検索キーワード: `Animagine XL v3.1 FP8`
   - ファイルサイズ: 約 **5〜6 GB**（FP16版は約10GBなので間違えないこと）
2. **配置先ディレクトリ**: Pinokio の ComfyUI フォルダ内の `models/checkpoints/` にコピー
   ```
   (Pinokioインストール先)/api/comfyui.default/models/checkpoints/animagineXL_v31.safetensors
   ```

> [!WARNING]
> **FP16 版（約10GB）を絶対に使わないでください。** RTX 3080 Laptop 16GB では InstantID と同時起動時に OOM が確実に発生します。
> ファイルサイズで必ず確認: **FP8 版 ≈ 5〜6 GB** / FP16 版 ≈ 10 GB。

### ✅ 確認ポイント
- ファイルが `models/checkpoints/` に存在する
- ComfyUI の「Load Checkpoint」ノードのドロップダウンに `animagineXL_v31` が表示される

## Step 1-6: SDXL Lightning 4-step LoRA の配置

4ステップで高速生成を実現するための LoRA です。

1. **ダウンロード元**: Hugging Face — ByteDance/SDXL-Lightning
   - ファイル名: `sdxl_lightning_4step_lora.safetensors`
   - ファイルサイズ: 約 **400 MB**
2. **配置先**: `models/loras/` にコピー

### ✅ 確認ポイント
- ファイルが `models/loras/` に存在する

## Step 1-7: テスト画像生成（チェックポイント + LoRA のノード接続）

ComfyUI を初めて触る方向けに、**「どのノードのどの色の丸から、どの丸へ線をつなぐのか」** を一つずつ丁寧に解説します。

---

### 💡 初心者のための ComfyUI の基本ルール

1. **ノード（四角い箱）の構造**:
   - **左側の丸（端子）**: 入力（Input）＝ データを受け取る口
   - **右側の丸（端子）**: 出力（Output）＝ データを次のノードへ渡す口
2. **線のつなぎ方**:
   - 右側の丸を **マウス左クリックしたまま引っ張り（ドラッグ）**、繋ぎたい相手の左側の丸の上で **離す（ドロップ）**。
   - 既存の線を外したいときは、丸をクリックして何もない空間へ引っ張って離せば外れます。
3. **色のルール（超重要）**:
   - 原則として **「同じ色同士」** をつなぎます。
   - 🟣 **MODEL（紫色）**: AI の頭脳本体
   - 🟡 **CLIP（黄色）**: 人間の言葉（プロンプト）を理解する辞書
   - 🔴 **VAE（赤色）**: ノイズデータを肉眼で見える「画像」に現像するパーツ
   - 🟠 **CONDITIONING（薄橙色）**: プロンプトの指示内容
   - 🌸 **LATENT（ピンク/赤紫色）**: 画像になる前のノイズデータ
   - 🔵 **IMAGE（青色）**: 完成した画像データ

---

### 🗺️ Step 1-7 の全体配線図（完成形）

```mermaid
graph LR
    subgraph 1. モデル読込
        CKPT["Load Checkpoint\n(animagineXL_v31)"]
    end

    subgraph 2. 高速化アドオン
        LORA["Load LoRA\n(sdxl_lightning_4step)"]
    end

    subgraph 3. プロンプト入力
        P_POS["CLIP Text Encode\n(Positive: 良い特徴)"]
        P_NEG["CLIP Text Encode\n(Negative: 除外特徴)"]
    end

    subgraph 4. キャンバス準備
        LATENT["Empty Latent Image\n(1024 x 1024)"]
    end

    subgraph 5. 描画・生成
        KS["KSampler\n(Steps: 4 / cfg: 1.8)"]
    end

    subgraph 6. 現像・保存
        VAE_DEC["VAE Decode"]
        SAVE["Save Image"]
    end

    %% 配線
    CKPT --"🟣 MODEL"--> LORA
    CKPT --"🟡 CLIP"--> LORA
    CKPT --"🔴 VAE"--> VAE_DEC

    LORA --"🟣 MODEL"--> KS
    LORA --"🟡 CLIP"--> P_POS
    LORA --"🟡 CLIP"--> P_NEG

    P_POS --"🟠 CONDITIONING"--> KS
    P_NEG --"🟠 CONDITIONING"--> KS
    LATENT --"🌸 LATENT"--> KS

    KS --"🌸 LATENT"--> VAE_DEC
    VAE_DEC --"🔵 IMAGE"--> SAVE

    classDef purple fill:#7c3aed,stroke:#a78bfa,color:#fff;
    classDef yellow fill:#d97706,stroke:#fcd34d,color:#fff;
    classDef red fill:#dc2626,stroke:#fca5a5,color:#fff;
    classDef orange fill:#ea580c,stroke:#fdba74,color:#fff;
    classDef pink fill:#db2777,stroke:#f472b6,color:#fff;
    classDef blue fill:#2563eb,stroke:#93c5fd,color:#fff;
```

---

### 🔌 端子接続の完全一覧表（この通りに線をつなぐ）

| # | 出発元ノード | 出発端子（右側） | 色 | つなぐ先ノード | 受け取り端子（左側） |
| :-: | :--- | :--- | :-: | :--- | :--- |
| **1** | **Load Checkpoint** | `MODEL` | 🟣 紫 | **Load LoRA** | `model` |
| **2** | **Load Checkpoint** | `CLIP` | 🟡 黄 | **Load LoRA** | `clip` |
| **3** | **Load Checkpoint** | `VAE` | 🔴 赤 | **VAE Decode** | `vae` |
| **4** | **Load LoRA** | `MODEL` | 🟣 紫 | **KSampler** | `model` |
| **5** | **Load LoRA** | `CLIP` | 🟡 黄 | **CLIP Text Encode（上: Positive）** | `clip` |
| **6** | **Load LoRA** | `CLIP` | 🟡 黄 | **CLIP Text Encode（下: Negative）** | `clip` |
| **7** | **CLIP Text Encode（上）** | `CONDITIONING` | 🟠 橙 | **KSampler** | `positive` |
| **8** | **CLIP Text Encode（下）** | `CONDITIONING` | 🟠 橙 | **KSampler** | `negative` |
| **9** | **Empty Latent Image** | `LATENT` | 🌸 ピンク | **KSampler** | `latent_image` |
| **10** | **KSampler** | `LATENT` | 🌸 ピンク | **VAE Decode** | `samples` |
| **11** | **VAE Decode** | `IMAGE` | 🔵 青 | **Save Image** | `images` |

> [!NOTE]
> **LoRA の役目（なぜ間に挟むのか？）**:
> デフォルトでは `Load Checkpoint` から `KSampler` や `CLIP Text Encode` に直接線が伸びています。
> LoRA はモデルをパワーアップさせる「中継器（アンプ）」のようなものなので、**一度 LoRA に線を入れて、LoRA から送り出す** という形に付け替えます。
> ※手順 5 と 6 のように、1つの端子（LoRA の `CLIP`）から 2 本の線を分岐させてそれぞれ繋いで問題ありません。

---

### 🛠️ 画面での具体的な操作手順（1ステップずつ実行）

#### 【作業 1】初期状態の確認
1. ComfyUI をブラウザで開きます（`http://localhost:8188`）。
2. 画面右側のメニューで **「Load Default」** をクリックして、標準状態にします。

#### 【作業 2】「Load LoRA」ノードを追加する
1. 画面の **何もない灰色の場所で右クリック** します。
2. メニューから **`Add Node` → `loaders` → `Load LoRA`** を順にクリックします。
3. 画面に「Load LoRA」という新しい四角い箱が現れます。ドラッグして `Load Checkpoint` と `KSampler` の間のスペースに置いてください。

#### 【作業 3】既存の線を付け替える（LoRA を挟み込む）
1. **Load Checkpoint の右側 `MODEL`（紫の丸）** をクリック＆ドラッグして、**Load LoRA の左側 `model`（紫の丸）** に繋ぎます。
2. **Load Checkpoint の右側 `CLIP`（黄色の丸）** をクリック＆ドラッグして、**Load LoRA の左側 `clip`（黄色の丸）** に繋ぎます。
3. **Load LoRA の右側 `MODEL`（紫の丸）** をクリック＆ドラッグして、**KSampler の左側 `model`（紫の丸）** に繋ぎます。
4. **Load LoRA の右側 `CLIP`（黄色の丸）** をクリック＆ドラッグして、**上側の CLIP Text Encode の左側 `clip`（黄色の丸）** に繋ぎます。
5. もう一度 **Load LoRA の右側 `CLIP`（黄色の丸）** からドラッグして、**下側の CLIP Text Encode の左側 `clip`（黄色の丸）** に繋ぎます。

#### 【作業 4】各ノードのパラメータ（数値）を設定する

上から順に、各ノードの中にある文字や数値を設定します：

1. **Load Checkpoint**:
   - `ckpt_name`: **`animagineXL_v31.safetensors`** を選択
2. **Load LoRA**:
   - `lora_name`: **`sdxl_lightning_4step_lora.safetensors`** を選択
   - `strength_model`: `1.00`
   - `strength_clip`: `1.00`
3. **CLIP Text Encode（上側: Positive プロンプト）**:
   - テキスト入力欄に以下を貼り付けます：
     ```text
     masterpiece, best quality, very aesthetic, 1girl, solo, anime style, blue hair, smile, school uniform, cherry blossom background
     ```
4. **CLIP Text Encode（下側: Negative プロンプト）**:
   - テキスト入力欄に以下を貼り付けます：
     ```text
     nsfw, lowres, bad anatomy, bad hands, text, error, missing fingers, worst quality, low quality, realistic, photograph, 3d render
     ```
5. **Empty Latent Image**:
   - `width`: `1024`
   - `height`: `1024`
   - `batch_size`: `1`
6. **KSampler（超重要設定！）**:
   - `seed`: そのままでOK（ランダム生成したい場合は `control_after_generate` を `randomize` に）
   - `steps`: **`4`**（※デフォルトの 20 から必ず **4** に変更してください）
   - `cfg`: **`1.8`**（※デフォルトの 8.0 から必ず **1.8** に変更してください）
   - `sampler_name`: **`euler`**
   - `scheduler`: **`sgm_uniform`**
   - `denoise`: `1.00`
7. **Save Image**:
   - `filename_prefix`: `ComfyUI`（変更不要）

#### 【作業 5】画像生成テストを実行
1. 画面右上の青い **「Queue Prompt」** ボタンをクリックします。
2. ノードの枠線が順番に緑色に光りながら処理が進みます。
3. **3〜5秒程度** で、一番右の `Save Image` ノードに桜並木と青髪のアニメ女子高生のイラストが表示されれば **大成功** です！

### ✅ 確認ポイント
- アニメ調の画像が **3〜5秒以内** に出力される
- 画像が真っ黒・ノイズ・崩壊画像ではなく、綺麗なイラストになっている
- ComfyUI のコンソール（Pinokio ログ）に赤いエラーが出ていないこと

---

## 🚧 Phase Gate 1: ComfyUI 基盤構築 完了チェック

> **以下の全項目を満たすまで Phase 2 に進まないでください。**

| # | チェック項目 | 確認方法 | 合否 |
| :--- | :--- | :--- | :--- |
| 1 | ComfyUI が `http://localhost:8188` で起動する | ブラウザでアクセス | ☐ |
| 2 | ComfyUI Manager が利用可能 | UI に「Manager」ボタンがある | ☐ |
| 3 | Animagine XL v3.1 **FP8版** がロードできる | Checkpoint ノードで選択可能 | ☐ |
| 4 | SDXL Lightning 4-step LoRA がロードできる | LoRA ノードで選択可能 | ☐ |
| 5 | テスト画像が **5秒以内** に生成される | Queue Prompt → 画像表示 | ☐ |
| 6 | VRAM 使用量が **8 GB 以下**（この段階） | PowerShell: `nvidia-smi` | ☐ |

---

---

# Phase 2: Ollama 導入（ローカル LLM 稼働）

**目的**: Ollama をインストールし、日本語の感情解析・プロンプト生成用の LLM がローカルで動作する状態にする。

## Step 2-1: Ollama のインストール

1. ブラウザで https://ollama.com/download にアクセス
2. **「Download for Windows」** をクリックしてインストーラーをダウンロード
3. インストーラーを実行（デフォルト設定でOK）
4. インストール完了後、**PowerShell を新しく開く**（パスの反映に必要）

### ✅ 確認コマンド
```powershell
ollama --version
```
バージョン番号が表示されればOK。

## Step 2-2: LLM モデルのダウンロード

PowerShell で以下を **1行ずつ** 実行します。

```powershell
# ① 本命モデル（超低遅延）— 約 1.6 GB
ollama pull gemma4:e2b

# ② 日本語リファレンス — 約 1.9 GB
ollama pull qwen2.5:3b

# ③ 非常用フェイルセーフ — 約 900 MB
ollama pull qwen2.5:1.5b
```

> [!NOTE]
> ダウンロードには回線速度に応じて 5〜30 分かかります。
> 3つ合計で約 **4.5 GB** のディスク容量を使用します。

### ✅ 確認コマンド
```powershell
ollama list
```
3つのモデルが一覧に表示されればOK。

## Step 2-3: LLM の動作テスト（JSON 生成）

実際に StoryWeaver で使うのと同じ形式で JSON を生成させて、正しく動くか確認します。

```powershell
ollama run gemma4:e2b 'You are an animation director. A hero shouted: "I will never give up!". Generate a JSON object with keys: emotion (Japanese), animeAura (English tags), narrativeCaption (Japanese sentence), characterAction (English). Output ONLY valid JSON.' --format json
```

### ✅ 確認ポイント
- JSON 形式のレスポンスが返ること（`{...}` で囲まれた構造）
- `emotion`, `animeAura`, `narrativeCaption`, `characterAction` の4つのキーが含まれていること
- 応答時間が **5秒以内** であること（e2b は非常に高速なモデル）

## Step 2-4: Ollama API サーバーの確認

Ollama はインストール時にバックグラウンドサービスとして自動起動します。

```powershell
# API が応答するか確認
Invoke-RestMethod -Uri "http://localhost:11434/api/tags"
```

### ✅ 確認ポイント
- JSON でモデル一覧が返却される
- ポート `11434` でリスニングしている

## Step 2-5: VRAM 共存テスト（ComfyUI + Ollama 同時起動）

**この確認が非常に重要です。** 両方を同時に起動した状態で VRAM が足りるか確認します。

1. **ComfyUI を起動中のまま** にする（Pinokio で Start 状態）
2. PowerShell で Ollama にリクエストを送る:
   ```powershell
   ollama run gemma4:e2b "Hello, test." --verbose
   ```
3. VRAM 使用量を確認:
   ```powershell
   nvidia-smi
   ```

### ✅ 確認ポイント
- 両方が同時に動作し、応答が返る
- VRAM 合計使用量が **14.5 GB 以下** であること

> [!WARNING]
> もし VRAM が 14.5 GB を超える場合:
> 1. Ollama のモデルを `qwen2.5:1.5b`（最軽量版）に切り替えて再テスト
> 2. ComfyUI 側で使っていないモデルがキャッシュに残っていないか確認
> 3. それでもダメな場合は `OLLAMA_GPU_MEMORY=2048` 環境変数で制限する

---

## 🚧 Phase Gate 2: Ollama 導入 完了チェック

> **以下の全項目を満たすまで Phase 3 に進まないでください。**

| # | チェック項目 | 確認方法 | 合否 |
| :--- | :--- | :--- | :--- |
| 1 | Ollama がインストール済み | `ollama --version` | ☐ |
| 2 | gemma4:e2b が応答する | `ollama run gemma4:e2b "test"` | ☐ |
| 3 | JSON 形式で正しく出力できる | 上記 Step 2-3 のテスト | ☐ |
| 4 | API サーバーがポート 11434 で応答 | `Invoke-RestMethod` テスト | ☐ |
| 5 | ComfyUI と同時起動で **VRAM ≤ 14.5 GB** | `nvidia-smi` | ☐ |

---

---

# Phase 3: ComfyUI — アニメ調顔転生パイプライン構築（本人同一性 ➔ 動的演出 ➔ 高速化）

**目的**: 写真の特徴（髪型・眼鏡・顔貌）を確実に反映しつつ、ストーリーに応じたダイナミックなポーズ・表情と、展示運用に耐える生成速度を両立する画像生成パイプラインを確立する。

> [!IMPORTANT]
> **【基本方針】「本人同一性の確立 ➔ ストーリー連動の動的演出 ➔ 生成時間短縮」を順次確立**:
> まず第一に「顔の特徴がきちんと残るアニメ・漫画絵」を成立させ、その上で「キャラクターをダイナミックに変換してストーリーに応じたポーズ・表情」を作り、最後に「生成時間の短縮」を行う 3大フェーズ体系で手戻りなく進めます。
> 詳細な技術仕様・全14ノード配線表は **[phase3_revision_plan.md](file:///c:/antigravity/StoryWeaver/docs/plans/phase3_revision_plan.md)** を参照してください。

---

## 1. 3大フェーズ検証フローと Gate（関門）

```mermaid
flowchart TD
    subgraph P3A["Phase 3-A: 【第1期】顔特徴・本人同一性とアニメ品質の確立"]
        A1["ポートレート構図固定"] --> A2["WD14 Tagger (外見属性自動抽出)"]
        A2 --> A3["ApplyInstantIDAdvanced (顔貌固定)"]
        A3 --> A4["FaceDetailer (別人化防止・高精細化)"]
        A4 --> GA{"🚧 Gate 3-A<br>・本人同一性（目鼻立ち/髪型/眼鏡）<br>・美麗アニメ/漫画画質<br>・solo遵守"}
    end

    subgraph P3B["Phase 3-B: 【第2期】ストーリー連動の動的ポージング・表情と顧客提供品質"]
        B1["骨格拘束緩和 (cn_strength 調整)"] --> B2["ストーリープロンプト注入 (抜刀/跳躍/構図)"]
        B2 --> B3["表情変化の追従 (叫び/微笑み)"]
        B3 --> B4["全身・引き構図での小顔潰れ防止"]
        B4 --> GB{"🚧 Gate 3-B<br>・ポーズ/表情への完全追従（首折れなし）<br>・動的変換後も本人同一性を維持<br>・提供物として感動を与える絵の完成度"}
    end

    subgraph P3C["Phase 3-C: 【第3期】生成時間の短縮・展示運用最適化 & API確定"]
        C1["画質基準に基づく高速化比較 (LoRA / steps)"] --> C2["画質維持とレイテンシの最適点決定"]
        C2 --> C3["VRAM ≤ 14.5GB & ゼロダウンタイム検証"]
        C3 --> GC{"🚧 Gate 3-C (最終関門)<br>・生成時間 ≤ 7分 (420秒) 許容<br>・OOM ゼロ<br>・完全自動 storyweaver_anime_api.json 出力"}
    end

    GA -- "合格 (本人性と画質の確立)" --> P3B
    GB -- "合格 (動的演出と提供品質の確立)" --> P3C
    GC -- "合格 (運用速度とAPIの確立)" --> PHASE4["Phase 4: FastAPI オーケストレーター構築へ"]

    classDef gate fill:#d97706,stroke:#fcd34d,color:#fff;
    classDef phase4 fill:#16a34a,stroke:#22c55e,color:#fff;
```

---

## 2. 各検証フェーズの手順・判定基準 (Gate)・調整方針

### Phase 3-A: 【第1期】顔特徴・本人同一性とアニメ品質の確立
- **目的**: 動的ポーズや全身構図を排し、元写真の本人らしさ（目鼻立ち、髪型、眼鏡）が確実に反映された美麗アニメ調イラストのベースラインを確立する。
- **検証手順**:
  1. プロンプトをポートレート（バストアップ、正面〜自然な向き）に固定。
  2. WD14 Tagger による外見属性（髪型・眼鏡）の自動抽出・結合を安定化。
  3. `ApplyInstantIDAdvanced`（Base）の `ip_weight: 0.70〜0.75` で顔貌特徴を確実に転写。
  4. FaceDetailer（`denoise: 0.25〜0.30`, `bbox_crop_factor: 1.4`）で別人化を防ぎつつ瞳や眼鏡を鮮明化。

#### 🚧 Gate 3-A 判定基準（合格条件）
| # | チェック項目 | 合格基準 | 合否 |
| :-: | :--- | :--- | :---: |
| A-1 | **本人同一性の成立** | 写真を見た人が「本人だ」と即座に認識できる（目元の特徴、髪型、眼鏡が一致） | ☐ |
| A-2 | **美麗アニメ品質** | 実写の不気味さや崩れがなく、瞳にハイライトが入った美しいセル画アニメ調であること | ☐ |
| A-3 | **`solo` 遵守** | 人物が1人だけであり、多人数化・コラージュ・分裂が一切発生しないこと | ☐ |
| A-4 | **別人化の非発生** | FaceDetailer 適用前後で顔立ちが別人に置き換わっていないこと | ☐ |

- **【OK の場合】**: 本人性と画質が確立！→ **Phase 3-B（動的ポージング・表情演出）へ進む**。
- **【NG の場合（調整方針）】**:
  - 似ていない: `ip_weight: 0.75` へ引き上げ、WD14 の `threshold` を `0.30` に下げて眼鏡・髪型タグを補強。
  - アニメ調が硬い: `ip_weight: 0.65` へ微減、CFG を `7.0` に調整。
  - FaceDetailer で別人になる: `denoise` を `0.25` 以下へ引き下げ。

---

### Phase 3-B: 【第2期】ストーリー連動の動的ポージング・表情と顧客提供品質
- **目的**: 第1期で確立した本人同一性を維持したまま、ストーリーに応じたダイナミックなアクション（抜刀、跳躍）、表情変化、全身構図への変換を実現し、顧客に提供できる絵画完成度を高める。
- **検証手順**:
  1. `ApplyInstantIDAdvanced` の骨格拘束を `cn_strength: 0.12〜0.18 (推奨 0.15)` に緩和し、正面固定を解除。
  2. ストーリープロンプト（抜刀、跳躍、構図指示）および表情指示（叫び、笑顔等）を注入。
  3. 全身・引き構図における小顔崩れを FaceDetailer の顔専用タグ連携でクリアに修復。

#### 🚧 Gate 3-B 判定基準（合格条件）
| # | チェック項目 | 合格基準 | 合否 |
| :-: | :--- | :--- | :--- |
| B-1 | **ポーズ追従性** | 抜刀や跳躍、斜めアングルに身体と頭部が自然に追従し、首折れや正面固定がないこと | ☐ |
| B-2 | **表情・ストーリー演出** | 指示した表情（叫び、笑顔等）や世界観エフェクトが破綻なく描画されていること | ☐ |
| B-3 | **動的変換時の同一性維持** | アクションポーズや全身構図になっても、Phase 3-A で確立した本人と同一人物に見えること | ☐ |
| B-4 | **引き構図の解像感** | 全身（full body）描画時でも、顔・瞳・眼鏡が潰れず綺麗にリファインされていること | ☐ |

- **【OK の場合】**: 動的演出と提供品質が確立！→ **Phase 3-C（生成時間短縮・運用最適化）へ進む**。
- **【NG の場合（調整方針）】**:
  - 首が正面を向いたままポーズと乖離: `cn_strength: 0.12` へ緩和、`end_at: 0.80` に短縮。
  - 動的ポーズで顔が崩れる: `cn_strength: 0.18` へ微増、`ip_weight: 0.70` へ補強。
  - 顔内に剣やマントのエフェクト混入: FaceDetailer の `wildcard` に顔特化タグを注入して完全分離。

---

### Phase 3-C: 【第3期】生成時間の短縮・展示運用最適化 & API確定
- **目的**: 短時間制約による画質劣化を防ぐため、まずは最大7分（420秒）の時間を許容して最高画質・本人同一性の水準を確立する。その上で確立した品質を基準とし、展示運用に向けて段階的にどこまで短縮可能かを測定・最適化して、完全自動 API ワークフロー（`storyweaver_anime_api.json`）を確定する。
- **検証手順**:
  1. 画質基準に基づく高速化比較（フル品質サンプリング vs 各種ステップ短縮 / LoRA導入）の実施。
  2. 連続生成テストによる VRAM ≤ 14.5GB & ゼロダウンタイムの検証。
  3. `storyweaver_anime_api.json` の出力・API ロード確認。

#### 🚧 Gate 3-C 判定基準（最終関門）
| # | チェック項目 | 合格基準 | 合否 |
| :-: | :--- | :--- | :---: |
| C-1 | **生成時間許容** | 1回のイラスト生成が **最大7分以内（420秒以内）** で安定完了すること | ☐ |
| C-2 | **画質・本人性の非劣化** | Gate 3-A（本人同一性）および Gate 3-B（動的演出）で確立した画質水準を満たしていること | ☐ |
| C-3 | **OOM ゼロ (VRAM ≤ 14.5GB)** | 長時間サンプリング中も VRAM 14.5GB を一度も超えず、クラッシュしないこと | ☐ |
| C-4 | **短縮ベンチマークと API 確定** | 画質基準に基づく短縮検証を完了し、`storyweaver_anime_api.json` が正常に出力・保存されること | ☐ |

- **【OK の場合】**: Phase 3 完了！→ **Phase 4（FastAPI オーケストレーター構築）へ進む**。
- **【NG の場合（調整方針）】**:
  - Lightning LoRA で陰影が崩れる: LoRA strength を `0.8` に下げるか、標準モデル 20 steps（約13秒）を採用。
  - VRAM 超過: FaceDetailer の `guide_size` を 512 に調整。

---

# Phase 4: FastAPI オーケストレーター構築

**目的**: 顔写真・音声テキスト入力を受け取り、Ollama → ComfyUI を順次呼び出して画像生成結果を返す API サーバーを構築する。

## Step 4-1: Python 仮想環境の作成

プロジェクト専用の仮想環境を作ります。

```powershell
cd c:\antigravity\StoryWeaver
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> [!NOTE]
> 以降の Phase 4 のコマンドは、すべて **仮想環境を有効化した状態** で実行してください。
> プロンプトが `(.venv) PS c:\antigravity\StoryWeaver>` に変わっていることを確認。

## Step 4-2: 依存ライブラリのインストール

```powershell
pip install funasr modelscope soundfile fastapi uvicorn requests python-multipart
```

> [!NOTE]
> `funasr` は SenseVoice（音声認識）用のライブラリです。
> 初回の `import` 時に SenseVoiceSmall モデル（約400MB）が自動ダウンロードされます。

### ✅ 確認コマンド
```powershell
python -c "import fastapi; import funasr; print('OK')"
```
`OK` と表示されればインストール成功。

## Step 4-3: server.py の作成

`Attached_doc/storyweaver_live.md` に記載された `server.py` のコードをベースに、以下の **安全対策を追加した改良版** を作成します。

> **私（Antigravity）がコードを作成します。** このステップでは以下の改良点を盛り込みます:
> 1. タイムアウト付きポーリング（無限ループ防止）
> 2. Ollama JSON パースのフォールバック
> 3. 同時実行セマフォ（VRAM スパイク防止）
> 4. 一時ファイルの UUID 付きファイル名（競合防止）

### ✅ 確認ポイント
- `server.py` がエラーなく起動する
- `http://localhost:8000/docs` にアクセスして Swagger UI が表示される

## Step 4-4: SenseVoice (音声認識) の初回起動テスト

サーバー初回起動時に SenseVoice モデルが自動ダウンロードされます。

```powershell
python -c "from funasr import AutoModel; m = AutoModel(model='iic/SenseVoiceSmall', trust_remote_code=True, device='cpu'); print('SenseVoice loaded OK')"
```

> [!TIP]
> VRAM を節約するため SenseVoice は **CPU 実行** を推奨します。
> 0.4 GB の VRAM 節約ができ、推論速度への影響はわずかです（音声認識は約0.1秒）。

### ✅ 確認ポイント
- モデルのダウンロードが完了する（初回のみ数分かかる）
- `SenseVoice loaded OK` と表示される

## Step 4-5: パイプライン結合テスト（API 単体テスト）

ComfyUI と Ollama を起動した状態で、`server.py` を起動し、curl でテストします。

```powershell
# 1. 別ターミナルで server.py を起動
python server.py

# 2. テスト用の顔画像を用意（例: test_face.jpg）
# 3. curl でテスト送信
curl -X POST "http://localhost:8000/api/process_story" `
  -F "face_image=@test_face.jpg" `
  -F "transcript_text=絶対に諦めない！" `
  -F "base_prompt=dramatic battle scene" `
  -F "scene_style=fantasy anime"
```

### ✅ 確認ポイント
- JSON レスポンスが返る
- `transcript`, `analysis`, `imageBase64` の3つのキーが含まれる
- `imageBase64` を Base64 デコードすると、アニメ調の画像になっている
- 全体の処理時間が **10秒以内**（WD14 Tagger + FaceDetailer 追加後の実測で判定。超過時は付録の調整手段を適用）

---

## 🚧 Phase Gate 4: FastAPI オーケストレーター 完了チェック

> **以下の全項目を満たすまで Phase 5 に進まないでください。**

| # | チェック項目 | 確認方法 | 合否 |
| :--- | :--- | :--- | :--- |
| 1 | `server.py` がポート 8000 で起動 | `http://localhost:8000/docs` | ☐ |
| 2 | SenseVoice モデルが正常ロード済み | 起動ログにエラーなし | ☐ |
| 3 | API テストで JSON レスポンスが返る | curl テスト | ☐ |
| 4 | 返却画像がアニメ調 & 顔特徴反映 | Base64 デコード・目視確認 | ☐ |
| 5 | 全体処理 ≤ **10秒** | curl 実行時間計測 | ☐ |
| 6 | 3サービス同時起動中 VRAM ≤ **14.5 GB** | `nvidia-smi` | ☐ |

---

---

# Phase 5: フロントエンド UI 構築・接続

**目的**: ブラウザ上でカメラ撮影・セリフ入力 → アニメ画生成 → 朗読再生までの体験者向けフルフローを実装する。

## Step 5-1: フロントエンド HTML/CSS/JS の作成

> **私（Antigravity）がコードを作成します。** 以下の機能を実装します:
> - Webカメラからの顔写真撮影
> - セリフテキスト入力（音声入力オプション付き）
> - シーンプリセット選択（ファンタジー、SF、日常 等）
> - 生成中のローディングアニメーション
> - 生成結果のアニメ画カード表示
> - Web Speech API による日本語朗読自動再生
> - 全画面シアターモード（プロジェクター展示用）
> - 記念アートカード PNG ダウンロード

## Step 5-2: FastAPI からフロントエンドの静的配信設定

`server.py` に静的ファイル配信を追加し、ポート 8000 でフロントエンドも配信します。

### ✅ 確認ポイント
- `http://localhost:8000` にアクセスしてフロントエンド UI が表示される
- カメラプレビューが動作する

## Step 5-3: End-to-End テスト

1. ブラウザで `http://localhost:8000` にアクセス
2. カメラで顔写真を撮影
3. セリフを入力（例: 「この世界を守るために、立ち上がる！」）
4. シーンプリセットを選択
5. **「生成」** ボタンをクリック
6. アニメ調のキャラクターイラストが表示される
7. 朗読音声が自動再生される

---

## 🚧 Phase Gate 5: フロントエンド 完了チェック

> **以下の全項目を満たすまで Phase 6 に進まないでください。**

| # | チェック項目 | 確認方法 | 合否 |
| :--- | :--- | :--- | :--- |
| 1 | UI がブラウザに表示される | `http://localhost:8000` | ☐ |
| 2 | カメラプレビューが動作する | ブラウザのカメラ許可 | ☐ |
| 3 | 顔撮影 → セリフ入力 → 生成 が成功 | E2E テスト実行 | ☐ |
| 4 | アニメ画カードが画面に表示される | 目視 | ☐ |
| 5 | 朗読音声が自動再生される | スピーカー出力確認 | ☐ |
| 6 | シアターモード（全画面）が動作する | 全画面ボタン | ☐ |
| 7 | PNG ダウンロードが動作する | ダウンロードボタン | ☐ |

---

---

# Phase 6: 展示本番チューニング & リハーサル

**目的**: 展示本番環境での安定稼働を検証し、長時間連続運用に耐えるパフォーマンスと品質を確認する。

## Step 6-1: 連続生成ストレステスト

10回連続で異なる入力パターンで生成テストを実施します。

| テスト# | 入力バリエーション | チェック項目 |
| :--- | :--- | :--- |
| 1〜3 | 異なる人物の顔写真 | 顔特徴が反映されるか |
| 4〜5 | 長文セリフ（50文字以上） | Ollama がタイムアウトしないか |
| 6〜7 | 異なるシーンプリセット | プリセットごとに画風が変わるか |
| 8〜9 | 即時連続クリック（1秒間隔） | セマフォが効いてキュー処理されるか |
| 10 | 空セリフ（テキスト未入力） | フォールバックが効くか |

### ✅ 確認ポイント
- 10回全てで正常に画像が生成される
- VRAM 使用量が安定して **14.5 GB 以下** を維持
- GPU 温度が **85℃ 以下** を維持（`nvidia-smi` で確認）
- メモリリーク（RAM の単調増加）がない

## Step 6-2: 画質チューニング

| 調整項目 | 初期値 | 調整方法 |
| :--- | :--- | :--- |
| 顔の実写感が残る | `ip_weight: 0.60`（Main / Detailer） | → `0.50〜0.55` に下げる |
| 顔の特徴が薄い | `ip_weight: 0.60`（Detailer） | → `0.65〜0.70` に上げる |
| 顔の向きがポーズに追従しない | `cn_strength: 0.25`（Main） | → `0.20` に下げる |
| 目鼻の配置が崩れる | `cn_strength: 0.25`（Main）/ `0.35`（Detailer） | → Main `0.30〜0.35` / Detailer `0.40〜0.45` に上げる |
| 再描画した顔が浮く（首・髪との境目） | FaceDetailer `denoise: 0.45` | → `0.40` に下げる / `feather` を `10` に |
| 引きの絵で顔が再描画されない | FaceDetailer `bbox_threshold: 0.50` | → `0.35` に下げる |
| 不要なタグ（服装・背景など）が混ざる | WD14 `threshold: 0.40` | → `0.45〜0.50` に上げる / `exclude_tags` に追記 |
| 眼鏡などの装飾品が拾われない | WD14 `threshold: 0.40` | → `0.30〜0.35` に下げる |
| ComfyUI の処理時間が 8 秒を超える | FaceDetailer `guide_size: 768` | → `640` に下げる / WD14 を `wd-v1-4-moat-tagger-v2` に |
| 色彩が地味 | — | Positive Prompt に `vibrant colors, saturated` を追加 |

## Step 6-3: 起動手順書の作成（展示当日用）

展示本番の朝、以下の順序でシステムを起動します:

```
起動順序（厳守）:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. PC 起動 → nvidia-smi で GPU 認識確認
2. Pinokio → ComfyUI 起動 (ポート 8188)
3. Ollama 自動起動確認 (ポート 11434)
4. PowerShell → server.py 起動 (ポート 8000)
5. ブラウザ → http://localhost:8000 アクセス
6. テスト生成 1回実行 → 正常確認
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🚧 Phase Gate 6（最終ゲート）: 本番稼働準備 完了チェック

> **以下の全項目を満たしたら、展示本番準備完了です。🎉**

| # | チェック項目 | 確認方法 | 合否 |
| :--- | :--- | :--- | :--- |
| 1 | 連続10回生成テスト全成功 | ストレステスト | ☐ |
| 2 | OOM エラー発生なし | 全テスト中 `nvidia-smi` 監視 | ☐ |
| 3 | GPU 温度 ≤ 85℃ 安定 | `nvidia-smi` | ☐ |
| 4 | 1回あたりの生成時間 ≤ 10秒 | ストップウォッチ計測 | ☐ |
| 5 | 画質が展示水準（目視OK） | 関係者レビュー | ☐ |
| 6 | 起動手順書が完成 | ドキュメント確認 | ☐ |
| 7 | 障害時の復旧手順を把握 | incident-check スキル確認 | ☐ |

---

---

## 付録: トラブルシューティング早見表

| 症状 | 原因の可能性 | 対処法 |
| :--- | :--- | :--- |
| ComfyUI が起動しない | Pinokio の設定ミス | Pinokio からアンインストール → 再インストール |
| `Load Checkpoint` / `UNETLoader` にモデルが表示されない | ファイルの配置先が違う | ComfyUI ルートの `models/checkpoints/` または `models/unet/` を再確認 |
| Mage-Flow / FLUX.2 Klein ノードが見つからない | ComfyUI 本体のバージョンが古い | ComfyUI を最新版にアップデート（`git pull` または Pinokio 更新） |
| OOM (Out of Memory) エラー | VRAM 超過・プロセス同時ロード | ① Ollama リクエストに `keep_alive: 0` が付与されているか確認 ② Mage-Flow は Int8版、FLUXは FP8版 を使用しているか確認 |
| Ollama が応答しない | サービス停止 | `ollama serve` をターミナルで手動起動 |
| 生成画像が真っ黒 / 白飛び | cfg または スケジューラ設定ミス | Mage-Flow は cfg: 1.0 / simple、FLUX は cfg: 1.0 + Flux2Scheduler を確認 |
| 顔写真の特徴が反映されない | 参照画像の入力端子ミス | Mage は `TextEncodeMageFlowEdit` の `ref_image_1`、FLUX は `ReferenceLatent` への VAEEncode 接続を確認 |
| ポーズが正面に固定されてしまう | 骨格拘束の残存 | 旧 InstantID の ControlNet は外し、マルチモーダル DiT のプロンプト指示（SceneSpec）に委ねる |
| FaceDetailer で顔が別人化する | 過剰な denoise / 常時発火 | 条件付き発火（BBox長辺 < 180px）を確認し、denoise を `0.35〜0.40` に調整 |
| API テストで `Connection Refused` | サービス未起動 | 各サービスの起動状態を確認 (8000, 8188, 11434) |
| ブラウザでカメラが使えない | HTTPS 未使用 | `localhost` 経由なら HTTP でもカメラ使用可 |

---

## 次のアクション

**Phase 1 から順番に着手してください。** 各 Phase Gate のチェックリストを全て ☑ にしてから次の Phase に進みます。

構築中に不明点やエラーが発生した場合は、いつでも質問してください。
エラー内容と `nvidia-smi` の出力を添えていただくと、迅速に原因特定できます。
