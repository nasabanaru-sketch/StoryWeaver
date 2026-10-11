---
trigger: manual
---

# エラー再発防止・コーディング規約 (error-prevention.md)

本ドキュメントは、展示本番環境において安定稼働を維持し、過去に発生した障害や潜在的な不具合の再発を防止するための実装ルールです。コード作成・変更時に自動適用されます。

---

## 1. VRAM 管理・OOM（Out of Memory）防止規約

### 1.1 VRAM 割当の上限監視
- RTX 3080 Laptop (16GB) 環境下において、プロセス全体の VRAM 占有が **14.5 GB を超過しない** 設計を維持すること。
- ComfyUI の大規模モデル（Animagine XL v3.1）は必ず **FP8版（量子化版）** を使用すること。FP16版の無断投入を禁止する。
- 画質・本人同一性のベースライン確立期間中は、サンプリングステップ数（20〜30 steps 等）や高精細FaceDetailerを十分に活用して最高画質を追求すること。生成時間は一旦最大7分（420秒）まで許容し、短時間制約による画質劣化を防止する。

### 1.2 モデルの同時推論排他制御
- FastAPI 内で重い処理が同時にリクエストされた場合、同時実行数をセマフォ等で制御し、VRAM の一時的なスパイクを防止すること。
```python
import asyncio

# 同時生成リクエストを1件に制限（キューイング）
generation_lock = asyncio.Lock()
```

---

## 2. 通信タイムアウトとポーリング制御

### 2.1 無限ループの禁止
- ComfyUI へのキュー投入後のポーリング（`poll_comfyui_result`）には、必ず **最大タイムアウト（画質検証期間中は最大 450〜500秒）** と **リトライ回数上限** を設けること。
- `while True:` による無期限ポーリングコードは禁止。
```python
# 悪い例 (BAD)
while True:
    hist = requests.get(...)

# 良い例 (GOOD: 最大7分許容に合わせた設定)
MAX_WAIT_SECONDS = 450  # 最大7分半のポーリング待機を許容
start_time = time.time()
while time.time() - start_time < MAX_WAIT_SECONDS:
    # ポーリング処理
    time.sleep(0.5)
else:
    raise TimeoutError("ComfyUI generation timed out.")
```

### 2.2 HTTP リクエストのタイムアウト設定
- `requests` や `httpx` を用いた全ての外部通信（Ollama, ComfyUI）において、`timeout=` 引数を必須とする。
```python
requests.post("http://localhost:11434/api/generate", json=payload, timeout=10.0)
```

---

## 3. フォールバック・堅牢性設計

### 3.1 Ollama (LLM) レスポンスの堅牢化
- LLM が指定した JSON 形式以外の文字列や壊れた JSON を返却した場合に備え、フォールバック値を定義すること。
- バックエンドが 500 エラーで落ちるのを防ぎ、デフォルトの演出プロンプトで画像生成を継続させること。
```python
try:
    analysis = json.loads(ollama_res["response"])
except Exception as e:
    logger.warning(f"Ollama JSON parse failed, using fallback: {e}")
    analysis = {
        "emotion": "決意",
        "animeAura": "soft radiant light, gentle breeze",
        "narrativeCaption": transcript or "新たな物語が幕を開ける。",
        "characterAction": "confident standing pose, looking forward"
    }
```

### 3.2 SenseVoice (音声認識) のフェイルセーフ
- 音声入力が無音またはノイズのみで認識失敗（空文字）となった場合、デフォルトの汎用セリフ（または画面入力テキスト）へフォールバックすること。

---

## 4. ファイル I/O と一時ファイル排他制御

### 4.1 固定ファイル名競合の防止
- `temp_input.wav` や `user_face.jpg` などの固定ファイル名を使用する場合、並列リクエストや高速な連続実行時にファイル破損（レースコンディション）が起きないよう UUID やタイムスタンプを付与するか、セマフォで直列化すること。
- 処理終了後は一時ファイルを確実にクリーンアップ、またはテンポラリディレクトリを活用すること。

---

## 5. フロントエンド・バックエンド連携規約

### 5.1 エラーの可視化
- サーバー側エラー発生時は、フロントエンドで無限ローディングとならないよう、`try...catch...finally` で必ず `isGenerating` フラグを解除し、ユーザー向けトースト通知を表示すること。
- HTTP ステータスコードは実態に合わせて返却すること（503: サービス未起動、504: タイムアウト、400: 入力不備）。
