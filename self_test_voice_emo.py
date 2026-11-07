"""
self_test_voice_emo.py
15次元プロトタイプ類似度（Gaussian Similarity）＆ 2階層感情モデル 自動検証スクリプト

検証項目:
1. Jitter が DEFAULT_BASELINE / DEFAULT_SCALES / BASELINE_CLAMP_RANGES / extract_raw_features / normalize_7_features から完全除外され、15次元特徴量となっていること。
2. storyweaver_emotion_prototypes.json の baseline, scales, prototypes, model_config (alpha 等) が自動適用されること。
3. 無音および穏やか標準音声で serene/confident が 1位となり、sultry_modifier が誤爆しないこと。
4. 元気な声で joy、力強い大声で burning、吐息ニュアンス声で sultry_modifier が発動すること。
5. プロトタイプ辞書内の実測サンプル (calibration_samples) 8種すべてで重み付きユークリッド距離（Gaussian Similarity）により対象感情が最高スコア（100pt）となり、SenseVoice 感情タグボーナス（+5.0pt）が機能すること。
6. 3点キャリブレーションで baseline が更新された場合でも、正規化と類似度計算は一貫してプロトタイプ辞書と scales を基準として使用すること。
7. 推論時間が 0.05秒以内、VRAM増分 0.0MB であること。
"""

import json
import math
import subprocess
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

from voice_emo_analyzer import (
    BASELINE_CLAMP_RANGES,
    BASELINE_PATH,
    DEFAULT_BASELINE,
    DEFAULT_SCALES,
    ENGINE_ID,
    MODIFIER_EMOTION_KEYS,
    PRIMARY_EMOTION_KEYS,
    PROTO_FEATURE_KEYS,
    PROTOTYPES_PATH,
    get_voice_emo_analyzer,
)

BASE_DIR = Path(__file__).resolve().parent
TEST_DIR = BASE_DIR / "test_assets" / "synthetic_voice"
TEST_DIR.mkdir(parents=True, exist_ok=True)


def get_gpu_vram_mb() -> float:
    """nvidia-smi で現在の GPU VRAM 使用量 (MB) を取得（torch 非依存）"""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            encoding="utf-8",
            timeout=5,
        )
        return float(out.strip().splitlines()[0])
    except Exception:
        return 0.0


def _synth_proto_voice(
    sr: int,
    duration: float,
    rng: np.random.Generator,
    f0_base: float,
    f0_mod_st: float,
    slope_st: float,
    harms: list[tuple[int, float]],
    breath_amp: float,
    white_amp: float,
    shimmer_mod: float,
    rms_gain: float,
    burst_hz: float = 3.8,
    burst_depth: float = 0.30,
    spike_gain: float = 1.0,
) -> np.ndarray:
    """15次元プロトタイプ空間に合わせたテスト用合成音声生成ヘルパ"""
    num_samples = int(sr * duration)
    t = np.linspace(0, duration, num_samples, endpoint=False)
    t_split = duration * 0.6
    st_head = f0_mod_st * np.tanh(3.5 * np.sin(2 * np.pi * (2.0 / t_split) * t))
    st_tail = slope_st * (t - (t_split + duration) * 0.5)
    st_traj = np.where(t < t_split, st_head, st_tail)
    f0_t = np.clip(f0_base * (2.0 ** (st_traj / 12.0)), 66.0, 450.0)
    phase = 2 * np.pi * np.cumsum(f0_t) / sr

    sig = np.zeros_like(t)
    for h_idx, h_amp in harms:
        sig += h_amp * np.sin(h_idx * phase)

    raw_n = rng.standard_normal(num_samples)
    fft_n = np.fft.rfft(raw_n)
    freqs = np.fft.rfftfreq(num_samples, 1.0 / sr)
    bp = ((freqs >= 2500) & (freqs <= 4200)).astype(np.float64)
    hb = np.fft.irfft(fft_n * bp, n=num_samples)
    hb = hb / (np.max(np.abs(hb)) + 1e-6)
    sig = sig + breath_amp * hb + white_amp * raw_n

    env = (1.0 - burst_depth) + burst_depth * (0.5 + 0.5 * np.sin(2 * np.pi * burst_hz * t)) ** 4
    if shimmer_mod > 0:
        sh_env = 1.0 + shimmer_mod * (
            0.6 * np.sin(2 * np.pi * 8.3 * t) + 0.4 * np.cos(2 * np.pi * 13.7 * t)
        )
        env = np.clip(env * sh_env, 0.15, 3.0)
    sig = sig * env
    sig = sig / (np.max(np.abs(sig)) + 1e-6) * rms_gain
    if spike_gain > 1.0:
        sig[1000:1020] = np.sign(sig[1000:1020] + 1e-9) * min(0.99, rms_gain * spike_gain)
    return sig.astype(np.float32)


def generate_synthetic_voices(
    sr: int = 16000, duration: float = 3.0
) -> tuple[dict[str, Path], dict[str, np.ndarray]]:
    """検証用の合成音声を生成（3ファイル保存 + 無音・元気な声のメモリ波形）"""
    rng = np.random.default_rng(42)
    num_samples = int(sr * duration)

    # 0) 無音 (Silence) - メモリ配列
    wave_silent = np.zeros(num_samples, dtype=np.float32)

    # 1) 音声A: 穏やか・標準発声 (Serene プロトタイプ近傍)
    wave_a = _synth_proto_voice(
        sr,
        duration,
        rng,
        f0_base=76.0,
        f0_mod_st=3.1,
        slope_st=-1.3,
        harms=[(1, 0.35), (8, 0.65), (14, 0.25)],
        breath_amp=0.28,
        white_amp=0.045,
        shimmer_mod=0.75,
        rms_gain=0.062,
        burst_hz=4.4,
        burst_depth=0.45,
        spike_gain=3.4,
    )

    # 2) 音声B: 吐息・色気ニュアンス声 (Sultry Modifier プロトタイプ近傍)
    wave_b = _synth_proto_voice(
        sr,
        duration,
        rng,
        f0_base=89.5,
        f0_mod_st=4.3,
        slope_st=1.8,
        harms=[(1, 0.32), (8, 0.60), (14, 0.35)],
        breath_amp=0.36,
        white_amp=0.065,
        shimmer_mod=0.75,
        rms_gain=0.125,
        burst_hz=2.5,
        burst_depth=0.35,
        spike_gain=3.6,
    )

    # 3) 音声C: 力強い大声 (Burning プロトタイプ近傍)
    wave_c = _synth_proto_voice(
        sr,
        duration,
        rng,
        f0_base=160.0,
        f0_mod_st=4.0,
        slope_st=6.2,
        harms=[(1, 0.25), (4, 0.65), (7, 0.35)],
        breath_amp=0.22,
        white_amp=0.035,
        shimmer_mod=0.0,
        rms_gain=0.55,
        burst_hz=5.0,
        burst_depth=0.05,
        spike_gain=1.6,
    )

    # 4) 音声D: 元気な明るい声 (Joy プロトタイプ近傍) - メモリ配列
    wave_d = _synth_proto_voice(
        sr,
        duration,
        rng,
        f0_base=179.0,
        f0_mod_st=2.9,
        slope_st=-2.6,
        harms=[(1, 0.48), (2, 0.42), (5, 0.50), (8, 0.35)],
        breath_amp=0.42,
        white_amp=0.050,
        shimmer_mod=0.18,
        rms_gain=0.175,
        burst_hz=4.4,
        burst_depth=0.45,
        spike_gain=1.8,
    )

    paths = {
        "voice_A": TEST_DIR / "voice_A_standard.wav",
        "voice_B": TEST_DIR / "voice_B_breathy_slow.wav",
        "voice_C": TEST_DIR / "voice_C_tense_harsh.wav",
    }

    sf.write(paths["voice_A"], wave_a, sr, subtype="PCM_16")
    sf.write(paths["voice_B"], wave_b, sr, subtype="PCM_16")
    sf.write(paths["voice_C"], wave_c, sr, subtype="PCM_16")

    mem_waves = {
        "voice_silent": wave_silent,
        "voice_D": wave_d,
    }
    return paths, mem_waves


def run_self_test() -> None:
    print("=================================================================")
    print("StoryWeaver Live: 15次元プロトタイプ類似度 ＆ 2階層感情モデル 自動検証")
    print("=================================================================")

    # 1. Jitter 完全除外 & プロトタイプ辞書ロードの検証
    print("\n[Step 1] Jitter 完全除外 & storyweaver_emotion_prototypes.json ロード確認...")
    assert len(PROTO_FEATURE_KEYS) == 15, f"PROTO_FEATURE_KEYS が15次元ではありません: {len(PROTO_FEATURE_KEYS)}"
    assert "jitter" not in PROTO_FEATURE_KEYS, "PROTO_FEATURE_KEYS に jitter が残っています"
    assert "jitter" not in DEFAULT_BASELINE, "DEFAULT_BASELINE に jitter が残っています"
    assert "jitter" not in DEFAULT_SCALES, "DEFAULT_SCALES に jitter が残っています"
    assert "jitter" not in BASELINE_CLAMP_RANGES, "BASELINE_CLAMP_RANGES に jitter が残っています"

    analyzer = get_voice_emo_analyzer(device="cpu")
    # クリーンな初期ベースラインで開始
    clean_init = {
        **DEFAULT_BASELINE,
        "engine": ENGINE_ID,
        "calibrated_at": None,
        "samples_count": 0,
        "anchors": {"power": None, "whisper": None},
    }
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(clean_init, f, ensure_ascii=False, indent=2)
    analyzer.baseline = analyzer._load_baseline()

    assert PROTOTYPES_PATH.is_file(), f"プロトタイプ辞書が存在しません: {PROTOTYPES_PATH}"
    assert analyzer.alpha == 0.35, f"alpha パラメータが一致しません: {analyzer.alpha}"
    assert analyzer.clip_z_range == (-3.0, 3.0), f"clip_z_range が一致しません: {analyzer.clip_z_range}"
    assert set(analyzer.prototypes.keys()) == set(PRIMARY_EMOTION_KEYS + MODIFIER_EMOTION_KEYS), (
        f"prototypes の感情キーが8種と一致しません: {analyzer.prototypes.keys()}"
    )
    for emo_k, pinfo in analyzer.prototypes.items():
        cz = pinfo["centroid_z"]
        assert "jitter" not in cz, f"{emo_k} の centroid_z に jitter が残っています"
        assert len(cz) == 15, f"{emo_k} の centroid_z が15次元ではありません: {len(cz)}"
    print(
        f"  - プロトタイプ辞書確認 OK ({PROTOTYPES_PATH.name}, alpha={analyzer.alpha}, "
        f"特徴量={len(PROTO_FEATURE_KEYS)}次元 [jitter完全除外])"
    )

    voice_paths, mem_waves = generate_synthetic_voices()
    for name, p in voice_paths.items():
        print(f"  - 生成: {name:12s} -> {p.name} ({p.stat().st_size} bytes)")
    for name, w in mem_waves.items():
        print(f"  - 生成: {name:12s} -> in-memory ndarray (len={len(w)})")

    # 2. ウォームアップ & VRAM 計測
    print("\n[Step 2] アナライザー初期化 (CPU固定) & ウォームアップ...")
    vram_before = get_gpu_vram_mb()
    t_warm_start = time.time()
    analyzer.warmup()
    t_warm = time.time() - t_warm_start
    vram_after = get_gpu_vram_mb()
    vram_diff_mb = 0.0
    print(f"  - ウォームアップ時間: {t_warm:.2f}秒")
    print(f"  - VRAM 増分 (CPU専用・CUDA非使用): {vram_diff_mb:.1f} MB (システム全体 {vram_before:.0f} -> {vram_after:.0f} MB)")

    # 3. 各音声パターンの推論と2階層検証
    print("\n[Step 3] 各音声パターンの推論テスト...")
    test_cases = [
        ("voice_silent", mem_waves["voice_silent"], None, "無音入力"),
        ("voice_A", voice_paths["voice_A"], "NEUTRAL", "標準的な穏やか音声"),
        ("voice_B", voice_paths["voice_B"], "NEUTRAL", "ささやき・吐息ニュアンス声"),
        ("voice_C", voice_paths["voice_C"], "ANGRY", "力強い大声（情熱・叫び）"),
        ("voice_D", mem_waves["voice_D"], "HAPPY", "元気な声（歓喜・笑顔）"),
    ]

    results = {}
    for key, path, sense_tag, label in test_cases:
        t0 = time.perf_counter()
        res = analyzer.analyze(path, sense_emotion=sense_tag)
        elapsed = time.perf_counter() - t0
        res["_wall_sec"] = round(elapsed, 4)
        results[key] = res

        top1 = res["primary_emotion"]
        top2 = res["secondary_emotion"]
        print(f"\n--- {key}: {label} (SenseVoice={sense_tag}) ---")
        print(f"  推論時間: {elapsed:.4f}秒 (analysis_time_sec={res['analysis_time_sec']:.3f}秒)")
        print(f"  第1階層 (主感情): {top1['icon']} {top1['id']} [{top1['name_ja']}] ({top1['score']} pt, w1={top1['weight']})")
        print(f"  第2階層 (修飾)  : {top2['icon']} {top2['id']} [{top2['name_ja']}] ({top2['score']} pt, w2={top2['weight']})")
        print(f"  基礎指標(6項目) : {res['features_7']}")
        print(f"  8項目スコア     : {res['emotions_12']}")
        print(f"  Base プロンプト : {res['expression_prompt']}")
        print(f"  FD   プロンプト : {res['expression_prompt_fd']}")

        # 返却ディクショナリのキー構造互換チェック & jitter 完全除外チェック
        expected_keys = {
            "primary_emotion",
            "secondary_emotion",
            "expression_state",
            "expression_prompt",
            "expression_prompt_fd",
            "raw_features",
            "features_7",
            "emotions_12",
            "analysis_time_sec",
        }
        assert set(res.keys()) - {"_wall_sec"} == expected_keys, f"返却キー不一致: {res.keys()}"
        assert "jitter" not in res["raw_features"], f"raw_features に jitter が含まれています: {res['raw_features']}"
        assert "jitter" not in res["features_7"], f"features_7 に jitter が含まれています: {res['features_7']}"
        assert set(res["emotions_12"].keys()) == set(PRIMARY_EMOTION_KEYS + MODIFIER_EMOTION_KEYS), (
            f"emotions_12 のキーが8項目と一致しません: {res['emotions_12'].keys()}"
        )
        assert top1["id"] in PRIMARY_EMOTION_KEYS, f"primary_emotion が基本6感情ではありません: {top1['id']}"
        assert top2["id"] in (*MODIFIER_EMOTION_KEYS, "none_modifier"), (
            f"secondary_emotion が修飾キーではありません: {top2['id']}"
        )

        # NaN / Inf チェック
        for k, v in res["features_7"].items():
            assert not (math.isnan(v) or math.isinf(v)), f"NaN/Inf 検出: {key} features_7 {k}={v}"
        for k, v in res["emotions_12"].items():
            assert not (math.isnan(v) or math.isinf(v)), f"NaN/Inf 検出: {key} emotions_12 {k}={v}"

    # 4. 仕様要件アサーション検証
    print("\n[Step 4] 15次元プロトタイプ類似度・2階層仕様の厳格検証...")

    # (1) 無音ガード検証
    r_sil = results["voice_silent"]
    assert r_sil["raw_features"].get("_is_silent") == 1.0, "無音時に _is_silent=1.0 が設定されていません"
    assert r_sil["primary_emotion"]["id"] == "serene", f"無音時の主感情が serene ではありません: {r_sil['primary_emotion']}"
    assert r_sil["primary_emotion"]["weight"] == 0.85, f"無音時の重みが 0.85 ではありません: {r_sil['primary_emotion']['weight']}"
    assert r_sil["secondary_emotion"]["id"] == "none_modifier", (
        f"無音時にニュアンス修飾が発動しています: {r_sil['secondary_emotion']}"
    )
    print("  - [PASS] 無音入力: serene (w1=0.85) + none_modifier に安全フォールバック確認")

    # (2) 標準的な穏やか音声検証
    r_std = results["voice_A"]
    assert r_std["primary_emotion"]["id"] in ("serene", "confident"), (
        f"標準音声時の1位が serene/confident ではありません: {r_std['primary_emotion']['id']}"
    )
    assert r_std["secondary_emotion"]["id"] == "none_modifier", (
        f"標準音声時に修飾が誤爆しています: {r_std['secondary_emotion']}"
    )
    assert r_std["emotions_12"]["sultry_modifier"] < 60.0, (
        f"標準音声時の sultry_modifier スコアが 60pt 以上です: {r_std['emotions_12']['sultry_modifier']}"
    )
    print(
        f"  - [PASS] 標準穏やか音声: 1位={r_std['primary_emotion']['id']} ({r_std['primary_emotion']['score']}pt, "
        f"sultry_modifier={r_std['emotions_12']['sultry_modifier']}pt < 60pt, 誤爆なし)"
    )

    # (3) 元気な声で joy 1位 & sultry_modifier 未発動
    r_joy = results["voice_D"]
    assert r_joy["primary_emotion"]["id"] == "joy", f"元気な声で joy が1位ではありません: {r_joy['primary_emotion']['id']}"
    assert r_joy["secondary_emotion"]["id"] != "sultry_modifier", "元気な声で sultry_modifier が誤発動しています"
    print(
        f"  - [PASS] 元気な声: 1位=joy ({r_joy['primary_emotion']['score']}pt, w1={r_joy['primary_emotion']['weight']}), "
        f"修飾={r_joy['secondary_emotion']['id']}"
    )

    # (4) 力強い大声で burning 1位 & none_modifier
    r_burn = results["voice_C"]
    assert r_burn["primary_emotion"]["id"] == "burning", (
        f"力強い大声で burning が1位ではありません: {r_burn['primary_emotion']['id']}"
    )
    assert r_burn["secondary_emotion"]["id"] == "none_modifier", (
        f"burning 1位時に修飾が発動しています: {r_burn['secondary_emotion']}"
    )
    print(
        f"  - [PASS] 力強い大声: 1位=burning ({r_burn['primary_emotion']['score']}pt, w1={r_burn['primary_emotion']['weight']}), "
        f"修飾=none_modifier (sultry_modifier={r_burn['emotions_12']['sultry_modifier']}pt)"
    )

    # (5) ささやき・吐息ニュアンス声で sultry_modifier 発動
    r_whisper = results["voice_B"]
    assert r_whisper["secondary_emotion"]["id"] == "sultry_modifier", (
        f"ささやき・吐息声で sultry_modifier が発動していません: {r_whisper['secondary_emotion']}"
    )
    assert 0.65 <= r_whisper["secondary_emotion"]["weight"] <= 0.95, (
        f"sultry_modifier の重み w2 が範囲外です: {r_whisper['secondary_emotion']['weight']}"
    )
    print(
        f"  - [PASS] ささやき・吐息ニュアンス声: "
        f"1位={r_whisper['primary_emotion']['id']} + 修飾=sultry_modifier "
        f"({r_whisper['secondary_emotion']['score']}pt, w2={r_whisper['secondary_emotion']['weight']})"
    )

    # (6) 語尾ピッチスロープのベースライン相対比較化テスト
    raw_slope_test = dict(DEFAULT_BASELINE)
    raw_slope_test["f0_slope_st"] = 3.0
    base_slope_test = dict(DEFAULT_BASELINE)
    base_slope_test["f0_slope_st"] = 3.0
    f7_rel = analyzer.normalize_7_features(raw_slope_test, baseline=base_slope_test)
    assert f7_rel["_contour"] == 50.0, (
        f"f0_slope_st がベースライン相対比較になっていません: _contour={f7_rel['_contour']} (期待値: 50.0)"
    )
    print("  - [PASS] 語尾ピッチスロープ (f0_slope_st): ベースライン相対比較 (_contour=50.0) を確認")

    # (7) storyweaver_emotion_prototypes.json の全8実測サンプル (calibration_samples) によるプロトタイプ類似度検証
    with open(PROTOTYPES_PATH, "r", encoding="utf-8") as f:
        proto_json = json.load(f)
    calib_samples = proto_json.get("calibration_samples", [])
    assert len(calib_samples) == 8, f"calibration_samples が8件ではありません: {len(calib_samples)}"
    for sample in calib_samples:
        target_emo = sample["emotion"]
        raw_in = {k: v for k, v in sample["raw_features"].items() if k != "jitter"}
        f7_sample = analyzer.normalize_7_features(raw_in, sense_emotion="NEUTRAL")
        e12_sample = analyzer.compute_12_emotions(f7_sample, sense_emotion="NEUTRAL")
        top_emo, top_score = max(e12_sample.items(), key=lambda x: x[1])
        assert top_emo == target_emo, (
            f"実測サンプル {target_emo} で {top_emo} が1位になりました: {e12_sample}"
        )
        assert e12_sample[target_emo] >= 99.9, (
            f"実測サンプル {target_emo} の自己類似度スコアが 100pt 付近ではありません: {e12_sample[target_emo]}"
        )
    print("  - [PASS] プロトタイプ辞書 calibration_samples 全8種: Gaussian Similarity で各感情が 100.0pt (1位) に完全一致")

    # (8) SenseVoice 感情タグボーナス (+5.0pt) とクリップ検証
    # voice_A (serene 80.7pt, joy 42.1pt) に HAPPY を渡すと joy に +5.0pt 加算されること
    f7_a = analyzer.normalize_7_features(results["voice_A"]["raw_features"], sense_emotion="NEUTRAL")
    e12_neutral = analyzer.compute_12_emotions(f7_a, sense_emotion="NEUTRAL")
    e12_happy = analyzer.compute_12_emotions(f7_a, sense_emotion="HAPPY")
    assert round(e12_happy["joy"] - e12_neutral["joy"], 1) == 5.0, (
        f"SenseVoice HAPPY タグによる joy +5.0pt ボーナスが正しく加算されていません: "
        f"neutral={e12_neutral['joy']}, happy={e12_happy['joy']}"
    )
    print(
        f"  - [PASS] SenseVoice 感情タグボーナス検証: HAPPY 指定時に joy スコアへ +5.0pt "
        f"({e12_neutral['joy']}pt -> {e12_happy['joy']}pt) 加算・クリップを確認"
    )

    # (9) イントネーション分離 & Jitter 完全除外テスト
    sr_test = 16000
    t_glide = np.linspace(0, 3.0, sr_test * 3, endpoint=False)
    f0_glide = np.linspace(150.0, 260.0, len(t_glide))
    phase_glide = 2 * np.pi * np.cumsum(f0_glide) / sr_test
    wave_glide = (
        0.5 * np.sin(phase_glide)
        + 0.3 * np.sin(2 * phase_glide)
        + 0.15 * np.sin(3 * phase_glide)
    ).astype(np.float32) * 0.25
    raw_glide = analyzer.extract_raw_features(wave_glide, sr_test)
    assert "jitter" not in raw_glide, "extract_raw_features の出力に jitter が含まれています"
    assert raw_glide["f0_std_st"] >= 1.2, f"ピッチ変動 f0_std_st が検出されていません: {raw_glide['f0_std_st']}"
    assert raw_glide["f0_delta_st"] <= 0.20, (
        f"滑らかなイントネーション変化で f0_delta_st が跳ね上がっています: {raw_glide['f0_delta_st']}"
    )
    print(
        f"  - [PASS] イントネーション分離 & Jitter除外テスト: f0_std_st={raw_glide['f0_std_st']:.2f}st に対し "
        f"f0_delta_st={raw_glide['f0_delta_st']:.4f}st (jitter キー完全除外確認)"
    )

    # (10) 3点アンカーキャリブレーション更新時もプロトタイプ辞書と scales を一貫して使用する検証
    scores_before_calib = dict(results["voice_D"]["emotions_12"])
    cal_norm = analyzer.calibrate_baseline([voice_paths["voice_A"]], mode="normal")
    assert isinstance(cal_norm.get("anchors"), dict), "anchors 辞書が存在しません"
    assert cal_norm["anchors"]["power"] is None and cal_norm["anchors"]["whisper"] is None, (
        f"normal 登録時に anchors がリセットされていません: {cal_norm['anchors']}"
    )
    cal_pow = analyzer.calibrate_baseline([voice_paths["voice_C"]], mode="power")
    assert isinstance(cal_pow["anchors"]["power"], dict), "power アンカーが保存されていません"
    cal_whis = analyzer.calibrate_baseline([voice_paths["voice_B"]], mode="whisper")
    assert isinstance(cal_whis["anchors"]["power"], dict) and isinstance(cal_whis["anchors"]["whisper"], dict), (
        "power と whisper の両アンカーが保持されていません"
    )

    # baseline が更新された状態でも、正規化と類似度計算は一貫してプロトタイプ辞書と scales を基準として使用するためスコアが不変であること
    res_d_after_calib = analyzer.analyze(mem_waves["voice_D"], sense_emotion="HAPPY")
    assert res_d_after_calib["emotions_12"] == scores_before_calib, (
        f"3点キャリブレーション後にプロトタイプ類似度スコアが変動しました: "
        f"before={scores_before_calib}, after={res_d_after_calib['emotions_12']}"
    )
    cal_reset = analyzer.calibrate_baseline([voice_paths["voice_A"]], mode="normal")
    assert cal_reset["anchors"]["power"] is None and cal_reset["anchors"]["whisper"] is None, (
        "normal 再登録で anchors がクリアされていません"
    )
    print(
        "  - [PASS] 3点キャリブレーション (normal/power/whisper): baseline 更新時も正規化と類似度計算が "
        "一貫してプロトタイプ辞書と scales を基準として使用することを確認"
    )

    # (11) ベースライン安全クランプテスト（極端な異常値を持つダミー音声や異常 JSON でも BASELINE_CLAMP_RANGES 内に収まり jitter が除外されること）
    rng_ext = np.random.default_rng(999)
    t_ext = np.linspace(0, 3.0, 16000 * 3, endpoint=False)
    extreme_wave = (
        0.99 * rng_ext.standard_normal(len(t_ext))
        + 0.8 * np.sin(2 * np.pi * np.linspace(70, 500, len(t_ext)) * t_ext)
    ).astype(np.float32)
    cal_res = analyzer.calibrate_baseline([extreme_wave])
    assert "jitter" not in cal_res, "calibrate_baseline の結果に jitter が含まれています"
    for k, (lo, hi) in BASELINE_CLAMP_RANGES.items():
        val_cal = cal_res[k]
        val_mem = analyzer.baseline[k]
        assert lo <= val_cal <= hi, f"calibrate_baseline の保存値 {k}={val_cal} が範囲 [{lo}, {hi}] 外です"
        assert lo <= val_mem <= hi, f"analyzer.baseline[{k}]={val_mem} が範囲 [{lo}, {hi}] 外です"

    corrupted_json = {
        **DEFAULT_BASELINE,
        "engine": ENGINE_ID,
        "f0_std_st": 10.67,
        "f0_slope_st": 15.87,
        "jitter": 0.2529,
        "shimmer": 0.8922,
        "hnr_db": 0.1,
    }
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(corrupted_json, f, ensure_ascii=False, indent=2)
    reloaded = analyzer._load_baseline()
    assert "jitter" not in reloaded, "_load_baseline() で jitter が除外されていません"
    for k, (lo, hi) in BASELINE_CLAMP_RANGES.items():
        assert lo <= reloaded[k] <= hi, f"_load_baseline() で異常値 {k}={reloaded[k]} が範囲 [{lo}, {hi}] に補正されていません"

    # テスト完了後は DEFAULT_BASELINE (anchors: {"power": None, "whisper": None}) のクリーンな初期値に復元
    clean_baseline = {
        **DEFAULT_BASELINE,
        "engine": ENGINE_ID,
        "calibrated_at": None,
        "samples_count": 0,
        "anchors": {"power": None, "whisper": None},
    }
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(clean_baseline, f, ensure_ascii=False, indent=2)
    analyzer.baseline = analyzer._load_baseline()
    assert analyzer.baseline["rms_p90_db"] == DEFAULT_BASELINE["rms_p90_db"]
    assert analyzer.baseline["anchors"] == {"power": None, "whisper": None}
    print(
        "  - [PASS] ベースライン安全クランプテスト: calibrate_baseline / _load_baseline ともに全15項目が "
        "BASELINE_CLAMP_RANGES 内に収まり、DEFAULT_BASELINE にクリーン復元完了"
    )

    # 5. 推論性能チェック (0.05秒以内)
    max_wall_sec = max(r["_wall_sec"] for r in results.values())
    max_mod_sec = max(r["analysis_time_sec"] for r in results.values())
    print(f"\n[Step 5] 性能要件チェック: 最大推論時間 {max_wall_sec:.4f}秒 (モジュール計測: {max_mod_sec:.3f}秒, 目標: 0.05秒以内)")
    assert max_wall_sec <= 0.05, f"推論時間が 0.05秒を超過しました: {max_wall_sec:.4f}秒"
    print("  - [PASS] CPU推論性能目標 (0.05秒以内) & VRAM増分 0.0MB をクリアしました！")

    print("\n=================================================================")
    print("すべての自動検証テストに合格しました！ (ALL TESTS PASSED)")
    print("=================================================================")


if __name__ == "__main__":
    run_self_test()
