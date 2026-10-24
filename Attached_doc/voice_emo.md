# プロジェクト概要：音声からの12感情・色気スコア算出モジュールの実装と StoryWeaver Live 統合

## 1. 目的とターゲット環境
マイクから入力された「指定セリフ（3〜5秒の日本語音声・16kHz モノラル WAV）」を解析し、AI感情モデル（3次元VAD）と音響物理特徴量（eGeMAPSv02）をハイブリッド合成して、画像生成プロンプト制御用の「12種類の感情・色気パラメータ（0〜100点）」を算出するモジュールを作成し、StoryWeaver Live の拡張感情分析モードとして統合せよ。

- **実行環境:** Windows 11 (ThinkPad X1 Extreme Gen 4 / RAM 32GB)
- **GPU / CPU方針:** NVIDIA GeForce RTX 3080 Laptop GPU (VRAM 16GB)。
  - **【重要】StoryWeaver Live の VRAM 上限（14.5GB）および「音声処理は VRAM 0MB」の原則を守るため、本モジュールは原則として CPU 推論（`device="cpu"`）で動作させ、VRAM 増分 0MB を維持すること。**（CPU で 0.5秒を超過し GPU 推論を有効化する場合でも、推論完了直後にモデルを CPU へ退避し `torch.cuda.empty_cache()` を実行して ComfyUI 実行前に VRAM を完全解放すること）。
- **性能要件:** モデルのウォームアップ完了後、1音声あたりの推論＋解析時間が **CPU 実行時 0.8秒以内（GPU 実行時 0.3秒以内）** であること。

---

## 2. 役割分担（開発AIと人間の分担）

| フェーズ | 担当 | 実施内容 |
| :--- | :--- | :--- |
| **① 構築フェーズ** | **開発AI** | ・必要ライブラリ（`transformers`, `opensmile` 等）の導入<br>・AI感情モデル（`wav2vec2-msp-dim`）と音響解析（`openSMILE eGeMAPSv02`）の統合モジュール（`voice_emo_analyzer.py`）作成<br>・基準音声（棒読み）との差分計算および12感情スコア算出ロジックの実装<br>・`server.py` およびフロントエンド UI への「分析モード切替」「ベースライン登録」の統合 |
| **② 自動検証フェーズ** | **開発AI** | ・合成テスト音声（WAV）のプログラムによる自動生成（`self_test_voice_emo.py`）<br>・パイプライン動作検証（エラーや `NaN` なく7基礎特徴量と12感情スコアが出力されるか確認）<br>・パフォーマンス検証（推論時間および VRAM 増分 0MB の計測） |
| **③ 実機発声フェーズ** | **人間** | ・UI または CLI からマイクで指定セリフを「①棒読み（基準登録）」「②吐息多め（色気）」「③優しい声（慈愛）」「④低く硬い声（憎しみ）」等で吹き込む<br>・出力された数値と生成画像を確認し、必要に応じて開発AIへ係数調整を指示する |

---

## 3. 技術スタックと使用モデル（厳守）
推測で別のモデルや未検証のライブラリに置き換えず、以下の指定構成で実装すること。

1. **3次元感情認識モデル:**
   - モデル名: `audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim` (`transformers` 経由でロード)
   - 出力: `Arousal`（覚醒度）, `Dominance`（支配性）, `Valence`（快・不快）の3つの連続値（概ね0.0〜1.0の範囲）
   - 実装上の注意: このモデルはカスタム分類ヘッドを持つため、HuggingFace公式モデルカードの実装例に従い、`Wav2Vec2PreTrainedModel` を継承したカスタムクラス（`RegressionHead` および `EmotionModel`）を定義して正しく重みをロードすること。入力音声のサンプリングレートは **16,000Hz (モノラル)** に統一すること。

2. **音響物理特徴量抽出（CPU処理）:**
   - ライブラリ: `opensmile` (`Smile(feature_set=opensmile.FeatureSet.eGeMAPSv02, feature_level=opensmile.FeatureLevel.Functionals)`)
   - 抽出する主要カラム（と対応する意味）:
     - **吐息・息漏れ感 (Breathiness):** `logRelF0-H1-H2_sma3nz_amean`（H1-H2振幅差：高いほど息漏れ声）および `HNRdBACF_sma3nz_amean`（調波対雑音比：低いほど息成分が多い）
     - **声の柔らかさ (Softness):** `alphaRatioV_sma3nz_amean` および `hammarbergIndexV_sma3nz_amean`（スペクトル傾斜：高域エネルギーが穏やかなほど柔らかい声）
     - **ゆったり感・余韻 (Slowness):** 有音区間の発話長（秒）および `loudnessPeaksPerSec`（秒間ピーク数が少ないほどゆったりした発話）
     - **声の微細揺らぎ (Tremor):** `jitterLocal_sma3nz_amean`（ピッチ揺らぎ）および `shimmerLocaldB_sma3nz_amean`（振幅揺らぎ）

3. **セリフ文字起こしとの連携:**
   - 本モジュールは感情・音響スコアの算出に特化する。Phase 4 の「録音セリフの文字起こし反映」には、既存の `SenseVoiceSmall`（CPU）によるテキスト認識結果をそのまま併用すること。

---

## 4. 作成・更新するファイル構成
既存の `config.json` と衝突しないよう、専用の設定ファイル名を使用すること。

1. `voice_emo_config.json` : 7つの基礎指標の正規化パラメータ（初期平均・標準偏差）、12感情スコアの重み係数、および各感情に対応する Animagine XL 3.1 用プロンプト辞書を格納する設定ファイル。
2. `voice_emo_baseline.json` : 棒読み録音時の各特徴量の平均値を保存するファイル（未作成時はデフォルト値で動作）。
3. `voice_emo_analyzer.py` : モデルのロード、音声波形からの7基礎特徴量の抽出、キャリブレーション（`voice_emo_baseline.json` との差分正規化）、12感情スコア＋画像生成プロンプト算出を行うコアモジュール。
4. `calibrate_and_evaluate.py` : マイクを使って対話式で単体テスト・基準登録するためのCLIスクリプト（モード1：ベースライン登録、モード2：演技採点テスト）。
5. `self_test_voice_emo.py` : 開発AI自身がパイプラインの動作と性能を自動検証するためのテストスクリプト。
6. `server.py` ＆ フロントエンドUI（既存ファイルの拡張）:
   - `config.json` に `emotion_mode`: `"standard"`（従来の SenseVoice + 声量5段階）または `"detailed_12"`（本モジュールによる12感情分析）の切替設定を追加。
   - スタッフ設定画面から「感情分析モードの切替」と「棒読みベースラインの録音・登録（`POST /api/calibrate_voice_emo`）」を実行可能にする。

---

## 5. 7つの基礎指標の正規化と12感情スコアの計算仕様 (`voice_emo_analyzer.py`)

### (1) 7つの基礎指標（0〜100点への正規化）
`voice_emo_baseline.json`（棒読み時の平均値）が存在する場合は、棒読み時の値を「50点」とし、そこからの変化量（シグモイド関数または線形スケーリング＋0〜100クリップ）で0〜100点に変換すること。未登録時は `voice_emo_config.json` の標準初期閾値で0〜100点に正規化する。
- `valence` (快・ポジティブ度)
- `arousal` (覚醒度・テンション)
- `dominance` (支配性・力強さ)
- `breathiness` (吐息・息漏れ感：H1-H2が高く、HNRが低いほど高スコア)
- `softness` (声の柔らかさ：Alpha Ratioが低く、高域の刺々しさがないほど高スコア)
- `slowness` (ゆったり感・余韻：発話時間が基準より長く、`loudnessPeaksPerSec` が低いほど高スコア)
- `tremor` (声の微細揺らぎ：Jitter / Shimmerが高いほど高スコア)

### (2) 12種類の拡張感情パラメータ算出式（0〜100にクリップ）
1. **色気・官能 (Sensuality):** `0.45 * breathiness + 0.30 * slowness + 0.25 * (100 - abs(arousal - 40))`
2. **愛情・親愛 (Affection):** `0.35 * valence + 0.30 * breathiness + 0.20 * softness + 0.15 * arousal`
3. **慈愛・優しさ (Benevolence):** `0.35 * softness + 0.30 * valence + 0.20 * slowness + 0.15 * (100 - arousal)`
4. **自愛・陶酔 (Self-Love):** `0.30 * valence + 0.30 * dominance + 0.25 * slowness + 0.15 * (100 - arousal)`
5. **歓喜・喜び (Joy):** `0.40 * valence + 0.40 * arousal + 0.20 * dominance`
6. **楽しさ・無邪気 (Amusement):** `0.40 * valence + 0.30 * arousal + 0.30 * (100 - slowness)`
7. **哀しみ・憂愁 (Sorrow):** `0.30 * (100 - valence) + 0.25 * (100 - arousal) + 0.25 * (100 - dominance) + 0.20 * tremor`
8. **恥じらい・照れ (Bashfulness):** `0.35 * breathiness + 0.30 * (100 - dominance) + 0.20 * tremor + 0.15 * softness`
9. **激しい怒り (Rage):** `0.35 * (100 - valence) + 0.35 * arousal + 0.20 * dominance + 0.10 * (100 - softness)`
10. **憎しみ・怨念 (Hatred):** `0.40 * (100 - valence) + 0.25 * dominance + 0.20 * (100 - softness) + 0.15 * (100 - arousal)`
11. **軽蔑・冷酷 (Contempt):** `0.30 * (100 - valence) + 0.30 * dominance + 0.20 * (100 - arousal) + 0.20 * (100 - breathiness)`
12. **恐怖・怯え (Fear):** `0.30 * (100 - valence) + 0.30 * arousal + 0.20 * (100 - dominance) + 0.20 * tremor`

### (3) 画像生成プロンプトへの変換仕様（Animagine XL 3.1 適合版）
- スコア上位2つの感情を抽出する。
- Animagine XL 3.1 での構図崩れや塗り破綻を防ぐため、重み変換式は **`round(0.85 + (score / 100) * 0.35, 2)`（最大 1.20）** とする。
- FaceDetailer（`Node_Pos_FD` 案B：表情専念）で背景ライティングタグが混入して顔が濁るのを防ぐため、`voice_emo_config.json` のプロンプト辞書は各感情につき **`face_tags`（表情・目元・口元のみ：Base と FD の両方に使用）** と **`lighting_tags`（照明・雰囲気演出：Base のみに使用）** に分けて定義すること。
  - 例（Sensuality）:
    - `face_tags`: `"seductive half-closed eyes, slightly parted lips, sultry expression, slight blush"`
    - `lighting_tags`: `"magenta and amber rim lighting, moody atmosphere"`

---

## 6. 開発AIが自律的に実行・検証する内容（完了条件）
コードを作成したら、人間に完了報告をする前に**開発AI自身がターミナルで `self_test_voice_emo.py` を実行し、以下の4項目をすべて検証・クリアすること。** エラーが出た場合は自己修正すること。

1. **ダミー音声による単体テスト:**
   - `numpy` で以下の性質を持つ3種類の合成音声（3秒・16kHz WAV）を自動生成する。
     - 音声A（標準トーン：基本周波数200Hz＋倍音）
     - 音声B（疑似ブレス・ゆったり：基本周波数180Hz＋ピンクノイズ混合＋緩やかなエンベロープ）
     - 音声C（疑似緊張・高音硬質：基本周波数350Hz＋強い高次倍音＋振幅変調）
2. **特徴量抽出と数値変動の確認:**
   - 音声A, B, Cを `voice_emo_analyzer.py` に通し、すべての特徴量が `NaN` やエラーにならず数値として取得できることを確認する。
   - 音声Aに比べ、音声Bで `breathiness` が上昇し、音声Cで `softness` が低下することを確認する。
3. **推論速度とVRAM消費量の計測:**
   - ウォームアップ後の推論時間と、VRAM 消費量（CPU 固定により VRAM 増分 0MB であること）を計測する。
4. **API 統合テスト:**
   - `POST /api/analyze_audio` を `emotion_mode: "detailed_12"` で呼び出し、SenseVoice の文字起こしテキストとともに、7基礎指標・12感情スコア・上位2感情のプロンプトが正常に JSON 返却されることを確認する。