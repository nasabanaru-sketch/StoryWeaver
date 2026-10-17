"""
StoryWeaver Live - Step 1 検証スクリプト
目的:
  WD14 Taggerを使わず、ローカルのマルチモーダルLLM (Ollama) に実写の顔写真を渡すだけで、
  1. 本人の不変の外見特徴 (髪型・生え際・眼鏡・性別)
  2. Animagine XLの「前髪バイアス」を打ち消す動的ネガティブプロンプト
  が正確にJSONで自動抽出され、かつ「写真の表情」が混入しないことを検証する。

使い方:
  python verify_step1_vlm.py --image path/to/face_photo.jpg --model gemma4:e2b
"""

import argparse
import base64
import json
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

OLLAMA_API_URL = "http://localhost:11434/api/generate"

# ---------------------------------------------------------------------------
# 外見抽出専用の厳格なシステムプロンプト
# ---------------------------------------------------------------------------
VLM_SYSTEM_PROMPT = """You are an expert anime character designer and visual feature extractor for Stable Diffusion XL (Animagine XL).
Analyze the attached real-person portrait photo and extract ONLY their static physical traits to recreate their likeness in an anime illustration.

CRITICAL RULES:
1. EXTRACT ONLY STATIC PHYSICAL TRAITS: gender tag (1boy / 1girl), hair length, hair style (e.g., buzz cut, very short hair, bob cut, long hair, ponytail), hair color, hairline/forehead visibility (e.g., exposed forehead, bangs, parted bangs), eyewear (e.g., glasses, rimless glasses, black-framed glasses, or no glasses), and facial hair (e.g., beard, mustache, clean-shaven).
2. STRICTLY EXCLUDE EXPRESSIONS & POSES: Do NOT include any facial expressions (NEVER output 'smile', 'smiling', 'serious', 'looking at viewer', 'open mouth') or background/clothing details. Facial expressions will be injected separately from voice emotion later.
3. COUNTERACT ANIMAGINE HAIR BIAS (Dynamic Negative Prompt):
   - If the person has a buzz cut, receding hairline, swept-back hair, or an exposed forehead with NO bangs covering the forehead, you MUST output strong anti-bangs tags in `negative_hair_bias`: "bangs, fringe, long bangs, hair over forehead, hair between eyes, medium hair, long hair".
   - If the person clearly has bangs covering their forehead and long hair, output anti-short-hair tags in `negative_hair_bias`: "bald, buzz cut, very short hair, exposed forehead".

Output ONLY a valid JSON object with the exact following schema:
{
  "gender_and_age": "e.g., 1boy, male focus, mature male",
  "hair_and_forehead": "e.g., buzz cut, very short black hair, exposed forehead, no bangs",
  "eyewear_and_accessories": "e.g., glasses, rimless eyewear (or empty string if none)",
  "physical_traits_combined": "Combined comma-separated Danbooru-style positive tags for all physical traits above",
  "negative_hair_bias": "Comma-separated negative tags to prevent wrong hairstyle generation",
  "has_exposed_forehead": true
}"""


def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_face_with_ollama(image_path: Path, model_name: str) -> dict:
    b64_image = encode_image_to_base64(image_path)

    payload = {
        "model": model_name,
        "prompt": VLM_SYSTEM_PROMPT,
        "images": [b64_image],
        "format": "json",
        "stream": False,
        "keep_alive": 0,  # 推論直後にVRAMからアンロード (展示本番と同等の排他制御)
        "options": {
            "temperature": 0.1,  # 再現性を高めるため低温度に設定
        }
    }

    req = urllib.request.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"\n[ERROR] Ollama APIへの接続に失敗しました: {e}")
        print("1. `ollama serve` が起動しているか確認してください。")
        print(f"2. 指定したモデル `{model_name}` が `ollama list` に存在するか確認してください。")
        sys.exit(1)

    elapsed = time.time() - start_time
    raw_response = result.get("response", "{}")

    try:
        parsed_json = json.loads(raw_response)
    except json.JSONDecodeError:
        parsed_json = {"raw_output": raw_response, "error": "JSON parse failed"}

    return {
        "elapsed_seconds": round(elapsed, 2),
        "model": model_name,
        "extracted": parsed_json,
    }


def run_gate_check(extracted: dict) -> None:
    """Gate 1 の自動検証チェックを表示する"""
    print("\n" + "=" * 60)
    print("🔍 Step 1 自動検証チェック (Gate 1 判定)")
    print("=" * 60)

    combined = extracted.get("physical_traits_combined", "").lower()
    neg_bias = extracted.get("negative_hair_bias", "").lower()

    # チェック1: 表情タグの混入がないか
    forbidden_expressions = ["smile", "smiling", "laugh", "angry", "sad", "open mouth", "grin"]
    leaked = [w for w in forbidden_expressions if w in combined]
    if not leaked:
        print("✅ [PASS] 表情の分離チェック: 写真の表情タグ（smile等）は混入していません。")
    else:
        print(f"❌ [FAIL] 表情の分離チェック: 禁止された表情タグが混入しています -> {leaked}")

    # チェック2: 髪型・額の記述が存在するか
    if extracted.get("hair_and_forehead"):
        print(f"✅ [PASS] 髪型・生え際抽出  : {extracted.get('hair_and_forehead')}")
    else:
        print("❌ [FAIL] 髪型・生え際抽出  : 髪型タグが空です。")

    # チェック3: 動的ネガティブプロンプトが生成されているか
    if neg_bias:
        print(f"✅ [PASS] 逆バイアスNegative: {neg_bias}")
    else:
        print("⚠️ [WARN] 逆バイアスNegative: ネガティブ補正タグが空です。")

    print("-" * 60)
    print("💡 ComfyUIへ自動注入される最終タグプレビュー:")
    print(f"  [Positive 外見パート]: {extracted.get('physical_traits_combined')}")
    print(f"  [Negative 追加パート]: {extracted.get('negative_hair_bias')}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Step 1: Ollama VLM 顔特徴抽出の単体検証スクリプト")
    parser.add_argument(
        "--image", "-i",
        type=str,
        required=True,
        help="検証する顔写真ファイルのパス (例: reWIN_20260204_20_46_41_Pro.jpg)"
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="gemma4:e2b",
        help="使用するOllamaのビジョン対応モデル名 (デフォルト: gemma4:e2b / 代替: gwen2.5vl:3b, gemma3:4b 等)"
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"[ERROR] 指定された画像ファイルが見つかりません: {image_path}")
        sys.exit(1)

    print(f"📷 入力画像: {image_path.name}")
    print(f"🤖 使用モデル: {args.model} (推論完了後に keep_alive:0 でVRAM即時解放)")
    print("⏳ 解析中...")

    res = analyze_face_with_ollama(image_path, args.model)

    print(f"\n⏱️ 処理時間: {res['elapsed_seconds']} 秒")
    print("\n📄 抽出されたJSONデータ:")
    print(json.dumps(res["extracted"], indent=2, ensure_ascii=False))

    run_gate_check(res["extracted"])


if __name__ == "__main__":
    main()