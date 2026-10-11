# StoryWeaver Live Phase 3計画改訂指示プロンプト

以下の指示に従って、StoryWeaver LiveのPhase 3再構築・検証計画を全面的に改訂してください。

この文書は、計画作成AIへそのままコピー＆ペーストして使用するための指示です。

---

## 役割

あなたは、ローカルAI画像生成、ComfyUI、画像編集モデル、人物一致性、FastAPI、Ollama、Windows GPU運用、展示システム設計に詳しいシニア技術アーキテクトです。

以下の既存計画をベースに、最新のWeb情報と公式ドキュメントを再調査したうえで、実装可能性を再評価し、同じ粒度以上の詳細な改訂版計画を作成してください。

単なる文章の修正ではなく、次の内容を含む**実装可能な計画書**にしてください。

- 目的と制約
- 最新情報の調査結果
- モデル・ノード・ファイル構成
- VRAM/RAM/処理時間の見積もり
- FastAPI/Ollama/ComfyUIの連携
- 段階的な検証手順
- 失敗時のfallback
- 評価指標
- ライセンス・個人情報・安全面
- 実装順序
- 受け入れ基準

---

## 最重要指示：Webを再調査すること

計画を作成する前に、必ずWeb検索を実施してください。

前回の調査結果をそのまま信用せず、**計画作成時点で最新の公式情報を再確認**してください。特に、モデルの現存性、モデル名、ファイル名、ComfyUIテンプレート、必要ノード、必要ファイル、ライセンス、VRAM、推奨steps、推奨CFG、参照画像仕様を確認してください。

可能な限り、公式一次情報を優先してください。

### 必ず確認する情報源

1. Microsoft Mage公式プロジェクトページ
   - https://microsoft.github.io/Mage/flow/
2. Microsoft Mage公式GitHub
   - https://github.com/microsoft/Mage
3. Mage-Flow公式README
   - https://github.com/microsoft/Mage/blob/main/mage_flow/README.md
4. ComfyUI公式Mage-Flowワークフロー
   - https://docs.comfy.org/tutorials/image/mage-flow/mage-flow
5. Comfy-Org Mage-Flowモデルページ
   - https://huggingface.co/Comfy-Org/Mage-Flow
6. Black Forest Labs公式FLUX.2リポジトリ
   - https://github.com/black-forest-labs/flux2
7. ComfyUI公式FLUX.2 Kleinガイド
   - https://docs.comfy.org/tutorials/flux/flux-2-klein
8. FLUX.2 Klein 4B公式モデルカード
   - https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
9. ComfyUI公式ドキュメント
   - https://docs.comfy.org/
10. ComfyUI Impact Pack公式リポジトリ
    - https://github.com/ltdrdata/ComfyUI-Impact-Pack
11. Ollama公式Gemma 4 E2B
    - https://ollama.com/library/gemma4:e2b

### Web調査で必ず明記すること

各モデル・ツールについて、次を表形式で整理してください。

| 項目 | 確認内容 |
|---|---|
| 現存性 | 現在アクセス可能か |
| 公式URL | 実際に確認したURL |
| 正式モデル名 | 大文字小文字を含めて正確に記載 |
| 配布元 | Microsoft、Comfy-Org、Black Forest Labs等 |
| ComfyUI対応 | 公式テンプレートの有無 |
| 必要ファイル | モデル、VAE、text encoder等 |
| 量子化版 | Int8、FP8、BF16等 |
| 推奨steps | Base、Turbo、Distilledごとに記載 |
| CFG/guidance | モデル別に記載 |
| 参照画像 | 枚数、入力方法、制約 |
| VRAM | 公式値と実機未確認値を分ける |
| ライセンス | モデルとカスタムノードを分ける |
| 注意事項 | 404、gated、バージョン依存等 |

検索結果のスニペットだけを根拠にせず、必ず元ページを開いて内容を確認してください。

公式情報に記載がない内容は、推測で断定しないでください。以下のように書き分けてください。

- 公式に確認できた事実
- コミュニティ報告
- 実機で検証が必要な仮説
- 現時点では不明な点

---

## 既存の前提条件

以下の前提は維持してください。

- システム名：StoryWeaver Live
- 用途：AI展示ブース
- 入力：来場者の顔写真
- 出力：来場者の特徴を維持したアニメ調イラスト
- ハードウェア：ThinkPad X1 Extreme
- CPU：Core i9
- GPU：RTX 3080 Laptop GPU
- GPU VRAM：16GB
- RAM：32GB
- OS：Windows
- ローカル実行が前提
- クラウドAPIへの画像送信は前提にしない
- 来場者の撮影は正面からの1回シャッターを原則とする
- 複数アングル撮影は展示オペレーション上、極力避ける
- FastAPIをオーケストレーターとして使用する
- Ollamaをシナリオ・プロンプト生成に使用する
- LLMとComfyUI画像生成を同時にGPU常駐させず、直列化する
- LLMには直接ファイルパスを生成させない
- 事前定義したasset_idを出力させ、FastAPI側でパスを解決する
- batch sizeは1を原則とする
- 個人写真はローカルで処理し、保存期間を最小化する

---

## 改訂対象のモデル候補

次のモデルを、最新情報に基づいて再評価してください。

1. Mage-Flow-Edit-Turbo
   - ComfyUI向けInt8版
   - 4 steps
2. Mage-Flow-Edit
   - ComfyUI向けInt8版
   - 30 steps
3. FLUX.2 Klein 4B Distilled
   - FP8版
   - 4 steps
4. FLUX.2 Klein 4B Base
   - 品質上限確認用
   - 公式推奨stepsを確認すること
5. 既存のInstantIDワークフロー
   - 比較対照群として一時的に維持

### モデル比較に関する重要な変更

Mage-FlowとFLUX.2 Kleinは、同じ一般的なKSampler構成として扱わないでください。

両者は、以下が異なるモデル固有のワークフローです。

- text encoder
- VAE
- diffusion model
- 画像参照条件の処理
- サンプリング方式
- steps
- CFG/guidance
- ComfyUIノードまたはサブグラフ

したがって、改訂計画では以下のように分けてください。

```text
共通：FastAPI SceneSpec、asset_id、queue、history、結果取得

Mage専用：公式Mage-Flow Editサブグラフ
FLUX専用：公式FLUX.2 Klein Editサブグラフ
```

「Model Loader → Instruction Text Encode → KSampler → VAE Decode」という構成は、概念図として使う場合を除き、実装手順として記載しないでください。

各モデルについて、公式テンプレートの実際のノード名・サブグラフ名・入力位置・モデルファイル名を記載してください。

---

## ComfyUI設計の改訂要件

### 共通のFastAPI契約

以下のようなモデル非依存のSceneSpecを設計してください。

```json
{
  "model_id": "mage_flow_edit_turbo_int8",
  "identity_asset_id": "visitor_001_face_v1",
  "scene_asset_id": "fantasy_city_day_v2",
  "style_asset_id": null,
  "instruction_en": "...",
  "width": 768,
  "height": 1024,
  "seed": 12345,
  "quality_mode": "preview"
}
```

ただし、最終的なJSON形式は最新調査結果に基づき改善して構いません。

必ず以下を含めてください。

- JSON Schema
- asset_id allowlist
- asset_idから実ファイルへの解決
- ファイル存在確認
- MIME type確認
- 解像度上限
- ファイルサイズ上限
- 参照画像枚数上限
- prompt長上限
- model_idのallowlist
- seedの扱い
- タイムアウト
- エラーコード
- 実行ログ

### Mage-Flow固有設計

次を公式情報から確認して記載してください。

- Mage-Flow Edit公式サブグラフ
- Edit TurboとEditの違い
- 参照画像の最大枚数
- 入力画像の順序
- 公式のsteps
- 公式のCFG
- `max_size`
- `vl_cond_long_edge`
- batch_cfg
- Mage-VAE
- Qwen3-VL 4B
- Int8モデルファイル名
- ComfyUI配置先
- 公式テンプレートの取得方法

### FLUX.2 Klein固有設計

次を公式情報から確認して記載してください。

- 4B DistilledとBaseの違い
- 公式ComfyUIサブグラフ
- 参照画像の入力方法
- text encoder
- VAE
- FP8ファイル名
- ComfyUI配置先
- steps
- guidance
- multi-reference editingの仕様
- 公式VRAM情報
- 4Bと9Bのライセンス差

---

## VRAM・RAM・直列化の改訂要件

以下の単純な配分表は使用しないでください。

```text
OS 1.5GB + 画像モデル8GB + Ollama 2.2GB + 安全余白4.3GB = 16GB
```

この計算は、ピーク時の一時テンソル、CUDA allocator、VAE、text encoder、ComfyUIキャッシュ、Ollama KV cacheを含まないため、保証値として不適切です。

改訂版では、次を分けて記載してください。

- ファイルサイズ
- 常駐VRAM
- 推論ピークVRAM
- CPU RAM
- 一時テンソル
- cold start
- warm start
- 参照画像1枚時
- 参照画像2枚時
- 参照画像3枚時
- 1024×1024
- 768×1024
- FaceDetailerなし
- FaceDetailerあり

公式測定値と、RTX 3080 Laptop 16GBでの未検証値を混同しないでください。

### LLMとComfyUIの直列化

「LLM退避後に画像生成」とだけ書かず、実装手順を具体化してください。

最低限、次のどれを採用するか決めてください。

#### 方式A：LLMをCPU中心で実行

- GPU使用量
- 処理時間
- Ollama設定
- CPU RAM

#### 方式B：LLM応答後にOllamaプロセス／モデルを停止

```text
1. OllamaにSceneSpec生成要求
2. JSON受信
3. Ollama stopまたはモデル解放
4. 数秒待機
5. nvidia-smiでVRAM解放確認
6. ComfyUIへqueue投入
```

#### 方式C：GPU offloadを明示

使用するOllamaバージョンで実際の設定方法を確認してください。

「LLM応答が終わった」ことと「GPU VRAMが解放された」ことを同一視しないでください。

### 必ず含める実測コマンド・ログ項目

- `nvidia-smi`
- GPU VRAM使用量
- GPU温度
- GPU使用率
- CPU RAM使用量
- ページファイル使用量
- ComfyUI queue時刻
- 生成開始時刻
- 生成終了時刻
- API返却時刻

---

## 処理時間の改訂要件

元の10秒目標は、次のように二段階へ整理してください。

| 区分 | 目標 |
|---|---:|
| Fast pathの最初の目標 | p95 30秒以内 |
| Stretch目標 | p95 10秒以内 |
| ハードタイムアウト | 180秒 |
| タイムアウト時 | fallbackまたは再試行 |

この時間には次を含めてください。

- 撮影画像保存
- 画像リサイズ
- LLM生成
- JSON検証
- asset_id解決
- Ollama停止／GPU解放
- ComfyUI upload
- queue待ち
- モデルロード
- text encoder
- diffusion
- VAE Decode
- FaceDetailer
- output取得
- HTTPレスポンス返却

cold startとwarm startを分け、各条件30回以上の測定を計画してください。

また、3分待つ場合の展示画面設計も追加してください。

```text
シナリオを構成中
人物を場面に配置中
画風を調整中
最終化中
```

ComfyUIのqueue/history/WebSocket等を使った進捗取得方法も記載してください。

---

## FaceDetailerの改訂要件

FaceDetailerは、常時実行ではなく、条件付きの二段階処理としてください。

```text
1. MageまたはFLUX.2 Kleinで全体生成
2. 顔品質評価
3. 閾値未満の場合だけFaceDetailer
4. 補正前後の人物一致性評価
5. 改善時のみ補正画像を採用
```

次を明記してください。

- 顔検出モデル
- FaceDetailerの依存
- Impact PackとImpact Subpackの違い
- ComfyUI互換バージョン
- 追加モデル
- VRAM追加量
- 処理時間追加
- GPL-3.0ライセンス
- FaceDetailerが別人化するリスク
- 補正前画像を必ず保存すること
- 補正結果を自動採用しない条件

FaceDetailerを「人物一致性の保証機構」と表現しないでください。FaceDetailerは顔品質補正機構です。

---

## 段階的検証手順の改訂要件

Level 1〜4を残しつつ、入力枚数だけでなく、機能別に分解してください。

### Level 1A：人物保持のみ

正面写真1枚を入力し、構図と人物特徴をできるだけ維持する。

### Level 1B：アニメ化のみ

背景を変えず、アニメスタイルへの変換だけを行う。

### Level 1C：背景変更のみ

人物を変えず、背景だけを変更する。

### Level 2：人物＋背景

- Image 1：来場者の正面写真
- Image 2：人物なしの背景・シーン画像
- instructionで役割を明示

背景画像に別人が写っている素材は避けてください。

### Level 3：疑似マルチアングル

必ず以下を比較してください。

- 3A：顔アップ＋上半身を1枚に合成
- 3B：顔アップ＋上半身を別々の参照画像として入力
- 3C：元写真1枚をそのまま入力

「疑似キャラクターシートによりAttentionが同一人物として統合される」と断定しないでください。

正しい位置づけは、以下です。

> 疑似マルチアングルは、1枚の写真から異なるスケールの特徴を与える仮説的手法であり、真の複数視点や専用顔ID条件付けではない。

### Level 4：開発用の真の複数アングル

本番来場者には要求せず、スタッフまたはテスト協力者で比較用データセットを作成してください。

- 正面
- 左右斜め
- 横顔
- 上半身
- 表情違い

このLevelは本番運用案ではなく、人物一致性の上限を測る対照群としてください。

---

## 疑似マルチアングルの理論レビュー要件

以下を説明してください。

- 画像がVAE・視覚エンコーダでトークン化されること
- 画像トークンとテキストトークンがAttentionへ入力されること
- 合成シートは専用の人物ID埋め込みではないこと
- 顔アップが局所特徴を強める可能性
- 顔アップと上半身の重複・混乱の可能性
- 新しい視点の情報は生成されないこと
- 4-step蒸留で細部保持が低下する可能性
- 別参照画像と合成シートを比較すべきこと

評価では、次を組み合わせてください。

- 本人または第三者のブラインド同一人物判定
- 顔埋め込み類似度
- 眼鏡、ほくろ、髪型、輪郭などの属性一致
- 顔占有率
- 背景達成度
- アニメ画風達成度
- ポーズ達成度
- 生成失敗率

---

## モデル比較と評価基準

次の比較マトリクスを作成してください。

```text
Mage Turbo
Mage Edit
FLUX.2 Klein Distilled
FLUX.2 Klein Base
InstantID対照
```

最低限、以下のテスト画像・条件を用意してください。

- P1：顔が大きい正面写真、背景変更のみ
- P2：顔が大きい正面写真、アニメ化のみ
- P3：正面写真＋人物なし背景
- P4：顔crop＋上半身cropの別画像
- P5：顔crop＋上半身cropの合成シート
- P6：開発用真の複数アングル
- P7：大きなポーズ変更
- P8：遠景構図

各条件について、seedを最低5種類以上使用してください。

評価表には次を含めてください。

| 評価軸 | 内容 |
|---|---|
| 人物一致性 | 顔、輪郭、髪型、眼鏡、ほくろ、年齢印象 |
| 背景一致性 | 指定シーン・assetとの一致 |
| アニメ品質 | 線、色、陰影、破綻 |
| ポーズ | 指示された構図との一致 |
| 速度 | p50、p95、最大値 |
| VRAM | peak VRAM |
| RAM | peak RAM |
| 成功率 | OOM、ノードエラー、別人化を含む |
| 再現性 | seed間の安定性 |

合格基準の例も作成してください。

- 顔一致性平均4.0/5以上
- 眼鏡や特徴的属性の保持率90%以上
- OOM 0回
- 生成成功率95%以上
- Fast path p95 30秒以内
- ハードタイムアウト180秒以内

数値は仮置きでよいですが、「本番前に実際の評価者で校正する」と明記してください。

---

## セキュリティ・個人情報・展示運用

次を計画に追加してください。

- 来場者の顔写真を保存するかどうか
- 保存する場合の保存期間
- エラー時の一時ファイル削除
- ログに顔画像のパスや個人情報を残さない方法
- 同意表示
- 画像をクラウドへ送信しないことの明示
- 管理者だけがテスト画像へアクセスできること
- ファイル名を来場者名にしないこと
- SHA-256またはランダムIDによる管理
- 出力画像の自動削除
- USBやバックアップへのコピー制御
- 展示終了時のデータ消去

---

## 最終的な計画書の構成

以下の章構成で、前回と同じ粒度以上の計画を作成してください。

1. エグゼクティブサマリー
2. 現行計画からの変更点
3. 目的と非目的
4. ハードウェア・ソフトウェア前提
5. 最新Web調査結果
6. モデル比較
7. Mage-Flow固有設計
8. FLUX.2 Klein固有設計
9. 共通FastAPI/SceneSpec設計
10. Ollama直列化設計
11. ComfyUI API連携
12. アセット管理
13. ComfyUIワークフロー構成
14. FaceDetailerの条件付き処理
15. Level 1〜4検証手順
16. 疑似マルチアングルの理論と検証
17. VRAM/RAM/時間計測計画
18. p50/p95/timeout設計
19. 品質評価指標
20. エラー処理とfallback
21. 個人情報・同意・ライセンス
22. 実装フェーズと作業順序
23. 受け入れ基準
24. 未解決事項とリスク
25. 参照URL一覧

---

## 出力要件

- 日本語で作成する
- Markdownで作成する
- 表を積極的に使用する
- 公式情報と推測を明確に分ける
- URLを本文と参照一覧に記載する
- 「実装可能」「要実機検証」「未確認」を明示する
- モデル名、ファイル名、steps、CFG、VRAM、ライセンスを曖昧にしない
- 既存案を単に肯定せず、技術的な欠陥を指摘する
- 10秒目標を保証値として書かない
- FaceDetailerを人物一致性保証と書かない
- 疑似キャラクターシートを人物ID保証と書かない
- MageとFLUX.2 Kleinを同じKSamplerワークフローと書かない
- Web調査日を明記する
- 最後に「採用推奨案」「保留案」「廃止案」を明確に分ける

最終的には、開発者がそのまま実装タスクへ分解できる粒度の計画書にしてください。
