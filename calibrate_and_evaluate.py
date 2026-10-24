"""
calibrate_and_evaluate.py
CLI用ベースライン登録＆演技採点テストスクリプト

使用例:
  # 対話メニュー起動
  python calibrate_and_evaluate.py

  # モード1: ベースライン登録 (ファイル指定)
  python calibrate_and_evaluate.py --mode calibrate --input test_assets/synthetic_voice/voice_A_standard.wav

  # モード2: 演技採点テスト (ファイル指定)
  python calibrate_and_evaluate.py --mode evaluate --input test_assets/synthetic_voice/voice_B_breathy_slow.wav
"""

import argparse
import sys
import time
from pathlib import Path

# Windows コンソールでの UTF-8 出力対応
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import sounddevice as sd
import soundfile as sf

from voice_emo_analyzer import get_voice_emo_analyzer

BASE_DIR = Path(__file__).resolve().parent
TEMP_RECORD_PATH = BASE_DIR / "tmp_audio" / "cli_recorded.wav"
TEMP_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)


def record_mic(duration_sec: float = 3.5, sr: int = 16000) -> Path:
    """マイクから音声を録音して WAV 保存"""
    print(f"\n[録音開始] {duration_sec} 秒間、マイクに向かって発声してください...")
    for i in range(3, 0, -1):
        print(f"  カウントダウン: {i}...")
        time.sleep(1.0)
    print("  ● 録音中 (REC)...")

    recording = sd.rec(int(duration_sec * sr), samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    print("  ■ 録音完了！")

    sf.write(TEMP_RECORD_PATH, recording, sr, subtype="PCM_16")
    return TEMP_RECORD_PATH


def run_calibrate(wav_path: Path):
    print(f"\n=======================================================")
    print(f"【モード1】棒読みベースライン登録: {wav_path.name}")
    print(f"=======================================================")
    analyzer = get_voice_emo_analyzer()
    analyzer.load_model()
    analyzer.warmup()

    print("特徴量を抽出して基準値 (voice_emo_baseline.json) を更新中...")
    new_baseline = analyzer.calibrate_baseline([wav_path])

    print("\n[更新されたベースライン基準値]")
    for k, v in new_baseline.items():
        print(f"  - {k:22s}: {v}")
    print("\nベースラインの更新が完了しました！以降の解析ではこの値が50点の基準となります。")


def run_evaluate(wav_path: Path):
    print(f"\n=======================================================")
    print(f"【モード2】演技感情採点テスト: {wav_path.name}")
    print(f"=======================================================")
    analyzer = get_voice_emo_analyzer()
    analyzer.load_model()
    analyzer.warmup()

    res = analyzer.analyze(wav_path)
    top1 = res["primary_emotion"]
    top2 = res["secondary_emotion"]

    print(f"\n[総合評価結果] (解析時間: {res['analysis_time_sec']:.3f} 秒)")
    print(f"  ★ Top-1 感情: {top1['icon']} {top1['name_ja']} ({top1['score']} pt / Weight: {top1['weight']})")
    print(f"  ★ Top-2 感情: {top2['icon']} {top2['name_ja']} ({top2['score']} pt / Weight: {top2['weight']})")

    print("\n[7つの基礎指標 (0〜100pt / 基準値=50pt)]")
    for k, v in res["features_7"].items():
        bar_len = int(v / 5)
        bar = "■" * bar_len + " " * (20 - bar_len)
        print(f"  - {k:12s} [{bar}] {v:5.1f} pt")

    print("\n[12感情スコア一覧]")
    sorted_emotions = sorted(res["emotions_12"].items(), key=lambda x: x[1], reverse=True)
    emotions_def = analyzer.config.get("emotions", {})
    for emo_id, score in sorted_emotions:
        info = emotions_def.get(emo_id, {})
        icon = info.get("icon", "  ")
        name_ja = info.get("name_ja", emo_id)
        bar_len = int(score / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {icon} {name_ja:10s} [{bar}] {score:5.1f} pt")

    print("\n[Animagine XL 3.1 生成プロンプト]")
    print(f"  ● Node 5 (Base - 全体構図):\n    {res['expression_prompt']}")
    print(f"  ● Node 32 (FD - FaceDetailer 表情彫刻):\n    {res['expression_prompt_fd']}")


def interactive_menu():
    print("=======================================================")
    print("StoryWeaver Live: 12感情・色気スコア分析 CLI")
    print("=======================================================")
    print("1: マイクで棒読みを録音してベースライン登録 (モード1)")
    print("2: マイクで演技を録音して採点テスト (モード2)")
    print("3: 既存WAVファイルでベースライン登録")
    print("4: 既存WAVファイルで演技採点テスト")
    print("q: 終了")
    choice = input("\n選択してください (1-4, q): ").strip()

    if choice == "1":
        p = record_mic(duration_sec=3.5)
        run_calibrate(p)
    elif choice == "2":
        p = record_mic(duration_sec=4.0)
        run_evaluate(p)
    elif choice == "3":
        path_str = input("WAVファイルパスを入力: ").strip().strip('"')
        if Path(path_str).is_file():
            run_calibrate(Path(path_str))
        else:
            print("エラー: ファイルが存在しません")
    elif choice == "4":
        path_str = input("WAVファイルパスを入力: ").strip().strip('"')
        if Path(path_str).is_file():
            run_evaluate(Path(path_str))
        else:
            print("エラー: ファイルが存在しません")
    else:
        print("終了します。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice Emotion Calibrate & Evaluate CLI")
    parser.add_argument("--mode", choices=["calibrate", "evaluate"], help="実行モード")
    parser.add_argument("--input", type=str, help="入力 WAV ファイルパス (省略時はマイク録音)")
    parser.add_argument("--duration", type=float, default=3.5, help="マイク録音秒数")
    args = parser.parse_args()

    if args.mode == "calibrate":
        target_path = Path(args.input) if args.input else record_mic(args.duration)
        run_calibrate(target_path)
    elif args.mode == "evaluate":
        target_path = Path(args.input) if args.input else record_mic(args.duration)
        run_evaluate(target_path)
    else:
        interactive_menu()
