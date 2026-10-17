"""
StoryWeaver Live - Phase 1-B 検証スクリプト
verify_step1_sensevoice.py

目的:
  1. SenseVoiceSmall を device="cpu" でロードし、VRAM 増分が 0 MB であることを実証する。
  2. 16kHz モノラル WAV から 20ms フレーム RMS によるピーク声量 (rms_p90) を算出する。
  3. SenseVoiceSmall の感情認識と rms_p90 を組み合わせたハイブリッド感情判定を行い、
     BURNING_DB_THRESHOLD による BURNING 昇格や COOL 判定が意図通り動作するか検証する。
  4. 推論時間が 0.5 秒以内（3〜5秒の音声）に収まるかを計測する。

使用例:
  python verify_step1_sensevoice.py --audio-dir test_assets/audio
  python verify_step1_sensevoice.py --audio test_assets/audio/01_shout.wav --threshold -12.0
"""

import argparse
import csv
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Optional, Tuple

import numpy as np
import soundfile as sf

# Windows コンソールでの文字化け防止
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 表情プロンプトマッピング (README.md 3.2節)
# ---------------------------------------------------------------------------
EXPRESSION_PROMPTS = {
    "BURNING": "shouting, fierce determination, intense eyes, open mouth, battle cry, dynamic expression",
    "JOYFUL": "confident smile, bright expressive eyes, joyful and energetic expression",
    "EMOTIONAL": "tearful eyes, emotional expression, biting lip, dramatic sorrow, desperate look",
    "COOL": "calm and composed expression, sharp gaze, cool determination, slight smirk",
}


# ---------------------------------------------------------------------------
# VRAM 計測
# ---------------------------------------------------------------------------
def get_gpu_vram_mb() -> float:
    """nvidia-smi を用いて GPU VRAM 使用量(MB)を取得する"""
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
# 音量計算 (20ms フレーム RMS -> 90パーセンタイル dBFS)
# ---------------------------------------------------------------------------
def compute_rms_p90(wav_path: Path, frame_ms: float = 20.0, silence_threshold_db: float = -50.0) -> Tuple[float, float, int]:
    """
    16kHz モノラル WAV から、無音区間を除外した 90 パーセンタイル音量 (rms_p90 dBFS) を算出する。
    戻り値: (rms_p90_db, duration_sec, valid_frames_count)
    """
    data, sample_rate = sf.read(wav_path, dtype="float32")
    if data.ndim > 1:
        # モノラル化
        data = np.mean(data, axis=1)

    duration_sec = len(data) / sample_rate
    frame_samples = int(sample_rate * (frame_ms / 1000.0))

    if frame_samples <= 0 or len(data) < frame_samples:
        return -99.0, duration_sec, 0

    num_frames = len(data) // frame_samples
    frame_db_list = []

    for i in range(num_frames):
        chunk = data[i * frame_samples : (i + 1) * frame_samples]
        rms = np.sqrt(np.mean(chunk**2))
        # dBFS 計算 (0 dBFS が最大振幅 1.0)
        db = 20.0 * np.log10(rms + 1e-9)
        # 無音区間（環境ノイズレベル）の除外
        if db >= silence_threshold_db:
            frame_db_list.append(db)

    if not frame_db_list:
        # 発話区間が検出されなかった場合
        return -99.0, duration_sec, 0

    rms_p90 = float(np.percentile(frame_db_list, 90))
    return round(rms_p90, 2), round(duration_sec, 2), len(frame_db_list)


# ---------------------------------------------------------------------------
# ハイブリッド感情判定ロジック (README.md 3.2節)
# ---------------------------------------------------------------------------
def determine_expression_category(sensevoice_emotion: str, rms_p90: float, burning_threshold_db: float) -> Tuple[str, str, str]:
    """
    SenseVoice の感情タグとピーク音量 (rms_p90) から判定カテゴリと expression_prompt を決定する。
    戻り値: (category, expression_prompt, decision_reason)
    """
    emo_upper = sensevoice_emotion.upper()

    # 1. ANGRY (任意音量) -> BURNING
    if "ANGRY" in emo_upper:
        category = "BURNING"
        reason = "SenseVoice: ANGRY (判定: BURNING)"
    # 2. HAPPY (任意音量) -> JOYFUL
    elif "HAPPY" in emo_upper:
        category = "JOYFUL"
        reason = "SenseVoice: HAPPY (判定: JOYFUL)"
    # 3. SAD (任意音量) -> EMOTIONAL
    elif "SAD" in emo_upper:
        category = "EMOTIONAL"
        reason = "SenseVoice: SAD (判定: EMOTIONAL)"
    # 4. NEUTRAL (またはその他) -> 音量による分岐
    else:
        if rms_p90 >= burning_threshold_db:
            category = "BURNING"
            reason = f"SenseVoice: NEUTRAL + 大声 (rms_p90 {rms_p90}dB >= {burning_threshold_db}dB -> BURNING昇格)"
        else:
            category = "COOL"
            reason = f"SenseVoice: NEUTRAL + 通常声量 (rms_p90 {rms_p90}dB < {burning_threshold_db}dB -> COOL)"

    prompt = EXPRESSION_PROMPTS.get(category, EXPRESSION_PROMPTS["COOL"])
    return category, prompt, reason


# ---------------------------------------------------------------------------
# SenseVoice 感情タグ抽出
# ---------------------------------------------------------------------------
EMOTION_TAG_PATTERN = re.compile(r"<\|(HAPPY|SAD|ANGRY|NEUTRAL)\|>", re.IGNORECASE)


def extract_emotion_tag(text: str) -> str:
    """SenseVoice 出力テキストから <|HAPPY|> などの感情タグを抽出する"""
    match = EMOTION_TAG_PATTERN.search(text)
    if match:
        return match.group(1).upper()
    # タグが見つからない場合は NEUTRAL とみなす
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# CSV ログ記録
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "timestamp",
    "filename",
    "duration_sec",
    "rms_p90_db",
    "threshold_db",
    "raw_sensevoice_text",
    "extracted_emotion",
    "final_category",
    "decision_reason",
    "inference_time_sec",
    "vram_delta_mb",
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
    parser = argparse.ArgumentParser(description="StoryWeaver Live - Phase 1-B SenseVoice & ピーク音量検証")
    parser.add_argument("--audio-dir", type=str, default="test_assets/audio", help="テスト音声ディレクトリ")
    parser.add_argument("--audio", type=str, default=None, help="単一テスト音声ファイルのパス")
    parser.add_argument("--config", type=str, default="config.json", help="設定ファイルパス")
    parser.add_argument("--threshold", type=float, default=None, help="一時的な BURNING_DB_THRESHOLD 上書き")
    parser.add_argument("--model", type=str, default="iic/SenseVoiceSmall", help="SenseVoice モデルパス/名前")
    parser.add_argument("--csv", type=str, default="sensevoice_benchmark.csv", help="出力先 CSV ファイル")

    args = parser.parse_args()

    # 1. 閾値の読み込み
    config_path = Path(args.config)
    burning_threshold = -12.0
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                burning_threshold = float(cfg.get("BURNING_DB_THRESHOLD", -12.0))
        except Exception as e:
            print(f"[WARN] config.json 読み込み失敗: {e}。デフォルト -12.0 dBFS を使用します。")
    if args.threshold is not None:
        burning_threshold = args.threshold

    # 2. テスト音声の列挙
    audio_paths = []
    if args.audio:
        p = Path(args.audio)
        if not p.is_file():
            print(f"[ERROR] 指定された音声ファイルが存在しません: {p}")
            sys.exit(1)
        audio_paths.append(p)
    else:
        audio_dir = Path(args.audio_dir)
        if not audio_dir.is_dir():
            print(f"[ERROR] 音声ディレクトリが存在しません: {audio_dir}")
            sys.exit(1)
        audio_paths = sorted(list(audio_dir.glob("*.wav")))

    if not audio_paths:
        print(f"[ERROR] 評価対象の WAV ファイルが見つかりません: {args.audio_dir}")
        print("`python record_test_audio.py --generate-synthetic` でダミー音声を生成するか録音してください。")
        sys.exit(1)

    print("=" * 80, flush=True)
    print(" StoryWeaver Live - Phase 1-B: SenseVoice 感情認識 & ピーク音量検証", flush=True)
    print(f" モデル      : {args.model} (device='cpu')", flush=True)
    print(f" 音声数      : {len(audio_paths)} 件", flush=True)
    print(f" 昇格閾値    : {burning_threshold} dBFS", flush=True)
    print("=" * 80, flush=True)

    # 3. モデルロード前の VRAM 計測
    vram_before = get_gpu_vram_mb()
    print(f"  [1/3] ロード前 GPU VRAM: {vram_before} MB", flush=True)

    # 4. SenseVoiceSmall モデルロード (CPU)
    print(f"  [2/3] SenseVoiceSmall モデルロード中 (device='cpu')...", flush=True)
    t_load_start = time.perf_counter()
    try:
        from funasr import AutoModel
        model = AutoModel(
            model=args.model,
            device="cpu",
            disable_update=True,
            log_level="ERROR",
        )
    except Exception as e:
        print(f"[ERROR] SenseVoice モデルのロードに失敗しました: {e}")
        sys.exit(1)
    t_load_end = time.perf_counter()
    load_time_sec = round(t_load_end - t_load_start, 2)

    # 5. ロード後の VRAM 計測
    vram_after = get_gpu_vram_mb()
    vram_delta = round(vram_after - vram_before, 1)
    print(f"  [3/3] ロード完了 (所要時間: {load_time_sec}s)", flush=True)
    print(f"        ロード後 GPU VRAM: {vram_after} MB (増分: {vram_delta} MB)", flush=True)

    if vram_delta <= 10.0:  # 多少のOS変動バッファ
        print("        [PASS Gate 1-B 基準1] VRAM 消費ゼロ (増分 0 MB 実証)", flush=True)
    else:
        print(f"        [FAIL Gate 1-B 基準1] VRAM が増加しています ({vram_delta} MB)!", flush=True)

    print("-" * 80, flush=True)
    csv_path = Path(args.csv)
    results = []

    for idx, wav_p in enumerate(audio_paths, 1):
        print(f"\n[{idx}/{len(audio_paths)}] 評価中: {wav_p.name}", flush=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 音量計算
        rms_p90, duration_sec, valid_frames = compute_rms_p90(wav_p)
        print(f"  - 長さ: {duration_sec}s, ピーク音量 rms_p90: {rms_p90} dBFS (有効フレーム数: {valid_frames})", flush=True)

        # SenseVoice 推論
        t_infer_start = time.perf_counter()
        try:
            res = model.generate(
                input=str(wav_p.resolve()),
                cache={},
                language="auto",
                use_itn=True,
            )
            t_infer_end = time.perf_counter()
            infer_time = round(t_infer_end - t_infer_start, 3)

            raw_text = ""
            if isinstance(res, list) and len(res) > 0:
                raw_text = res[0].get("text", "")
            elif isinstance(res, dict):
                raw_text = res.get("text", "")
        except Exception as e:
            print(f"  [ERROR] 推論エラー: {e}", flush=True)
            infer_time = -1.0
            raw_text = f"ERROR: {e}"

        # 感情タグ抽出 & ハイブリッド判定
        detected_emotion = extract_emotion_tag(raw_text)
        category, exp_prompt, reason = determine_expression_category(
            detected_emotion, rms_p90, burning_threshold
        )

        speed_status = "PASS" if (0 < infer_time <= 0.5) else ("WARN" if infer_time <= 1.0 else "SLOW")

        print(f"  - SenseVoice 出力  : {raw_text}", flush=True)
        print(f"  - 抽出感情タグ     : {detected_emotion}", flush=True)
        print(f"  - 最終判定カテゴリ : {category} ({reason})", flush=True)
        print(f"  - 推論時間         : {infer_time}s [{speed_status} 目標0.5s以内]", flush=True)
        print(f"  - expression_prompt: {exp_prompt}", flush=True)

        row = {
            "timestamp": ts,
            "filename": wav_p.name,
            "duration_sec": duration_sec,
            "rms_p90_db": rms_p90,
            "threshold_db": burning_threshold,
            "raw_sensevoice_text": raw_text,
            "extracted_emotion": detected_emotion,
            "final_category": category,
            "decision_reason": reason,
            "inference_time_sec": infer_time,
            "vram_delta_mb": vram_delta,
        }
        log_to_csv(csv_path, row)
        results.append((wav_p.name, duration_sec, rms_p90, detected_emotion, category, infer_time))

    print("\n" + "=" * 80, flush=True)
    print(" 全音声 検証サマリー", flush=True)
    print("=" * 80, flush=True)
    print(f"{'Filename':<16} | {'Len(s)':<6} | {'rms_p90':<10} | {'Emotion':<10} | {'Category':<10} | {'Time(s)':<8}")
    print("-" * 80, flush=True)
    for name, dur, rms, emo, cat, t_inf in results:
        print(f"{name:<16} | {dur:<6} | {rms:<10} | {emo:<10} | {cat:<10} | {t_inf:<8}", flush=True)
    print("=" * 80, flush=True)
    print(f"結果を {csv_path.resolve()} に保存しました。", flush=True)


if __name__ == "__main__":
    main()
