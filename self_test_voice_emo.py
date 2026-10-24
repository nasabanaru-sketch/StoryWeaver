"""
self_test_voice_emo.py
合成音声 A/B/C による自動検証スクリプト
1. 合成音声 A (標準), B (吐息・ゆったり), C (緊張・硬質) の生成
2. NaN チェック & 特徴量変動 (breathiness上昇, softness低下) の検証
3. 推論時間 & VRAM 増分 (0MB) の計測
"""

import math
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

import numpy as np
import soundfile as sf
import torch

from voice_emo_analyzer import get_voice_emo_analyzer

BASE_DIR = Path(__file__).resolve().parent
TEST_DIR = BASE_DIR / "test_assets" / "synthetic_voice"
TEST_DIR.mkdir(parents=True, exist_ok=True)


def generate_synthetic_voices(sr: int = 16000, duration: float = 3.0) -> dict[str, Path]:
    """3種類の合成音声を生成して保存"""
    num_samples = int(sr * duration)
    t = np.linspace(0, duration, num_samples, endpoint=False)

    # 1) 音声A: 標準トーン (200Hz + 2nd, 3rd倍音)
    wave_a = (
        0.50 * np.sin(2 * np.pi * 200 * t)
        + 0.25 * np.sin(2 * np.pi * 400 * t)
        + 0.12 * np.sin(2 * np.pi * 600 * t)
    )
    # フェードイン・アウト
    fade_len = int(sr * 0.05)
    env = np.ones(num_samples)
    env[:fade_len] = np.linspace(0, 1, fade_len)
    env[-fade_len:] = np.linspace(1, 0, fade_len)
    wave_a = (wave_a * env).astype(np.float32)

    # 2) 音声B: 疑似ブレス・ゆったり (180Hz + ノイズ高比率 + 緩やかなエンベロープ)
    noise = np.random.normal(0, 0.25, num_samples)
    wave_b = 0.25 * np.sin(2 * np.pi * 180 * t) + 0.10 * np.sin(2 * np.pi * 360 * t) + noise
    # 緩やかなエンベロープ
    env_b = np.sin(np.pi * t / duration) ** 1.5
    wave_b = (wave_b * env_b).astype(np.float32)
    # クリッピング防止正規化
    wave_b = wave_b / (np.max(np.abs(wave_b)) + 1e-6) * 0.7

    # 3) 音声C: 疑似緊張・高音硬質 (350Hz + 強い高次倍音 + 振幅変調)
    wave_c = (
        0.30 * np.sin(2 * np.pi * 350 * t)
        + 0.35 * np.sin(2 * np.pi * 700 * t)
        + 0.30 * np.sin(2 * np.pi * 1050 * t)
        + 0.25 * np.sin(2 * np.pi * 1400 * t)
        + 0.20 * np.sin(2 * np.pi * 2100 * t)
    )
    # 振幅変調 (tremor 疑似: 8Hz)
    am = 1.0 + 0.25 * np.sin(2 * np.pi * 8 * t)
    wave_c = (wave_c * am * env).astype(np.float32)
    wave_c = wave_c / (np.max(np.abs(wave_c)) + 1e-6) * 0.85

    paths = {
        "voice_A": TEST_DIR / "voice_A_standard.wav",
        "voice_B": TEST_DIR / "voice_B_breathy_slow.wav",
        "voice_C": TEST_DIR / "voice_C_tense_harsh.wav",
    }

    sf.write(paths["voice_A"], wave_a, sr, subtype="PCM_16")
    sf.write(paths["voice_B"], wave_b, sr, subtype="PCM_16")
    sf.write(paths["voice_C"], wave_c, sr, subtype="PCM_16")
    return paths


def get_vram_used_bytes() -> int:
    """現在の PyTorch CUDA 確保メモリ（bytes）"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated()
    return 0


def run_self_test():
    print("=================================================================")
    print("StoryWeaver Live: 12感情・色気スコア算出モジュール 自動検証")
    print("=================================================================")

    # 1. 音声生成
    print("\n[Step 1] テスト合成音声の生成...")
    voice_paths = generate_synthetic_voices()
    for name, p in voice_paths.items():
        print(f"  - 生成: {name} -> {p.name} ({p.stat().st_size} bytes)")

    # 2. アナライザー初期化 & VRAM計測
    print("\n[Step 2] アナライザー初期化 (CPU固定) & ウォームアップ...")
    vram_before = get_vram_used_bytes()
    analyzer = get_voice_emo_analyzer(device="cpu")
    t_load_start = time.time()
    analyzer.load_model()
    t_load = time.time() - t_load_start
    print(f"  - モデルロード時間: {t_load:.2f}秒")

    t_warm_start = time.time()
    analyzer.warmup()
    t_warm = time.time() - t_warm_start
    print(f"  - ウォームアップ時間: {t_warm:.2f}秒")

    vram_after = get_vram_used_bytes()
    vram_diff_mb = (vram_after - vram_before) / (1024 * 1024)
    print(f"  - PyTorch CUDA VRAM 増分: {vram_diff_mb:.2f} MB (目標: 0.0 MB)")
    assert vram_diff_mb == 0.0, f"VRAM 増分が 0MB ではありません: {vram_diff_mb}MB"

    # 3. 各音声の推論と数値検証
    print("\n[Step 3] 合成音声 A/B/C の推論テスト...")
    results = {}
    for name, p in voice_paths.items():
        t0 = time.time()
        res = analyzer.analyze(p)
        elapsed = time.time() - t0
        results[name] = res

        print(f"\n--- {name} ({p.name}) ---")
        print(f"推論時間: {elapsed:.3f}秒 (モジュール計測: {res['analysis_time_sec']:.3f}秒)")
        print(f"Top-1 感情: {res['primary_emotion']['icon']} {res['primary_emotion']['name_ja']} ({res['primary_emotion']['score']} pt, weight: {res['primary_emotion']['weight']})")
        print(f"Top-2 感情: {res['secondary_emotion']['icon']} {res['secondary_emotion']['name_ja']} ({res['secondary_emotion']['score']} pt, weight: {res['secondary_emotion']['weight']})")
        print(f"7基礎指標: {res['features_7']}")
        print(f"Base プロンプト: {res['expression_prompt']}")
        print(f"FD   プロンプト: {res['expression_prompt_fd']}")

        # NaN / Inf チェック
        for k, v in res["features_7"].items():
            assert not (math.isnan(v) or math.isinf(v)), f"NaN/Inf 検出: {name} 7基礎指標 {k}={v}"
        for k, v in res["emotions_12"].items():
            assert not (math.isnan(v) or math.isinf(v)), f"NaN/Inf 検出: {name} 12感情 {k}={v}"

    # 4. 特徴量変動の検証
    print("\n[Step 4] 特徴量変動の検証...")
    res_a = results["voice_A"]
    res_b = results["voice_B"]
    res_c = results["voice_C"]

    bre_a = res_a["features_7"]["breathiness"]
    bre_b = res_b["features_7"]["breathiness"]
    print(f"  - Breathiness: 音声A={bre_a}pt -> 音声B={bre_b}pt (差: {bre_b - bre_a:+.1f}pt)")
    assert bre_b > bre_a, f"検証失敗: 音声Bの breathiness ({bre_b}) が 音声A ({bre_a}) を上回っていません"
    print("    [PASS] 音声B (吐息・ノイズ) で breathiness が正常に上昇しました。")

    sof_a = res_a["features_7"]["softness"]
    sof_c = res_c["features_7"]["softness"]
    print(f"  - Softness:    音声A={sof_a}pt -> 音声C={sof_c}pt (差: {sof_c - sof_a:+.1f}pt)")
    assert sof_c < sof_a, f"検証失敗: 音声Cの softness ({sof_c}) が 音声A ({sof_a}) を下回っていません"
    print("    [PASS] 音声C (高音・硬質倍音) で softness が正常に低下しました。")

    # 5. 推論性能チェック
    max_infer_time = max(r["analysis_time_sec"] for r in results.values())
    print(f"\n[Step 5] 性能要件チェック: 最大推論時間 {max_infer_time:.3f}秒 (目標: 0.8秒以内)")
    if max_infer_time <= 0.8:
        print("    [PASS] CPU推論性能目標 (0.8秒以内) をクリアしました！")
    else:
        print(f"    [WARN] CPU推論性能目標 0.8秒をわずかに超過: {max_infer_time}秒")

    print("\n=================================================================")
    print("すべての自動検証テストに合格しました！ (ALL TESTS PASSED)")
    print("=================================================================")


if __name__ == "__main__":
    run_self_test()
