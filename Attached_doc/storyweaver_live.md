# StoryWeaver Live 完全ローカル構築マニュアル（実稼働・アニメ調特化版）

〜ThinkPad X1 Extreme (RTX 3080 Laptop 16GB / RAM 32GB) 最適化構成〜

本マニュアルは、展示ブース等の現場で「ComfyUI（アニメ調SDXL + InstantID）」と「音声認識（SenseVoice）」「小型LLM」を単一PC上で安定して同時稼働させるための完全ローカル構築手順書です。
画風を**アニメ調（Animagine XL v3.1）に一本化**し、カメラで撮影した現実の人間の顔特徴を破綻なく2Dアニメキャラクターへ転生させるための特化設定を記載しています。

---

## 1. アニメ調特化のシステム設計方針

### 課題：実写の顔写真 $\rightarrow$ アニメイラストへの転移
一般的なInstantIDは実写系チェックポイント向けに学習されているため、アニメ調モデルへ適用する際は以下の調整が必須となります。
* **InstantID Weight (IP-Adapter)**: `0.55 〜 0.70` に設定（強すぎると顔だけ実写風のシワや陰影が残り浮いてしまう）。
* **ControlNet (Keypoints) Weight**: `0.40 〜 0.60` に設定（骨格やパーツ配置のみをガイド）。
* **モデル選定**: アニメ系最高峰の表現力とDanbooruタグ親和性を持つ **Animagine XL v3.1**（FP8量子化版）を採用。
* **高速化**: **SDXL Lightning (4-step LoRA)** を併用し、アニメ画のクオリティを維持しながら約3〜4秒での出力を実現。

---

## 2. 厳選モデル・ファイル一覧（アニメ調特化）

### ① 言語モデル（Ollama）
ターミナルで実行して事前にダウンロードします。
```bash
# 本命：超低遅延エッジモデル
ollama pull gemma4:e2b

# 日本語表現力・Danbooru系タグ親和性のリファレンス
ollama pull qwen2.5:3b

# 非常用（最軽量フェイルセーフ）
ollama pull qwen2.5:1.5b
```

### ② 音声認識・感情抽出モデル
* **モデル名**: `FunAudioLLM/SenseVoiceSmall`
* **配置**: Pythonの `funasr` ライブラリ経由で自動取得（約400MB、RAM/CPUまたは余剰GPUで実行）。

### ③ ComfyUI 画像生成モデル（アニメ調 SDXL + InstantID）

| カテゴリ | ファイル名 | 格納先ディレクトリ | 用途 |
| :--- | :--- | :--- | :--- |
| **CheckPoint** | `animagineXL_v31.safetensors` (FP8版) | `ComfyUI/models/checkpoints/` | アニメ調SDXLベースモデル |
| **LoRA** | `sdxl_lightning_4step_lora.safetensors` | `ComfyUI/models/loras/` | 4ステップ超高速生成用LoRA |
| **InstantID** | `ip-adapter_instant_id_sdxl.bin` | `ComfyUI/models/instantid/` | 顔特徴抽出アダプター |
| **ControlNet** | `diffusion_pytorch_model.safetensors` | `ComfyUI/models/controlnet/` | InstantID用ControlNet |
| **InsightFace** | `antelopev2/` 一式 (.onnx 5ファイル) | `ComfyUI/models/insightface/models/antelopev2/` | 顔ランドマーク検出 |

---

## 3. RTX 3080 Laptop (16GB) メモリ配分計画

```
[ RTX 3080 Laptop 16GB VRAM 配分計画 ]
┌─────────────────────────────────────────────────────────────┐
│ 1. OS描画・ディスプレイドライバ基本予約     : 1.5 GB         │
│ 2. ComfyUI: Animagine XL v3.1 (FP8)         : 5.5 GB         │
│ 3. ComfyUI: InstantID + InsightFace         : 3.5 GB         │
│ 4. ComfyUI: VAE / ワークスペース一時バッファ : 1.5 GB         │
├─────────────────────────────────────────────────────────────┤
│ ComfyUI系 占有小計                          : 12.0 GB       │
├─────────────────────────────────────────────────────────────┤
│ 5. Ollama: Gemma 4 E2B (または Qwen 2.5-3B) : 2.2 〜 2.9 GB │
│ 6. 安全マージン (熱・動的バッファ)          : 1.1 〜 1.8 GB │
└─────────────────────────────────────────────────────────────┘
 合計: 16.0 GB 以内（展示本番中のOOMゼロ設計）
```

---

## 4. 全体システムアーキテクチャ

```
[展示ブース体験者]
   │
   ├─① Webカメラ ───> [フロントエンドUI (demo.txt)]
   │                     │ (撮影した顔写真 Base64)
   └─② マイク ───────>  │ (発話音声 WAV / セリフ文字列)
                         │
                         ▼ HTTP POST (Multipart)
                 [FastAPI Orchestrator] (server.py:8000)
                   │
                   ├── Step A: 音声認識 & 感情解析
                   │    └── SenseVoice-Small (約0.1秒)
                   │         => 「絶対に諦めない！光よ、闇を切り裂け！」[EMOTION: EXCITED]
                   │
                   ├── Step B: アニメ調プロンプト合成
                   │    └── Ollama API (gemma4:e2b または qwen2.5:3b)
                   │         => 日本語朗読文 + アニメ特化英語プロンプト (Danbooruタグ対応)
                   │
                   └── Step C: アニメ生成パイプライン実行
                        └── ComfyUI API (localhost:8188)
                             Input 1: 体験者の顔写真
                             Input 2: アニメ特化統合プロンプト + Animagine専用品質タグ
                             Engine : Animagine XL FP8 + SDXL Lightning 4-step + InstantID
                             => 3〜4秒で 16:9 アニメイラストを出力
                         │
                         ▼ JSON Response (画像Base64 + 台詞 + キャプション)
[フロントエンドUI (demo.txt)]
   │
   ├─ 画面表示（本人が2Dアニメキャラクター化されたワンシーン）
   ├─ Web Speech API による自動朗読再生
   ├─ 全画面シアターモード（プロジェクター展示）
   └─ 記念アートカード（PNG）出力
```

---

## 5. Step by Step 構築手順

### Step 1: 依存ライブラリのインストール
```bash
pip install funasr modelscope soundfile fastapi uvicorn requests python-multipart
```

### Step 2: ComfyUI アニメ特化ワークフローの準備
1. ComfyUI Manager より以下をインストールします。
   * `ComfyUI-InstantID`
   * `comfyui_controlnet_aux`
2. ワークフロー構築時の主要パラメータ設定（アニメ調への最適化）：
   * **Apply InstantID**:
     * `ip_weight`: `0.60`（実写感を抑え、アニメの絵柄に溶け込ませる）
     * `cn_weight`: `0.45`
   * **KSampler**:
     * `steps`: `4` (SDXL Lightning LoRA: `weight 1.0`)
     * `cfg`: `1.5 〜 2.0`（Lightningの標準値。高くしすぎると破綻します）
     * `sampler_name`: `euler`
     * `scheduler`: `sgm_uniform`
   * **Negative Prompt**:
     ```text
     nsfw, lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, realistic, photograph, 3d render
     ```
3. メニュー「**Enable Dev mode Options**」をONにし、「**Save (API Format)**」で `storyweaver_anime_api.json` として保存します。

---

### Step 3: FastAPI オーケストレーター (`server.py`) の作成

アニメ調のプロンプト生成に最適化させたバックエンドスクリプトです。

```python
import json
import base64
import time
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from funasr import AutoModel

app = FastAPI(title="StoryWeaver Anime Local Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 音声認識モデル (SenseVoiceSmall: GPUまたはCPUで常駐)
sense_voice = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=True, device="cuda:0")

# 軽量LLMモデル指定 (gemma4:e2b または qwen2.5:3b)
OLLAMA_MODEL = "gemma4:e2b"

# Animagine XL 推奨の品質プレフィックス
ANIMAGINE_QUALITY = "masterpiece, best quality, very aesthetic, anime art style, 8k wallpaper"

@app.post("/api/process_story")
async def process_story(
    face_image: UploadFile = File(...),
    audio_file: UploadFile = File(None),
    transcript_text: str = Form(None),
    base_prompt: str = Form(...),
    scene_style: str = Form(...)
):
    # 1. 音声テキスト化
    transcript = transcript_text
    if audio_file:
        audio_bytes = await audio_file.read()
        with open("temp_input.wav", "wb") as f:
            f.write(audio_bytes)
        res = sense_voice.generate(input="temp_input.wav", language="ja", use_itn=True)
        transcript = res[0]['text']

    # 2. Ollamaによる感情解析 ＆ アニメ演出プロンプト生成
    prompt_instruction = f"""
You are an animation director for a high-end Japanese anime movie.
The anime hero shouted this line: "{transcript}".
Scene Art Style: {scene_style}
Scene Base: {base_prompt}

Generate a JSON object with:
1. "emotion": Emotional state in Japanese (e.g., 覚醒した勇気, 哀愁と決意).
2. "animeAura": Anime visual effects in English tags (e.g., "swirling glowing blue mana, fierce golden sparks in eyes, fluttering cape, dynamic wind").
3. "narrativeCaption": One poetic Japanese narration sentence for voice reading.
4. "characterAction": English description of the character's dynamic anime pose and facial expression.
"""

    ollama_res = requests.post("http://localhost:11434/api/generate", json={
        "model": OLLAMA_MODEL,
        "prompt": prompt_instruction,
        "format": "json",
        "stream": False
    }).json()

    analysis = json.loads(ollama_res["response"])

    # 3. ComfyUI への入力受け渡し
    face_bytes = await face_image.read()
    with open("ComfyUI/input/user_face.jpg", "wb") as f:
        f.write(face_bytes)

    # アニメ調に特化した統合プロンプトの構築
    positive_prompt = (
        f"{ANIMAGINE_QUALITY}, 1boy/1girl, solo focus, "
        f"{scene_style}, {base_prompt}, "
        f"{analysis['characterAction']}, {analysis['animeAura']}, "
        f"cinematic angle, highly detailed anime illustration"
    )

    with open("storyweaver_anime_api.json", "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # ノード番号は作成したワークフローに合わせて確認・修正してください
    workflow["6"]["inputs"]["text"] = positive_prompt
    workflow["12"]["inputs"]["image"] = "user_face.jpg"

    # ジョブ投入
    queue_res = requests.post("http://localhost:8188/prompt", json={"prompt": workflow}).json()
    prompt_id = queue_res["prompt_id"]

    # 生成結果のポーリング取得
    image_base64 = poll_comfyui_result(prompt_id)

    return {
        "transcript": transcript,
        "analysis": analysis,
        "imageBase64": image_base64
    }

def poll_comfyui_result(prompt_id: str):
    while True:
        hist = requests.get(f"http://localhost:8188/history/{prompt_id}").json()
        if prompt_id in hist:
            outputs = hist[prompt_id]["outputs"]
            for node_id in outputs:
                if "images" in outputs[node_id]:
                    img_info = outputs[node_id]["images"][0]
                    img_data = requests.get(
                        f"http://localhost:8188/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                    ).content
                    return base64.b64encode(img_data).decode("utf-8")
        time.sleep(0.25)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 6. フロントエンド (`demo.txt`) との接続設定

`demo.txt` 内部の `generateStoryScene()` 関数を、クラウド（Gemini API）呼び出しからローカルサーバーへのリクエストに切り替えます。

```javascript
// demo.txt 内の generateStoryScene を差し替え
async function generateStoryScene() {
  if (state.isGenerating) return;

  const currentPreset = scenePresets.find(p => p.id === state.selectedPresetId);
  const formData = new FormData();
  
  // 顔写真（Blob）
  const faceBlob = await (await fetch(`data:${state.capturedFaceMimeType};base64,${state.capturedFaceBase64}`)).blob();
  formData.append("face_image", faceBlob, "face.jpg");
  
  // 台詞テキスト
  formData.append("transcript_text", document.getElementById('voice-transcript-input').value.trim());
  formData.append("base_prompt", currentPreset.basePrompt);
  formData.append("scene_style", currentPreset.style);

  state.isGenerating = true;
  document.getElementById('scene-loading-state').classList.remove('hidden');

  try {
    const res = await fetch("http://localhost:8000/api/process_story", {
      method: "POST",
      body: formData
    });
    const data = await res.json();

    // 画面への画像反映
    const imgUrl = `data:image/png;base64,${data.imageBase64}`;
    state.lastGeneratedImageBase64 = data.imageBase64;
    document.getElementById('generated-scene-image').src = imgUrl;
    document.getElementById('generated-scene-image').classList.remove('hidden');

    // キャプション・朗読の設定
    document.getElementById('scene-quote-text').textContent = `「${data.transcript}」`;
    document.getElementById('scene-caption-text').textContent = data.analysis.narrativeCaption;
    document.getElementById('scene-subtitle-overlay').classList.remove('hidden');

    // 朗読を自動開始
    readAloudScene();

    showToast("アニメ調のワンシーンが具現化されました！", "success");
  } catch (err) {
    console.error("Local Pipeline Error:", err);
    showToast("ローカル生成パイプラインとの通信に失敗しました。", "error");
  } finally {
    document.getElementById('scene-loading-state').classList.add('hidden');
    state.isGenerating = false;
  }
}
```

---

## 7. 展示本番でのチューニングのコツ

1. **実写顔の浮きを防ぐ**:
   体験者の写真がイラスト内でリアルすぎると感じた場合は、ComfyUIワークフロー内の `Apply InstantID` ノードで `ip_weight` を `0.60` $\rightarrow$ `0.50` 付近まで下げてください。輪郭や髪型、目元の大まかな特徴を保ちつつ、綺麗な2Dアニメ顔に仕上がります。
2. **高速化（4ステップ維持）**:
   `Animagine XL v3.1` に `sdxl_lightning_4step_lora` を適用することで、RTX 3080 Laptop環境で約3〜4秒で1280x720（16:9）の高精細アニメイラストが出力されます。