# 障害事後分析レポート（Postmortem）: Ollama 0.40.17 アップデート後の VLM 画像認識タイムアウト

* **発生日時**: 2026-11-23 10:36〜10:39 JST
* **対象バージョン**: Ollama `0.40.15` → `0.40.17`（自動更新：`2026-11-23 10:02:50`）、対象モデル `gemma4:e2b`
* **影響範囲**:
  1. サーバー起動時 `_ollama_warmup()` が 120 秒タイムアウトで失敗（Ollama 側 HTTP 500）
  2. Step 1 スタンバイ（`Qwen2-Audio` ロード）直後の Step 2 顔画像認識 `POST /api/analyze_face` が 30 秒タイムアウトで失敗（`504 OLLAMA_TIMEOUT` / Ollama 側 HTTP 500）
  3. `/api/ps` 上の Ollama VRAM 表示が実際（約 3.1 GB）より大幅に少なく（256.9 MB）報告される

---

## 1. 事象タイムライン（`%LOCALAPPDATA%\Ollama\server-1.log` / `upgrade.log` 実測）

1. **10:02:50〜10:04:12**: `OllamaSetup.exe` による `0.40.15` → `0.40.17` へのサイレントアップデート実行。
2. **10:36:36**: StoryWeaver 起動に伴い、`_ollama_warmup()` が `prompt: "ok"`, `keep_alive: 0`, `think` 未指定（120 秒タイムアウト）で `/api/generate` を呼び出し。
3. **10:36:36〜10:38:23**: 0.40.17 の `llama-server.exe`（`--load-mode none`, `--spec-type draft-mtp`, vision/audio 両エンコーダのダミーウォームアップ）の初回起動に **`106.73 seconds`** を要する（2 回目以降は 5〜12 秒）。
4. **10:37:53〜10:38:23**: Step 1 でユーザーが「AIモデルをスタンバイ」を実行。`POST /api/models/standby` が `preload_ollama_model()` を完了（`29.88s`）し、直後に裏で `Qwen2-Audio-7B-Instruct`（4bit）のロード（約 45〜60 秒、CPU/RAM/PCIe 高負荷）を開始。
5. **10:38:35**: 2. の `_ollama_warmup()` が単一スロット待機・思考生成・高負荷競合により **120 秒タイムアウト（`[GIN] 500 | 2m0s`）** でキャンセル。
6. **10:38:49〜10:39:19**: `Qwen2-Audio` ロード進行中にカメラ撮影が実行され、`POST /api/analyze_face`（`sw_crop_20261123_103849_11474d.jpg`）がロックなしで並列突入。`gemma4:e2b` がホスト RAM 上の重み（`CUDA_Host model buffer size = 2152.50 MiB`）と競合し、プロンプト処理速度が **`3.87 tokens/sec`** まで低下、画像エンコード（`encode_mtmd_`）だけで 27 秒以上を費やし、**30.07 秒で `OLLAMA_TIMEOUT`（504）** により失敗。

---

## 2. Ollama 0.40.17 の仕様変化と根本原因（5 点）

| # | 要因 | 詳細・実測値 |
| :-: | :--- | :--- |
| 1 | **VLM 呼び出し時の `think` パラメータ未指定** | 0.40.17 上の `gemma4:e2b` は `thinking` がデフォルト `true`（音声 Step 2 は `think=False` 指定済みだったが、`verify_step1_vlm.py` の画像認識には未指定）。毎回 1,300〜2,600 文字の思考テキストを生成し、推論時間が約 4〜5 倍に増大。 |
| 2 | **`analyze_face` と `standby` の排他制御欠如** | `POST /api/models/standby` が `QWEN2_LOCK` 配下で `Qwen2-Audio` をロードしている最中に、`POST /api/analyze_face` がロックなしで並列実行された。0.40.17 では `gemma4:e2b` が `CUDA_Host` に `2,152.50 MiB` を配置するため、RAM/PCIe 帯域競合で `3.87 tokens/sec` まで失速した。 |
| 3 | **起動時 `_ollama_warmup()` の競合・誤設定** | `prompt: "ok"`・`think` 未指定・`keep_alive: 0`・ロックなしで実行していたため、初回起動 106.73s と相まって 120s でタイムアウトし、直後のリクエストとも単一スロットを奪い合った。 |
| 4 | **コールドロードと推論の 30 秒枠混在** | `AGENTS.md` §3-② の Ollama 単体推論タイムアウト（30 秒）の中に初回/再ロード時間（5〜107 秒）が混在しており、未ロード時の直接推論がタイムアウトしやすかった。 |
| 5 | **`/api/ps` の `size_vram` 過小報告** | `llamacpp` ランナー＋`draft-mtp` 併用時、実 VRAM 増加 **`3,077 MB`**（`nvidia-smi` 実測: 209 → 3,286 MB）に対して `/api/ps` が **`256.9 MB`** と過小報告するため、UI 表示および `comfy_free_and_wait_vram()` の閾値判定が実態より約 2.8 GB 過小評価されていた。 |

### 参考：全 10 枚テスト画像での VLM 精度・速度比較（`think=True` vs `think=False`）
* **速度**: `think=True` 平均 3.94s/枚（最大 4.45s） vs `think=False` 平均 0.88s/枚（最大 1.63s、約 4.5 倍高速）。
* **精度**: スキーマ適合率は両方 10/10 (100%)。`think=True` は `koji-bose.jpg`（`very short hair` → `buzz cut` + 超短髪ネガ）や `michie.jpg`（薄前髪 `has_bangs=True`）の厳格ルール判定に優れる一方、`think=False` は `tomi.jpg`（性別 `1girl`）や `koji-women-.jpg`（`long hair`）の直感的判定に優れるトレードオフを確認。
* ユーザー方針（案B）に基づき、**デフォルトは `VLM_THINK: true`（厳格抽出優先）とし、`config.json` で `false` へ即時切替可能**な構成とした。

---

## 3. 実施した恒久対策

1. **`verify_step1_vlm.py`**:
   - `call_ollama_vlm()` に `think: bool = True` 引数を追加し、ペイロードへ `"think": bool(think)` を明示設定。CLI にも `--no-think` を追加。
   - Markdown コードフェンス除去および空レスポンス/バリデーション失敗時の詳細情報（`done_reason`, `thinking_len`）付与を追加。
2. **`qwen2_audio_hybrid.py`**:
   - `ensure_ollama_loaded()` を新設し、未ロード時のみ空プロンプト（`prompt: ""`）＋ `OLLAMA_WARMUP_TIMEOUT_SEC`（180 秒）で事前ロード（ロード済みなら即スキップ）。
   - `get_ollama_model_status()` に、`gemma4` / `llamacpp` 環境で `raw_vram_used_mb < 1024 MB` の場合に安全側下限見積もり `OLLAMA_GEMMA4_MIN_VRAM_MB = 3100.0` を返す補正（`vram_estimated: True` 付与）を実装。
   - `_warmup_ollama_bg()` および `analyze_hybrid()` の背景ロード待機タイムアウトを `OLLAMA_WARMUP_TIMEOUT_SEC`（180 秒）へ適正化。
3. **`server.py` / `config.json`**:
   - `config.json` / `DEFAULT_CONFIG` に `OLLAMA_WARMUP_TIMEOUT_SEC: 180` と `VLM_THINK: true` を追加し、`PUT /api/config` に `VLM_THINK` の真偽値バリデーションを追加。
   - 起動時ウォームアップを `_ollama_warmup_async()`（`QWEN2_LOCK` 配下・`ensure_ollama_loaded(..., keep_alive="5m")`）へ刷新し、`prompt: "ok"` と `keep_alive: 0` の競合を撤廃。
   - `POST /api/analyze_face` に `async with QWEN2_LOCK:` を導入し、`Qwen2-Audio` ロードとの CPU/RAM/PCIe 競合を完全排他。さらに `_analyze_blocking()` 内で 2 段階ロード（`ensure_ollama_loaded` 180 秒枠 → `call_ollama_vlm` 30 秒枠）を実装。
4. **ルール・ドキュメント**:
   - `.agents/rules/error-prevention.md` (§2.2, §2.3)、`docs/OPERATION_MANUAL.md` (§5, §7)、`docs/DEVELOPMENT_LOG.md`（第30期）を更新。

---

## 4. 検証結果（2026-11-23 実機実施）

* **構文チェック (`py_compile`)**: `server.py`, `verify_step1_vlm.py`, `qwen2_audio_hybrid.py` すべて PASS。
* **VLM 単体 CLI (`verify_step1_vlm.py`)**:
  - `koji-bose.jpg` (`think=True`): `1boy, very short hair, buzz cut, ...` / 超短髪ネガ付与、11.28s（コールドロード込み）PASS。
  - `koji-bose.jpg` (`--no-think`): 7.79s（コールドロード込み、eval 0.54s）PASS。
  - `michie.jpg` (`think=True`): `1girl, has_bangs=True`, ネガなし、11.63s PASS。
  - `test_noface.jpg` (`think=True`): `face_detected=False`, 9.58s PASS。
* **障害再現＆統合テスト（実機 Ollama + 実機 Qwen2-Audio、`comfy_free_and_wait_vram` のみモック）**:
  - **起動直後 `POST /api/models/standby`**: HTTP 200（51.81s）、`ollama_vram_used_mb=3100.0MB`（補正確認）、`qwen_vram=5962.7MB` PASS。
  - **並列競合テスト（`standby` 開始 5 秒後に `POST /api/analyze_face` 送信）**: `standby` HTTP 200（53.36s）、`analyze_face` HTTP 200（待機込み 53.24s、実 VLM 推論 **4.862s**, `think=True`）PASS。タイムアウト再発ゼロ。
  - **ハイブリッド音声分析 (`POST /api/analyze_audio`, `01_shout.wav`)**: HTTP 200（3.69s）、フォールバックなし、`joy 100.0pt`、完了後に `/api/ps` 空（自動解放）確認 PASS。
  - **VRAM 上限・解放確認**: ピーク VRAM **`10,921.9 MB <= 14,848 MB (14.5 GB)`**、アンロード後 `/api/ps` 空・GPU 0 MB へ復帰 PASS。
