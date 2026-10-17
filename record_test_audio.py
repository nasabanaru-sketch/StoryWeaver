"""
StoryWeaver Live - Phase 1-B テスト音声録音・生成ヘルパー
record_test_audio.py

目的:
  マイクから 16kHz / モノラル / 16bit PCM WAV 形式で以下の4パターンのテスト音声を録音・保存する。
  1. 01_shout.wav : 大声・叫び声（BURNING昇格テスト用）
  2. 02_happy.wav : 明るく元気な声（JOYFULテスト用）
  3. 03_sad.wav   : 悲痛・小声（EMOTIONALテスト用）
  4. 04_cool.wav  : 落ち着いた通常の声量（COOLテスト用）

オプション:
  --generate-synthetic: マイク録音の代わりに合成テスト音声WAV（正弦波・ノイズ・音量変化）を自動生成する。
"""

import argparse
from pathlib import Path
import sys
import time
import numpy as np

# Windows コンソールでの文字化け防止
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import soundfile as sf
except ImportError:
    print("[ERROR] soundfile がインストールされていません。'pip install soundfile' を実行してください。")
    sys.exit(1)

AUDIO_DIR = Path("test_assets/audio")
SAMPLE_RATE = 16000  # 16kHz
CHANNELS = 1         # モノラル

SCENARIOS = [
    {
        "filename": "01_shout.wav",
        "title": "01_shout.wav （大声・叫び声）",
        "guide": "マイクに向かって叫ぶような大声を出してください（例: 「うおおお！絶対に負けないぞ！」）",
        "duration": 4.0,
    },
    {
        "filename": "02_happy.wav",
        "title": "02_happy.wav （明るく元気な声）",
        "guide": "明るく笑顔で元気よく話してください（例: 「やったー！本当にありがとう、最高の気分だ！」）",
        "duration": 4.0,
    },
    {
        "filename": "03_sad.wav",
        "title": "03_sad.wav （悲痛・小声）",
        "guide": "静かに、悲しげ・落胆したトーンで話してください（例: 「そんな…もう終わりだなんて…」）",
        "duration": 4.0,
    },
    {
        "filename": "04_cool.wav",
        "title": "04_cool.wav （落ち着いた通常の声量）",
        "guide": "冷静に、平坦・クールな通常トーンで話してください（例: 「ターゲット捕捉。これよりシステムを突破する」）",
        "duration": 4.0,
    },
]


def record_interactive():
    try:
        import sounddevice as sd
    except ImportError:
        print("[ERROR] sounddevice がインストールされていません。'pip install sounddevice' を実行してください。")
        sys.exit(1)

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print(" StoryWeaver Live - テスト音声録音ヘルパー")
    print(f" フォーマット: {SAMPLE_RATE}Hz / モノラル / 16bit PCM WAV")
    print(f" 保存先: {AUDIO_DIR.resolve()}")
    print("=" * 80)

    for item in SCENARIOS:
        out_path = AUDIO_DIR / item["filename"]
        print(f"\n[{item['title']}]")
        print(f" ガイド: {item['guide']}")
        print(f" 録音時間: {item['duration']} 秒")
        input("  >> 準備ができたら [Enter] キーを押して録音を開始します...")

        print("  ● 録音中... 話してください！", flush=True)
        try:
            recording = sd.rec(
                int(item["duration"] * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
            )
            sd.wait()
        except Exception as e:
            print(f"  [ERROR] 録音中にエラーが発生しました: {e}")
            continue

        sf.write(out_path, recording, SAMPLE_RATE, subtype="PCM_16")
        print(f"  ✔ 保存完了: {out_path} ({item['duration']}s)")

    print("\n" + "=" * 80)
    print(" 全4パターンの録音が完了しました！")
    print("=" * 80)


def generate_synthetic_audio():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print(" 合成テスト音声（ダミーWAV）を生成します...")
    print("=" * 80)

    # 1. 大声（高振幅・叫び声シミュレート: -8 dBFS 程度）
    t = np.linspace(0, 3.5, int(3.5 * SAMPLE_RATE), False)
    # 基本周波数 + 倍音 + ノイズ
    sig_shout = (
        0.5 * np.sin(2 * np.pi * 300 * t) +
        0.3 * np.sin(2 * np.pi * 600 * t) +
        0.1 * np.random.normal(0, 0.2, len(t))
    )
    # エンベロープ
    env = np.sin(np.pi * np.linspace(0, 1, len(t)))
    sig_shout = sig_shout * env
    sig_shout = sig_shout / np.max(np.abs(sig_shout)) * 0.7  # -3dBFS ピーク
    sf.write(AUDIO_DIR / "01_shout.wav", (sig_shout * 32767).astype(np.int16), SAMPLE_RATE, subtype="PCM_16")
    print("  [OK] 生成: 01_shout.wav (高音量)")

    # 2. 明るい声（中高音域・適度な音量: -15 dBFS 程度）
    t = np.linspace(0, 3.0, int(3.0 * SAMPLE_RATE), False)
    sig_happy = 0.4 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    sig_happy = sig_happy * np.sin(np.pi * np.linspace(0, 1, len(t)))
    sig_happy = sig_happy / np.max(np.abs(sig_happy)) * 0.35
    sf.write(AUDIO_DIR / "02_happy.wav", (sig_happy * 32767).astype(np.int16), SAMPLE_RATE, subtype="PCM_16")
    print("  [OK] 生成: 02_happy.wav (中音量・明瞭)")

    # 3. 悲痛・小声（低振幅・小声: -28 dBFS 程度）
    t = np.linspace(0, 3.0, int(3.0 * SAMPLE_RATE), False)
    sig_sad = 0.2 * np.sin(2 * np.pi * 220 * t) + 0.05 * np.random.normal(0, 0.1, len(t))
    sig_sad = sig_sad * np.sin(np.pi * np.linspace(0, 1, len(t)))
    sig_sad = sig_sad / np.max(np.abs(sig_sad)) * 0.08
    sf.write(AUDIO_DIR / "03_sad.wav", (sig_sad * 32767).astype(np.int16), SAMPLE_RATE, subtype="PCM_16")
    print("  [OK] 生成: 03_sad.wav (低音量・小声)")

    # 4. 冷静・通常（平坦な音量: -18 dBFS 程度）
    t = np.linspace(0, 3.0, int(3.0 * SAMPLE_RATE), False)
    sig_cool = 0.3 * np.sin(2 * np.pi * 260 * t) + 0.1 * np.sin(2 * np.pi * 520 * t)
    sig_cool = sig_cool * np.sin(np.pi * np.linspace(0, 1, len(t)))
    sig_cool = sig_cool / np.max(np.abs(sig_cool)) * 0.2
    sf.write(AUDIO_DIR / "04_cool.wav", (sig_cool * 32767).astype(np.int16), SAMPLE_RATE, subtype="PCM_16")
    print("  [OK] 生成: 04_cool.wav (通常音量)")

    print("\n合成ダミー音声の作成が完了しました。")


def main():
    parser = argparse.ArgumentParser(description="StoryWeaver Live - テスト音声録音ヘルパー")
    parser.add_argument(
        "--generate-synthetic",
        action="store_true",
        help="マイク録音の代わりに合成WAVを生成する",
    )
    args = parser.parse_args()

    if args.generate_synthetic:
        generate_synthetic_audio()
    else:
        record_interactive()


if __name__ == "__main__":
    main()
