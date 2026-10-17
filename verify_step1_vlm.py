"""
StoryWeaver Live - Phase 1-A 検証スクリプト
verify_step1_vlm.py

目的:
  ローカルのマルチモーダル LLM (gemma4:e2b / Ollama) に顔写真を渡し、
  Pydantic JSON Schema 制約下で不変の外見特徴を抽出するとともに、
  表情排除、前髪バイアス判定、VRAM即時解放(keep_alive=0) を検証・計測する。

使用例:
  python verify_step1_vlm.py --faces-dir test_assets/faces --model gemma4:e2b
  python verify_step1_vlm.py --image test_assets/faces/koji-bose.jpg
"""

import argparse
import base64
import csv
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Literal, Optional

# Windows コンソールでの文字化け防止
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------------------
# Pydantic JSON Schema 定義
# ---------------------------------------------------------------------------
class FaceVlmExtraction(BaseModel):
    face_detected: bool = Field(
        ...,
        description=(
            "Set to true if a human face is clearly visible and recognizable. "
            "Set to false if no face is present, or the face is covered/obscured by hands, mask, or extreme blur."
        ),
    )
    gender_tag: Literal["1boy", "1girl"] = Field(
        ...,
        description="Gender tag for Danbooru/Animagine: '1boy' or '1girl'. If face_detected is false, default to '1boy'.",
    )
    hair_length: Literal[
        "buzz cut", "very short hair", "short hair", "medium hair", "long hair", "bald"
    ] = Field(
        ...,
        description="Overall hair length. If face_detected is false, default to 'short hair'.",
    )
    hair_style_details: str = Field(
        ...,
        description=(
            "Comma-separated Danbooru-style English tags for hair color, texture, cut, parting, or hairline "
            "(e.g., 'black hair, straight hair, receding hairline'). "
            "STRICTLY FORBIDDEN: Any facial expression words (e.g., smile, laughing, angry, open mouth). "
            "If face_detected is false, default to ''."
        ),
    )
    has_bangs: bool = Field(
        ...,
        description="True if bangs/fringe cover the forehead. False if forehead is exposed or hair is swept back/buzz cut. If face_detected is false, default to false.",
    )
    exposed_forehead: bool = Field(
        ...,
        description="True if forehead is clearly exposed/visible. False if covered by bangs. If face_detected is false, default to false.",
    )
    glasses: Literal["none", "glasses", "sunglasses"] = Field(
        ...,
        description="Eyewear type. Default to 'none' if none or if face_detected is false.",
    )
    facial_hair: Literal["none", "stubble", "beard", "mustache"] = Field(
        ...,
        description="Facial hair type. Default to 'none' if none or if face_detected is false.",
    )


# ---------------------------------------------------------------------------
# システムプロンプト定義
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert anime character designer and physical trait extractor for Animagine XL.
Analyze the user's portrait photograph and extract ONLY their static physical appearance.

CRITICAL INSTRUCTIONS:
1. FACE DETECTION & DEFAULTS:
   - If a clear human face is visible, set `face_detected` to true.
   - If NO face is present, or the face is covered by hands/objects or unidentifiable, set `face_detected` to false.
     When `face_detected` is false, populate all other fields with exact defaults:
     gender_tag="1boy", hair_length="short hair", hair_style_details="", has_bangs=false, exposed_forehead=false, glasses="none", facial_hair="none".

2. STRICTLY NO FACIAL EXPRESSIONS OR EMOTIONS:
   - Facial expressions will be injected separately based on voice emotion.
   - DO NOT EVER include expression tags in `hair_style_details` or any other field.
   - FORBIDDEN WORDS: 'smile', 'smiling', 'laughing', 'grin', 'angry', 'frown', 'open mouth', 'closed mouth', 'neutral', 'serious', 'happy', 'sad', 'teeth', 'looking at viewer'.
   - `hair_style_details` must ONLY describe hair color, cut, hairline, and hair texture.

3. FOREHEAD & BANGS:
   - If bangs cover the forehead, set `has_bangs` = true, `exposed_forehead` = false.
   - If forehead is exposed, receding, buzz cut, swept back, or bald, set `has_bangs` = false, `exposed_forehead` = true.

Output MUST strictly conform to the provided JSON schema."""


# ---------------------------------------------------------------------------
# VRAM 取得ユーティリティ
# ---------------------------------------------------------------------------
def get_gpu_vram_mb() -> float:
    """nvidia-smi または pynvml を用いて GPU VRAM 使用量(MB)を取得する"""
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return round(info.used / (1024 * 1024), 1)
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return float(res.stdout.strip().split("\n")[0].strip())
    except Exception:
        return -1.0


# ---------------------------------------------------------------------------
# 画像エンコード
# ---------------------------------------------------------------------------
def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ---------------------------------------------------------------------------
# Python ルールベース変換
# ---------------------------------------------------------------------------
FORBIDDEN_EXPRESSION_KEYWORDS = [
    "smile", "smiling", "laugh", "laughing", "grin", "grinning",
    "angry", "frown", "frowning", "open mouth", "closed mouth",
    "neutral", "serious", "looking at viewer", "happy", "sad", "teeth", "wink"
]


def rule_based_transform(extracted: FaceVlmExtraction) -> tuple[str, str, list[str]]:
    """
    抽出された特徴から physical_traits と negative_hair_bias を生成する。
    戻り値: (physical_traits, negative_hair_bias, detected_expression_warnings)
    """
    if not extracted.face_detected:
        return "", "", []

    traits: list[str] = [extracted.gender_tag]

    if extracted.hair_length and extracted.hair_length != "bald":
        traits.append(extracted.hair_length)
    elif extracted.hair_length == "bald":
        traits.append("bald")

    # hair_style_details のパース & 表情タグの検知・サニタイズ
    expression_warnings: list[str] = []
    if extracted.hair_style_details:
        raw_items = [t.strip() for t in extracted.hair_style_details.split(",") if t.strip()]
        sanitized_items = []
        for item in raw_items:
            lower = item.lower()
            found_expr = [kw for kw in FORBIDDEN_EXPRESSION_KEYWORDS if kw in lower]
            if found_expr:
                expression_warnings.append(f"Excluded expression token '{item}' ({', '.join(found_expr)})")
            else:
                sanitized_items.append(item)
        if sanitized_items:
            traits.extend(sanitized_items)

    # 眼鏡
    if extracted.glasses in ("glasses", "sunglasses"):
        traits.append(extracted.glasses)

    # 髭
    if extracted.facial_hair in ("stubble", "beard", "mustache"):
        traits.append(extracted.facial_hair)

    # 額露出・前髪判定
    # ルール: has_bangs == False または exposed_forehead == True の場合、
    # physical_traits に exposed forehead を確実に含め、
    # negative_hair_bias に "(bangs:1.3), (fringe:1.3), hair over forehead" をセット
    if not extracted.has_bangs or extracted.exposed_forehead:
        if "exposed forehead" not in [t.lower() for t in traits]:
            traits.append("exposed forehead")
        negative_hair_bias = "(bangs:1.3), (fringe:1.3), hair over forehead"
    else:
        negative_hair_bias = ""

    # 重複タグ排除（大文字小文字を無視しつつ順序を維持）
    seen = set()
    deduped: list[str] = []
    for t in traits:
        clean = t.strip()
        low = clean.lower()
        if low and low not in seen:
            seen.add(low)
            deduped.append(clean)

    physical_traits = ", ".join(deduped)
    return physical_traits, negative_hair_bias, expression_warnings


# ---------------------------------------------------------------------------
# Ollama 呼び出し
# ---------------------------------------------------------------------------
def call_ollama_vlm(
    image_path: Path,
    model: str,
    ollama_url: str = "http://localhost:11434/api/generate",
    timeout: int = 30,
) -> dict:
    print(f"  [1/4] 画像エンコード中: {image_path.name}", flush=True)
    b64_img = encode_image_to_base64(image_path)
    schema = FaceVlmExtraction.model_json_schema()

    payload = {
        "model": model,
        "prompt": SYSTEM_PROMPT,
        "images": [b64_img],
        "format": schema,
        "stream": False,
        "keep_alive": 0,  # 推論直後に VRAM からアンロード
        "options": {
            "temperature": 0.1,  # 決定論的抽出
        },
    }

    print(f"  [2/4] Ollama API にリクエスト送信中 (model={model}, timeout={timeout}s)...", flush=True)
    t0 = time.perf_counter()
    resp = requests.post(ollama_url, json=payload, timeout=timeout)
    t1 = time.perf_counter()
    wall_time_ms = round((t1 - t0) * 1000, 1)
    print(f"  [3/4] Ollama 応答受信 (所要時間: {wall_time_ms} ms)", flush=True)

    # アンロード後の VRAM 計測
    # keep_alive: 0 のためモデルアンロードが非同期で行われる場合を考慮し微小待機
    time.sleep(0.5)
    vram_used_mb = get_gpu_vram_mb()
    print(f"  [4/4] 解放後 VRAM 取得: {vram_used_mb} MB", flush=True)

    if resp.status_code != 200:
        raise RuntimeError(f"Ollama API returned HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    load_duration_ms = round(data.get("load_duration", 0) / 1e6, 1)
    eval_duration_ms = round(data.get("eval_duration", 0) / 1e6, 1)
    prompt_eval_duration_ms = round(data.get("prompt_eval_duration", 0) / 1e6, 1)
    raw_response_text = data.get("response", "{}")

    # Pydantic 検証
    try:
        parsed_dict = json.loads(raw_response_text)
        validated = FaceVlmExtraction.model_validate(parsed_dict)
        validation_error = None
    except (json.JSONDecodeError, ValidationError) as e:
        validated = None
        validation_error = str(e)
        parsed_dict = {}

    return {
        "wall_time_ms": wall_time_ms,
        "load_duration_ms": load_duration_ms,
        "eval_duration_ms": eval_duration_ms,
        "prompt_eval_duration_ms": prompt_eval_duration_ms,
        "vram_used_mb": vram_used_mb,
        "raw_response": raw_response_text,
        "parsed": parsed_dict,
        "validated": validated,
        "validation_error": validation_error,
    }


# ---------------------------------------------------------------------------
# CSV ログ記録
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "timestamp",
    "filename",
    "face_detected",
    "gender_tag",
    "hair_length",
    "hair_style_details",
    "has_bangs",
    "exposed_forehead",
    "glasses",
    "facial_hair",
    "physical_traits",
    "negative_hair_bias",
    "load_duration_ms",
    "eval_duration_ms",
    "wall_time_ms",
    "vram_used_mb",
    "status",
]


def log_to_csv(csv_path: Path, row: dict) -> None:
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="StoryWeaver Live - Phase 1-A VLM 外見抽出検証")
    parser.add_argument("--faces-dir", type=str, default="test_assets/faces", help="テスト画像ディレクトリ")
    parser.add_argument("--image", type=str, default=None, help="単一テスト画像ファイルのパス")
    parser.add_argument("--model", type=str, default="gemma4:e2b", help="Ollama モデル名")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434/api/generate", help="Ollama API URL")
    parser.add_argument("--timeout", type=int, default=30, help="タイムアウト秒数")
    parser.add_argument("--csv", type=str, default="vlm_benchmark.csv", help="ベンチマーク出力先CSV")

    args = parser.parse_args()

    # 画像ファイルの列挙
    image_paths: list[Path] = []
    if args.image:
        p = Path(args.image)
        if not p.is_file():
            print(f"[ERROR] 指定された画像が存在しません: {p}")
            sys.exit(1)
        image_paths.append(p)
    else:
        faces_dir = Path(args.faces_dir)
        if not faces_dir.is_dir():
            print(f"[ERROR] 指定ディレクトリが存在しません: {faces_dir}")
            sys.exit(1)
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.JPG", "*.JPEG", "*.PNG"):
            image_paths.extend(faces_dir.glob(ext))
        # 重複除外＆ソート
        image_paths = sorted(list(set(image_paths)))

    if not image_paths:
        print(f"[WARNING] 処理対象の画像が見つかりませんでした: {args.faces_dir}")
        print("画像を配置するか、--image で単一画像を指定してください。")
        sys.exit(0)

    print("=" * 80, flush=True)
    print(f" StoryWeaver Live - Phase 1-A: VLM 外見抽出検証", flush=True)
    print(f" Model       : {args.model}", flush=True)
    print(f" Ollama URL  : {args.ollama_url}", flush=True)
    print(f" Images Count: {len(image_paths)}", flush=True)
    print(f" CSV Output  : {args.csv}", flush=True)
    print("=" * 80, flush=True)

    csv_path = Path(args.csv)
    results = []

    for idx, img_path in enumerate(image_paths, 1):
        print(f"\n[{idx}/{len(image_paths)}] 処理中: {img_path.name}", flush=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            call_res = call_ollama_vlm(
                img_path,
                model=args.model,
                ollama_url=args.ollama_url,
                timeout=args.timeout,
            )
        except Exception as e:
            print(f"  [FAIL] 呼び出しエラー: {e}")
            row = {col: "" for col in CSV_COLUMNS}
            row.update({
                "timestamp": ts,
                "filename": img_path.name,
                "status": f"ERROR: {e}",
            })
            log_to_csv(csv_path, row)
            continue

        validated: Optional[FaceVlmExtraction] = call_res["validated"]
        if validated is None:
            print(f"  [FAIL] JSON Schema 検証失敗: {call_res['validation_error']}")
            row = {col: "" for col in CSV_COLUMNS}
            row.update({
                "timestamp": ts,
                "filename": img_path.name,
                "load_duration_ms": call_res["load_duration_ms"],
                "eval_duration_ms": call_res["eval_duration_ms"],
                "wall_time_ms": call_res["wall_time_ms"],
                "vram_used_mb": call_res["vram_used_mb"],
                "status": f"SCHEMA_ERROR: {call_res['validation_error']}",
            })
            log_to_csv(csv_path, row)
            continue

        # ルールベース変換
        phys_traits, neg_bias, expr_warnings = rule_based_transform(validated)

        # Gate チェック判定
        gate_1_json = "PASS"  # スキーマ通過
        gate_2_short = "N/A"
        gate_3_bangs = "N/A"
        gate_4_no_expr = "PASS" if not expr_warnings else "WARN"
        gate_6_undetected = "PASS" if not validated.face_detected else "DETECTED"

        if validated.face_detected:
            if validated.hair_length in ("buzz cut", "very short hair") or validated.exposed_forehead:
                gate_2_short = "PASS" if (neg_bias != "" and "exposed forehead" in phys_traits) else "FAIL"
            if validated.has_bangs:
                gate_3_bangs = "PASS" if neg_bias == "" else "FAIL"

        print(f"  [抽出結果]")
        print(f"    - face_detected     : {validated.face_detected}")
        print(f"    - gender_tag        : {validated.gender_tag}")
        print(f"    - hair_length       : {validated.hair_length}")
        print(f"    - hair_style_details: {validated.hair_style_details}")
        print(f"    - has_bangs         : {validated.has_bangs}")
        print(f"    - exposed_forehead  : {validated.exposed_forehead}")
        print(f"    - glasses           : {validated.glasses}")
        print(f"    - facial_hair       : {validated.facial_hair}")
        print(f"  [ルールベース変換]")
        print(f"    - physical_traits   : {phys_traits if phys_traits else '(なし)'}")
        print(f"    - negative_hair_bias: {neg_bias if neg_bias else '(なし)'}")
        if expr_warnings:
            for w in expr_warnings:
                print(f"    - [WARN 表情排除]   : {w}")
        print(f"  [性能計測]")
        print(f"    - Wall Time         : {call_res['wall_time_ms']} ms")
        print(f"    - Load Duration     : {call_res['load_duration_ms']} ms")
        print(f"    - Eval Duration     : {call_res['eval_duration_ms']} ms")
        print(f"    - 解放後 VRAM 使用量 : {call_res['vram_used_mb']} MB")

        # CSV 保存
        row = {
            "timestamp": ts,
            "filename": img_path.name,
            "face_detected": validated.face_detected,
            "gender_tag": validated.gender_tag,
            "hair_length": validated.hair_length,
            "hair_style_details": validated.hair_style_details,
            "has_bangs": validated.has_bangs,
            "exposed_forehead": validated.exposed_forehead,
            "glasses": validated.glasses,
            "facial_hair": validated.facial_hair,
            "physical_traits": phys_traits,
            "negative_hair_bias": neg_bias,
            "load_duration_ms": call_res["load_duration_ms"],
            "eval_duration_ms": call_res["eval_duration_ms"],
            "wall_time_ms": call_res["wall_time_ms"],
            "vram_used_mb": call_res["vram_used_mb"],
            "status": "OK",
        }
        log_to_csv(csv_path, row)
        results.append((img_path.name, validated, phys_traits, neg_bias, call_res))

    print("\n" + "=" * 80)
    print(" 全検証結果 サマリー")
    print("=" * 80)
    print(f"{'Filename':<20} | {'Detected':<8} | {'Gender':<6} | {'Hair Length':<15} | {'Forehead':<8} | {'Wall(s)':<7} | {'VRAM(MB)':<8}")
    print("-" * 80)
    for name, val, pt, nb, cr in results:
        wall_s = round(cr["wall_time_ms"] / 1000, 2)
        print(f"{name:<20} | {str(val.face_detected):<8} | {val.gender_tag:<6} | {val.hair_length:<15} | {str(val.exposed_forehead):<8} | {wall_s:<7} | {cr['vram_used_mb']:<8}")
    print("=" * 80)
    print(f"ベンチマーク結果を {csv_path.resolve()} に保存しました。")


if __name__ == "__main__":
    main()
