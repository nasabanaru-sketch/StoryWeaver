# StoryWeaver Live Phase 3 実装検証計画書
## （本人同一性 ➔ ストーリー動的演出 ➔ 生成時間短縮：3大フェーズ検証仕様）

**文書バージョン**: 4.1.0  
**改訂日**: 2026年10月11日  
**基本思想**: **「顔特徴の再現 ➔ ストーリー連動の動的演出 ➔ 生成速度の最適化」を順次確立し、手戻りゼロで顧客提供価値を最大化する**  
**対象環境**: ThinkPad X1 Extreme (GPU: RTX 3080 Laptop 16GB / RAM: 32GB / Windows 11)  
**運用制約**: 展示ブース完全ローカル稼働 / ゼロダウンタイム / VRAM 14.5GB 以内 / **生成時間：画質最優先のため一旦最大7分（420秒）まで許容**

---

## 1. 全体ロードマップと Phase 体系

本計画は、展示インスタレーションとしての顧客体験価値（「あ、自分だ！」「かっこいい！」「早い！」）を段階的かつ確実に達成するため、以下の **3大フェーズ構成** で推進します。
※短時間制約による画質劣化を防ぐため、**時間については一旦最大7分まで許容し、画質の許容範囲を確定させた後に時間短縮を図るアプローチ**をとります。

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

## 2. 各フェーズの詳細設計・タスク・判定基準 (Gate)

---

### Phase 3-A: 【第1期】顔特徴・本人同一性とアニメ品質の確立

#### 1. 目的
動的ポーズや全身構図などの不確定要素を完全に排除し、**「元写真の本人らしさ（目元・鼻・口の形状、髪型、眼鏡などの記号）」が確実に残り、かつ美麗なセル画調アニメ・漫画絵として成立するベースライン** を確立する。

#### 2. やること（検証タスク）
1. **構図の固定**:
   * プロンプトをポートレート（上半身・バストアップ、正面〜自然な向き）に固定し、顔の描画解像度を画面全体の50%以上に確保する。
2. **外見属性の自動抽出（WD14 Tagger 連携）**:
   * 写真から「髪型（短髪・黒髪等）」や「眼鏡（glasses）」などの外見属性を漏れなく抽出し、プロンプトへ自動結合する。
3. **InstantID 顔特徴強度の確立**:
   * `ApplyInstantIDAdvanced` の `ip_weight` を最適化し、Animagine XL の強力な美形アニメバイアスに負けずに本人の顔貌を確実に転写する。
4. **FaceDetailer による高精細化と「別人化防止」**:
   * FaceDetailer の `denoise` を「Base の顔立ちを壊さず、瞳のハイライトや眼鏡フレームだけを鮮明にする」安全領域に設定する。

#### 3. ワークフロー推奨構成
* **プロンプト**: `masterpiece, best quality, anime art style, solo, portrait, close-up face, upper body, looking at viewer, detailed facial features, simple background` ＋ WD14 自動タグ
* **ApplyInstantIDAdvanced (Base)**: `ip_weight: 0.70〜0.75`, `cn_strength: 0.25`, `end_at: 1.0`
* **FaceDetailer**: `denoise: 0.25〜0.30`, `bbox_crop_factor: 1.4`, `feather: 10`
* **FaceDetailer 側 InstantID**: `cn_strength: 0.0` (骨格不整合による歪みを排除), `ip_weight: 0.45`

#### 4. 🚧 Gate 3-A 判定基準（合格条件）
| # | チェック項目 | 合格基準 | 確認方法 | 合否 |
| :-: | :--- | :--- | :--- | :---: |
| A-1 | **本人同一性の成立** | 写真を見た人が「本人だ」と即座に認識できる（目元の特徴、髪型、眼鏡が一致） | 写真と比較確認 | ☐ |
| A-2 | **美麗アニメ品質** | 実写の生々しさや崩れがなく、瞳にハイライトが入った美しいセル画アニメ調であること | 目視確認 | ☐ |
| A-3 | **`solo` 遵守** | 人物が1人だけであり、多人数化・コラージュ・分裂が一切発生しないこと | 目視確認 | ☐ |
| A-4 | **別人化の非発生** | FaceDetailer 適用前後で顔立ちが別人に置き換わっていないこと | Preview vs Save 比較 | ☐ |

* **⚠️ 不合格時の対処手順**:
  * 似ていない $\rightarrow$ `ip_weight: 0.75` へ引き上げ、WD14 の `threshold` を `0.30` に下げて眼鏡・髪型タグを補強。
  * アニメ絵が硬い・実写臭い $\rightarrow$ `ip_weight: 0.65` へ微減、CFG を `7.0` に調整。
  * FaceDetailer で別人になる $\rightarrow$ `denoise` を `0.25` 以下へ引き下げ。

---

### Phase 3-B: 【第2期】ストーリー連動の動的ポージング・表情と顧客提供品質

#### 1. 目的
Phase 3-A で確立した「本人同一性」を一切損なうことなく、**ストーリー（戦士、魔法使い、冒険者等）に応じたダイナミックなアクション・ポージング、表情変化（微笑み、叫び、決意）、全身構図への変換** を実現し、展示来場者に提供して感動を与える絵画クオリティを確立する。

#### 2. やること（検証タスク）
1. **骨格拘束緩和によるポーズ自由度の解放**:
   * 元写真の証明写真的な「正面棒立ち骨格」をカットし、ダイナミックなアクションポーズ（抜刀、跳躍、振り返り、見上げ等）に身体と顔が自然に追従するスイートスポットを確定する。
2. **ストーリープロンプトおよび表情の注入**:
   * ストーリー演出タグ（`dynamic pose, full body, fantasy warrior, glowing sword, dynamic angle, shouting/confident smile`）を注入し、シーンに合致した迫力ある構図を生成する。
3. **引き構図・全身構図における顔潰れ対策**:
   * 人物が画面奥に配置された際、遠景の顔が潰れないよう FaceDetailer を連携させ、全身構図でも顔のディテール（目鼻立ち・眼鏡）を鮮明に保つ。
4. **全体調和・顧客提供価値の検証**:
   * 背景、エフェクト（魔法光や風）、衣装と、本人の顔が浮くことなく完全に調和し、持ち帰りたくなる1枚のアートとして成立しているかを評価する。

#### 3. ワークフロー推奨構成
* **ApplyInstantIDAdvanced (Base)**: `ip_weight: 0.65〜0.70`, **`cn_strength: 0.12〜0.18 (推奨 0.15)`**, `end_at: 0.85`
* **プロンプト**: ストーリー情景文 ＋ WD14 外見タグ
* **FaceDetailer**: `wildcard` に顔特化タグ（`detailed beautiful anime eyes, clear pupils`）を注入し、全身タグによる顔内ノイズ混入を防止。

#### 4. 🚧 Gate 3-B 判定基準（合格条件）
| # | チェック項目 | 合格基準 | 確認方法 | 合否 |
| :-: | :--- | :--- | :--- | :---: |
| B-1 | **ポーズ追従性** | 抜刀や跳躍、斜めアングルに身体と頭部が自然に追従し、首折れや正面固定がないこと | 目視確認 | ☐ |
| B-2 | **表情・ストーリー演出** | 指示した表情（叫び、笑顔等）や世界観エフェクトが破綻なく描画されていること | 目視確認 | ☐ |
| B-3 | **動的変換時の本人性維持** | アクションポーズや全身構図になっても、Phase 3-A で確立した本人と同一人物に見えること | 目視確認 | ☐ |
| B-4 | **引き構図の解像感** | 全身（full body）描画時でも、顔・瞳・眼鏡が潰れず綺麗にリファインされていること | 拡大確認 | ☐ |

* **⚠️ 不合格時の対処手順**:
  * 首が正面を向いたままポーズと乖離する $\rightarrow$ `cn_strength: 0.12` へ緩和、`end_at: 0.80` に短縮。
  * 動的ポーズで顔が崩れて別人化する $\rightarrow$ `cn_strength: 0.18` へ微増、`ip_weight: 0.70` へ補強。
  * 顔の中に剣やマントのエフェクトが混ざる $\rightarrow$ FaceDetailer の `positive` または `wildcard` を顔専用プロンプトに完全分離。

---

### Phase 3-C: 【第3期】生成時間の短縮・展示運用最適化 & API確定

#### 1. 目的
短時間制約（≤20秒）による画質劣化や描写崩れを防ぐため、**まずは最大7分（420秒）の時間を許容して Phase 3-A（本人同一性）および Phase 3-B（動的演出・絵画完成度）の最高画質水準を完全に確立** する。その上で、確立した品質をベンチマーク基準とし、展示運用に向けて段階的にどこまで時間を短縮できるかを測定・最適化し、FastAPI オーケストレーター（Phase 4）に接続可能な完全自動 API ワークフロー（`storyweaver_anime_api.json`）を確定する。

#### 2. やること（検証タスク）
1. **画質基準に基づく高速化手法の比較実証**:
   * **基準（フル品質）**: 標準 Animagine（25〜30 steps）＋ 高精細 FaceDetailer（15〜20 steps）による最高画質の所要時間を測定（最大7分以内）。
   * **短縮比較**:
     * 案 A: 標準 Animagine のサンプリングステップ最適化（KSampler 15〜20 steps, FaceDetailer 8〜10 steps）。
     * 案 B: Lightning LoRA 8-step / 4-step 導入時の画質・本人同一性の劣化度合いを検証。
   * 画質の許容範囲を絶対に下回らない「最適サンプリング設定」を決定する。
2. **展示運用レイテンシの段階的検証**:
   * 最大7分（420秒）を許容上限とし、画質維持が可能な最短時間を実測・記録する。
3. **VRAM 14.5GB 以内 & ゼロダウンタイム検証**:
   * 長時間サンプリングや連続生成（5回以上）を行い、VRAM リークや OOM（Out of Memory）、GPU 温度上昇によるスロットリングがないことを確認する。
4. **完全自動化 API ワークフローの出力と検証**:
   * 「写真（IMAGE）＋ ストーリープロンプト（STRING）」を外部から注入するだけで全自動稼働する `storyweaver_anime_api.json` を出力・テスト実行する。

#### 3. 🚧 Gate 3-C 判定基準（最終関門）
| # | チェック項目 | 合格基準 | 確認方法 | 合否 |
| :-: | :--- | :--- | :--- | :---: |
| C-1 | **生成時間許容** | 1回のイラスト生成が **最大7分以内（420秒以内）** で安定完了すること | 処理時間実測 | ☐ |
| C-2 | **画質・本人性の非劣化** | Gate 3-A（本人同一性）および Gate 3-B（動的演出）で確立した画質水準を満たしていること | A/B 比較評価 | ☐ |
| C-3 | **OOM ゼロ (VRAM ≤ 14.5GB)** | 長時間サンプリング中も VRAM 14.5GB を一度も超えず、クラッシュしないこと | `nvidia-smi` 監視 | ☐ |
| C-4 | **短縮ベンチマークと API 確定** | 画質基準に基づく短縮検証を完了し、`storyweaver_anime_api.json` が正常に出力・保存されること | API 実行検証 | ☐ |

* **⚠️ 不合格時の対処手順**:
  * Lightning LoRA で顔の陰影が崩れる $\rightarrow$ LoRA strength を `0.8` に下げるか、案2（標準モデル 20 steps、約13秒）を採用。
  * VRAM が 14.5GB を超える $\rightarrow$ FaceDetailer の `guide_size` を 768 から 512 に調整、または tiled_decode 有効化。

---

## 3. フェーズ間の連携と全体マイルストーン

```
【Phase 3-A】本人同一性・アニメ画質の確立 (ポートレート)
     │
     ▼ 🚧 Gate 3-A 合格 (似ている！美麗！)
【Phase 3-B】動的ポージング・表情と顧客提供品質 (ストーリー連動)
     │
     ▼ 🚧 Gate 3-B 合格 (かっこいい！ポーズ追従！提供価値成立！)
【Phase 3-C】生成時間短縮・展示運用最適化 & API確定 (高速化)
     │
     ▼ 🚧 Gate 3-C 合格 (早い！安定！API JSON確定！)
【Phase 4】FastAPI オーケストレーター統合 (ASR ➔ LLM ➔ ComfyUI)
```

---

## 4. 今回の検証方針の決定

以上の体系に基づき、**まずはすべての土台となる「Phase 3-A（顔特徴・本人同一性とアニメ品質の確立）」に全リソースを集中** します。
ポーズ指定や高速化 LoRA を一旦切り離し、Phase 3-A の Gate 合格を目指して検証を進めます。

---

## 5. Phase 3-A 具体的手順書（ComfyUI 操作仕様書）

ユーザー様が ComfyUI 上で迷わず実施できるよう、現在構築されているワークフロー（JSON `f18856ec-7f35-41b9-bc2f-69126996bcb1`）に対する具体的な変更箇所と設定値を以下に定義します。

### 5.1 前提モデル配置確認
* **Checkpoint**: `animagine-xl-3.1.float8_e4m3fn.safetensors` (Node 1)
* **InstantID**: `ip-adapter.bin` (Node 14) ＋ `diffusion_pytorch_model.safetensors` (Node 13) ＋ `antelopev2` (Node 17)
* **WD14 Tagger**: `wd-swinv2-tagger-v3` (Node 19)
* **FaceDetailer Bbox**: `bbox/face_yolov8m.pt` (Node 22)
* **テスト写真**: `reWIN_20260204_20_46_41_Pro.jpg` (Node 12)

### 5.2 ノード別設定変更手順（Step-by-Step：髪型・外見一致是正仕様）

#### Step 1: 【構図・外見特徴の指定】Node 21 `StringConcatenate` の設定
* **目的**: 顔中心の構図を保ちつつ、本人の最大の特徴である「短髪・坊主頭（buzz cut）」「広い額（exposed forehead）」「穏やかな微笑み（gentle smile）」を明示指定する。
* **設定変更**:
  * `string_a` に以下のテキストを入力:
    ```text
    masterpiece, best quality, very aesthetic, anime art style,
    solo, portrait, close-up face, upper body, looking at viewer,
    buzz cut, very short hair, exposed forehead, gentle smile,
    detailed facial features, sharp focus, simple background
    ```
  * `string_b`: Node 19 (WD14 Tagger) の出力 `STRING` が接続されている状態を維持。
  * `delimiter`: `, ` を維持。

#### Step 2: 【本人顔立ちの固定】Node 18 `ApplyInstantIDAdvanced` (Base用) の設定
* **目的**: 写真の目鼻立ち・輪郭を確実に転写する。
* **設定変更**:
  * `ip_weight`: `0.70〜0.72` （維持）
  * `cn_strength`: `0.25` （維持）
  * `end_at`: `1.0` （維持）

#### Step 3: 【フル品質サンプリング】Node 2 `KSampler` の設定
* **設定変更**:
  * `steps`: `30` （維持）
  * `cfg`: `6.5` （維持）
  * `sampler_name`: `euler_ancestral`
  * `scheduler`: `karras`
  * `denoise`: `1.0`

#### Step 4: 【前髪の発生を強力抑止】Node 6 `CLIPTextEncode` (Negative) の設定
* **目的**: SDXL モデルがアニメ男子のデフォルトとして勝手に前髪を描いてしまうのを徹底的にブロックする。
* **設定変更**:
  * 既存のネガティブプロンプトの先頭に以下を追加:
    ```text
    bangs, fringe, long bangs, hair over eyes, hair over forehead, medium hair, long hair,
    ```
    *(※元々の lowres, bad anatomy 等の前にカンマ区切りで配置)*

#### Step 5: 【別人化・首折れの完全阻止】Node 25 および Node 20 (`FaceDetailer`) の設定
* **設定変更**:
  * **Node 25 (`ApplyInstantIDAdvanced` 2個目)**:
    * `cn_strength`: `0.0` （ControlNet 骨格拘束を完全ゼロ化）
    * `ip_weight`: `0.45`
    * `end_at`: `0.70〜1.0`
  * **Node 20 (`FaceDetailer`)**:
    * `denoise`: `0.25` （元顔を壊さない上限値）
    * `bbox_crop_factor`: `1.4` （首や肩を巻き込まず顔と前髪だけを精密処理）
    * `feather`: `10`
    * `steps`: `20`

#### Step 6: 【外見属性の確実な抽出】Node 19 `WD14Tagger|pysssss` の設定
* **目的**: 写真から `buzz cut` や `short hair` などの髪型タグが閾値漏れするのを防ぎ、また表情タグ（smile）の誤遮断を解除する。
* **設定変更**:
  * `threshold`: `0.40` $\rightarrow$ **`0.25`** （感度を引き上げ、髪型タグを確実に抽出）
  * `exclude_tags`: 文字列から **`smile, `** を削除（本人の穏やかな微笑みを活かす）
  * `replace_underscore`: `true`
  * `trailing_comma`: `false`

#### Step 7: 生成実行と確認手順
1. 右上の **「Queue Prompt」** をクリックして生成を実行。
2. **Node 26 (`PreviewImage`)**: Base 生成画像で「額が露出した短髪・坊主頭になっているか」を確認。
3. **Node 9 (`SaveImage`)**: FaceDetailer 適用後の完成画像で「眼鏡・瞳・目元が高精細化され、前髪が生えていないか」を確認。

---

## 6. 検証実行記録（Phase 3-A ログ台帳）

検証の履歴を確実に残すため、ComfyUI での生成結果はこの計画書内の以下の記録台帳に直接追記・Git 管理します。

### 実行履歴一覧
| Run ID | 実施日時 | 主要設定 | Gate 3-A 判定 | 結果・所感・課題 |
| :--- | :--- | :--- | :---: | :--- |
| **RUN-3A-00** | 2026-10-11 | 初期構成 (Base 20st, FD 0.45, 全身構図) | ❌ NG | 構図分散、FD による別人化・首折れ懸念 |
| **RUN-3A-01** | 2026-10-12 | ポートレート固定、ip 0.70, cn 0.25, end 1.0, 30st, FD denoise 0.25, crop 1.4 | 🔺 改善・一部NG | 画質・眼鏡・目元は美麗化。しかし**髪型が全く不一致（短髪・坊主頭が前髪垂れ長髪化）** |
| **RUN-3A-02** | *(次回)* | WD14 閾値 0.25、Negative に `bangs` 追加、髪型タグ (`buzz cut, forehead`) 補強 | *(判定待ち)* | 髪型不一致の解消と本人同一性確立トライ |

---

### [記録: RUN-3A-01] ポートレート固定と低denoise FaceDetailer 評価
* **実施日時**: 2026年10月12日
* **入力写真**: `reWIN_20260204_20_46_41_Pro.jpg` (短髪・坊主頭、額全開、眼鏡、穏やかな微笑み)
* **設定パラメータ**:
  - Node 21: `masterpiece, best quality, very aesthetic, anime art style, solo, portrait, close-up face, upper body, looking at viewer, detailed facial features, sharp focus, simple background` ＋ WD14 出力
  - Node 18: `ip_weight: 0.70`, `cn_strength: 0.25`, `end_at: 1.0`
  - Node 2 (KSampler): `steps: 30`, `cfg: 6.5`, `euler_ancestral`, `karras`
  - Node 25: `ip_weight: 0.45`, `cn_strength: 0.0`, `end_at: 1.0`
  - Node 20 (FaceDetailer): `denoise: 0.25`, `bbox_crop_factor: 1.4`, `feather: 10`, `steps: 20`
  - Node 19 (WD14 Tagger): `threshold: 0.40` ➔ 出力 tags: `black hair, 1boy, male focus, glasses, black eyes, rimless eyewear`
* **Gate 3-A 判定結果**:
  - [x] A-2 美麗アニメ品質: **合格（極めて美麗なセル画調、瞳のハイライト、ライティング良好）**
  - [x] A-3 `solo` 遵守: **合格（1名のみ、コラージュ・分裂なし）**
  - [x] A-4 別人化の非発生: **合格（FD denoise 0.25 により Base の顔立ちが破綻せず高精細化）**
  - [ ] A-1 本人同一性: **不合格（致命的課題: 髪型が全く異なり、前髪の長い別人の髪型になっている。また表情が真顔・シリアス化）**
* **根本原因分析**:
  1. **InstantID の特性**: 顔認識モデル (InsightFace) は顔パーツ（目鼻口）のみを抽出し、**髪型の特徴量は持たない**。
  2. **WD14 のタグ欠落**: 閾値 0.40 により `buzz cut` や `short hair` が漏れ、`black hair` のみ出力された。
  3. **プロンプトとSDXLのバイアス**: 髪型指定がないため、SDXL が「アニメ男子の標準（前髪あり）」を勝手に描画した。
  4. **ネガティブの不足**: ネガティブに `bangs`（前髪）が入っていないため、前髪の発生を抑制できなかった。

---

### [次回記入欄: RUN-3A-02] 髪型・額露出の是正検証
* **対象フェーズ**: Phase 3-A
* **対策方針**:
  1. Node 19 (WD14 Tagger): `threshold: 0.25` に引き下げ、写真から `buzz cut` / `short hair` / `forehead` を確実に抽出。
  2. Node 6 (Negative): **`bangs, fringe, long bangs, hair over eyes, medium hair, long hair`** を追加し前髪を強力に抑止。
  3. Node 21 (`string_a`): **`buzz cut, very short hair, exposed forehead, gentle smile`** を明示補強。
* **生成画像 (Node 9)**: 
* **Gate 3-A 判定**:
  * [ ] A-1 本人同一性 (短髪・額露出・眼鏡・微笑みが一致しているか)
  * [ ] A-2 美麗アニメ品質 (セル画塗り・瞳のハイライト)
  * [ ] A-3 `solo` 遵守 (1名のみ、コラージュなし)
  * [ ] A-4 別人化の非発生 (Base の顔立ちが維持されている)
* **評価メモ・気づき**: 
 


