"""
voice_emo_analyzer.py
商用利用可能な音響物理特徴エンジン（librosa [ISC] + scipy / numpy [BSD] のみ）による
「7音響特徴 → 2階層感情モデル（基本6表情 ＋ 声質ニュアンス修飾2種） → Animagine XL 表情プロンプト合成」コアモジュール

StoryWeaver Live 統合用（emotion_mode = "detailed_12"）
- 2026-10-26 商用化改修: 非商用の audeering/wav2vec2-msp-dim (CC-BY-NC-SA) と
  openSMILE (Research License) を完全に排除。torch / transformers 非依存。
- 2026-11-01 2階層方式（案A）改修:
  - 第1階層: 基本表情 6種（joy, burning, sorrow, surprise_fear, confident, serene）から排他選択
  - 第2階層: 声質ニュアンス修飾 2種（sultry_modifier, bashful_modifier）を乗算ゲート＋閾値60pt以上で条件発動
  - 熱量スケーリング: 主感情重み w1 を Arousal に連動
  - 無音ガード (_is_silent=1.0 → serene 固定 w1=0.85)、語尾スロープ相対比較化、Arousal/Valence 再定義
- CPU のみで動作し VRAM 増分 0MB
- FaceDetailer 案B (Node 5: Base用 / Node 32: FD表情専用) に適合
- 公開 IF（get_voice_emo_analyzer / warmup / baseline / calibrate_baseline / analyze）は従来互換
"""

import io
import json
import logging
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import median_filter

if not hasattr(np, "math"):
    np.math = math  # type: ignore[attr-defined]

log = logging.getLogger("storyweaver.voice_emo")
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "voice_emo_config.json"
BASELINE_PATH = BASE_DIR / "voice_emo_baseline.json"
PROTOTYPES_PATH = BASE_DIR / "storyweaver_emotion_prototypes.json"

ENGINE_ID = "librosa_v1"
TARGET_SR = 16000
FRAME_LEN = 1024  # 64ms
HOP_LEN = 320  # 20ms
FMIN, FMAX = 70.0, 500.0

# 15次元音響特徴キー（jitter を完全除外）
PROTO_FEATURE_KEYS: Tuple[str, ...] = (
    "rms_p90_db",
    "peak_db",
    "centroid_hz",
    "rolloff_hz",
    "flatness",
    "onset_rate",
    "low_band_ratio",
    "f0_median_hz",
    "f0_std_st",
    "f0_iqr_st",
    "f0_delta_st",
    "f0_slope_st",
    "hnr_db",
    "breath_ratio",
    "shimmer",
)

# 生特徴量の既定基準値（storyweaver_emotion_prototypes.json 準拠・jitter 除外）
DEFAULT_BASELINE: Dict[str, float] = {
    "rms_p90_db": -33.99,
    "peak_db": -15.53,
    "centroid_hz": 1328.0,
    "rolloff_hz": 3063.0,
    "flatness": 0.0088,
    "onset_rate": 3.66,
    "low_band_ratio": 0.478,
    "f0_median_hz": 86.2,
    "f0_std_st": 2.78,
    "f0_iqr_st": 4.17,
    "f0_delta_st": 0.537,
    "f0_slope_st": -0.3,
    "hnr_db": 2.4,
    "breath_ratio": 0.0085,
    "shimmer": 0.0,
    "duration_sec": 3.5,
}
DEFAULT_SCALES: Dict[str, float] = {
    "rms_p90_db": 8.0,
    "peak_db": 6.0,
    "centroid_hz": 400.0,
    "rolloff_hz": 1200.0,
    "flatness": 0.01,
    "onset_rate": 2.5,
    "low_band_ratio": 0.12,
    "f0_median_hz": 3.0,
    "pitch_rel_st": 3.0,
    "f0_std_st": 0.8,
    "f0_iqr_st": 1.0,
    "f0_delta_st": 0.05,
    "f0_slope_st": 2.0,
    "hnr_db": 4.0,
    "breath_ratio": 0.3,
    "shimmer": 0.01,
}

# ベースラインキャリブレーションおよび読み込み時の異常値防止クランプ範囲（jitter 除外）
BASELINE_CLAMP_RANGES: Dict[str, Tuple[float, float]] = {
    "rms_p90_db": (-50.0, -1.0),
    "peak_db": (-40.0, 0.0),
    "centroid_hz": (300.0, 5000.0),
    "rolloff_hz": (500.0, 8000.0),
    "flatness": (0.00001, 0.50),
    "onset_rate": (0.5, 12.0),
    "low_band_ratio": (0.05, 0.98),
    "f0_delta_st": (0.0, 3.0),
    "f0_std_st": (0.1, 6.0),
    "f0_iqr_st": (0.1, 8.0),
    "f0_median_hz": (65.0, 400.0),
    "f0_slope_st": (-8.0, 8.0),
    "hnr_db": (0.5, 30.0),
    "breath_ratio": (0.0001, 0.60),
    "shimmer": (0.0, 0.50),
}

# SenseVoice 感情タグ → Valence 補助バイアス（点）
SENSE_VALENCE_BIAS: Dict[str, float] = {
    "HAPPY": 25.0,
    "SURPRISED": 5.0,
    "NEUTRAL": 0.0,
    "SAD": -25.0,
    "ANGRY": -20.0,
    "FEARFUL": -15.0,
    "DISGUSTED": -20.0,
}

# SenseVoice 感情タグ → 最終プロトタイプ感情スコアへの軽微なボーナス（+5.0点）
SENSE_EMOTION_BONUS: Dict[str, Tuple[str, float]] = {
    "HAPPY": ("joy", 5.0),
    "ANGRY": ("burning", 5.0),
    "SAD": ("sorrow", 5.0),
    "SURPRISED": ("surprise_fear", 5.0),
    "FEARFUL": ("surprise_fear", 5.0),
    "DISGUSTED": ("burning", 5.0),
}

# 2階層感情モデル定義キー
PRIMARY_EMOTION_KEYS: Tuple[str, ...] = (
    "joy",
    "burning",
    "sorrow",
    "surprise_fear",
    "confident",
    "serene",
)
MODIFIER_EMOTION_KEYS: Tuple[str, ...] = (
    "sultry_modifier",
    "bashful_modifier",
)
NONE_MODIFIER_DEF: Dict[str, Any] = {
    "id": "none_modifier",
    "name_ja": "ストレート表現（修飾なし）",
    "icon": "➖",
    "tier": "modifier",
    "description": "ニュアンス修飾なし（基本表情のみをストレートに出力）",
    "face_tags": "",
    "lighting_tags": "",
}
MODIFIER_THRESHOLD: float = 60.0


class VoiceEmoAnalyzer:
    """音声感情・音響特徴量アナライザー（librosa / scipy / numpy のみ・15次元プロトタイプ類似度＆2階層方式）"""

    def __init__(
        self,
        config_path: Union[str, Path] = CONFIG_PATH,
        baseline_path: Union[str, Path] = BASELINE_PATH,
        prototypes_path: Union[str, Path] = PROTOTYPES_PATH,
        device: str = "cpu",
    ):
        self.config_path = Path(config_path)
        self.baseline_path = Path(baseline_path)
        self.prototypes_path = Path(prototypes_path)
        self.device = "cpu"  # 互換用（常に CPU）
        self.config = self._load_json(self.config_path)

        # プロトタイプ辞書関連の初期化
        self._proto_mtime: Optional[float] = None
        self.model_config: Dict[str, Any] = {}
        self.alpha: float = 0.35
        self.clip_z_range: Tuple[float, float] = (-3.0, 3.0)
        self.proto_baseline: Dict[str, float] = {
            k: v for k, v in DEFAULT_BASELINE.items() if k in PROTO_FEATURE_KEYS
        }
        self.proto_scales: Dict[str, float] = {
            k: v for k, v in DEFAULT_SCALES.items() if k in PROTO_FEATURE_KEYS
        }
        self.feature_weights: Dict[str, float] = {k: 1.0 for k in PROTO_FEATURE_KEYS}
        self.prototypes: Dict[str, Any] = {}

        self._load_prototypes(force=True)
        self.scales = {
            k: v
            for k, v in {**DEFAULT_SCALES, **self.config.get("scales", {}), **self.proto_scales}.items()
            if k != "jitter"
        }
        self.default_baseline = {
            k: v
            for k, v in {**DEFAULT_BASELINE, **self.config.get("default_baseline", {}), **self.proto_baseline}.items()
            if k != "jitter"
        }
        self.baseline = self._load_baseline()
        self.is_loaded = False

    # ------------------------------------------------------------------ IO
    def _load_json(self, path: Path) -> dict:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_prototypes(self, force: bool = False) -> None:
        """storyweaver_emotion_prototypes.json を読み込み、baseline/scales/prototypes/model_config を適用（jitter除外）"""
        if not self.prototypes_path.is_file():
            return
        try:
            mtime = self.prototypes_path.stat().st_mtime
            if not force and self._proto_mtime is not None and mtime == self._proto_mtime:
                return
            data = self._load_json(self.prototypes_path)
            if not data:
                return
            self._proto_mtime = mtime
            self.model_config = dict(data.get("model_config") or {})
            self.alpha = float(self.model_config.get("alpha", 0.35))
            clip_rng = self.model_config.get("clip_z_range", [-3.0, 3.0])
            if isinstance(clip_rng, (list, tuple)) and len(clip_rng) >= 2:
                self.clip_z_range = (float(clip_rng[0]), float(clip_rng[1]))

            in_base = data.get("baseline") or {}
            if isinstance(in_base, dict):
                for k in PROTO_FEATURE_KEYS:
                    if k in in_base and isinstance(in_base[k], (int, float)):
                        self.proto_baseline[k] = float(in_base[k])

            in_scales = data.get("scales") or {}
            if isinstance(in_scales, dict):
                for k in PROTO_FEATURE_KEYS:
                    if k in in_scales and isinstance(in_scales[k], (int, float)):
                        self.proto_scales[k] = float(in_scales[k])
                if "f0_median_hz" in self.proto_scales:
                    self.proto_scales["pitch_rel_st"] = self.proto_scales["f0_median_hz"]

            in_weights = data.get("feature_weights") or {}
            if isinstance(in_weights, dict):
                self.feature_weights = {
                    k: float(in_weights.get(k, 1.0))
                    for k in PROTO_FEATURE_KEYS
                    if float(in_weights.get(k, 1.0)) > 0.0
                }

            in_protos = data.get("prototypes") or {}
            if isinstance(in_protos, dict):
                cleaned_protos: Dict[str, Any] = {}
                for emo_key, pinfo in in_protos.items():
                    if not isinstance(pinfo, dict):
                        continue
                    cz_in = pinfo.get("centroid_z") or {}
                    cz_clean = {
                        k: float(v)
                        for k, v in cz_in.items()
                        if k in PROTO_FEATURE_KEYS and isinstance(v, (int, float))
                    }
                    cleaned_protos[emo_key] = {**pinfo, "centroid_z": cz_clean}
                self.prototypes = cleaned_protos
        except Exception as e:
            log.warning("プロトタイプ辞書読み込み失敗 (%s): %s", self.prototypes_path.name, e)

    def _clamp_baseline_dict(self, base: Dict[str, Any]) -> Dict[str, Any]:
        """BASELINE_CLAMP_RANGES に基づきベースライン値を妥当範囲にクランプ（jitter は除外）"""
        clamped = {k: v for k, v in base.items() if k != "jitter"}
        for k, (lo, hi) in BASELINE_CLAMP_RANGES.items():
            if k in clamped and isinstance(clamped[k], (int, float)):
                clamped[k] = round(float(np.clip(clamped[k], lo, hi)), 4)
        return clamped

    def _load_baseline(self) -> dict:
        base: Dict[str, Any] = dict(self.default_baseline)
        base["engine"] = ENGINE_ID
        base["calibrated_at"] = None
        base["samples_count"] = 0
        base["anchors"] = {"power": None, "whisper": None}
        if self.baseline_path.is_file():
            try:
                with open(self.baseline_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("engine") == ENGINE_ID:
                    base.update(
                        {k: v for k, v in data.items() if k in self.default_baseline and k != "jitter"}
                    )
                    base["calibrated_at"] = data.get("calibrated_at")
                    base["samples_count"] = int(data.get("samples_count", 0) or 0)
                    anchors_in = data.get("anchors")
                    if isinstance(anchors_in, dict):
                        for ak in ("power", "whisper"):
                            av = anchors_in.get(ak)
                            if isinstance(av, dict):
                                base["anchors"][ak] = self._clamp_baseline_dict(av)
                            else:
                                base["anchors"][ak] = None
                else:
                    log.warning("旧エンジンのベースラインを検出。既定値を使用します（要再キャリブレーション）")
            except Exception as e:
                log.warning("ベースライン読み込み失敗、デフォルト値を使用: %s", e)
        return self._clamp_baseline_dict(base)

    def load_model(self) -> None:
        """互換用。外部モデルのロードは不要。"""
        self.is_loaded = True

    def warmup(self) -> None:
        """librosa 関数群（numba JIT 含む）の初回コンパイル"""
        self.load_model()
        t = np.arange(TARGET_SR * 2) / TARGET_SR
        dummy = (0.3 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
        dummy += 0.01 * np.random.default_rng(0).standard_normal(dummy.shape).astype(np.float32)
        _ = self.analyze_signal(dummy, TARGET_SR)
        log.info("VoiceEmoAnalyzer: ウォームアップ完了 (engine=%s)", ENGINE_ID)

    def _read_audio(self, wav_input: Union[bytes, str, Path, np.ndarray]) -> Tuple[np.ndarray, int]:
        """各種入力を float32 モノラル配列に正規化"""
        if isinstance(wav_input, np.ndarray):
            audio = wav_input.astype(np.float32)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            return audio, TARGET_SR
        if isinstance(wav_input, bytes):
            data, sr = sf.read(io.BytesIO(wav_input), dtype="float32")
        else:
            data, sr = sf.read(Path(wav_input), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data, sr

    # ------------------------------------------------------------ features
    def extract_raw_features(self, audio: np.ndarray, sr: int = TARGET_SR) -> Dict[str, float]:
        """音響物理特徴量の抽出（15項目・jitter除外。無音時は raw['_is_silent'] = 1.0 を記録）"""
        y = np.asarray(audio, dtype=np.float32)
        if sr != TARGET_SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=TARGET_SR)
            sr = TARGET_SR
        duration_sec = len(y) / sr if sr else 0.0
        raw = {k: v for k, v in self.default_baseline.items() if k != "jitter"}
        raw["duration_sec"] = duration_sec
        raw["_is_silent"] = 0.0
        if len(y) < FRAME_LEN * 2 or float(np.max(np.abs(y))) < 1e-5:
            raw["_is_silent"] = 1.0
            return raw  # 無音・極短 → 基準値（_is_silent=1.0）

        eps = 1e-10
        y_pad = np.pad(y, FRAME_LEN // 2, mode="reflect")
        frames = librosa.util.frame(y_pad, frame_length=FRAME_LEN, hop_length=HOP_LEN)  # (L, T)
        n_frames = frames.shape[1]

        # --- 声量（20ms フレーム RMS → 無音除外）
        rms = np.sqrt(np.mean(frames ** 2, axis=0) + eps)
        rms_db = 20 * np.log10(rms + eps)
        active = (rms_db > rms_db.max() - 35.0) & (rms_db > -55.0)
        if active.sum() < 3:
            raw["_is_silent"] = 1.0
            return raw
        raw["rms_p90_db"] = float(np.percentile(rms_db[active], 90))
        raw["peak_db"] = float(20 * np.log10(np.max(np.abs(y)) + eps))

        # --- スペクトル系
        win = np.hanning(FRAME_LEN).astype(np.float32)[:, None]
        spec = np.abs(np.fft.rfft(frames * win, axis=0)) ** 2  # (F, T)
        freqs = np.fft.rfftfreq(FRAME_LEN, 1.0 / sr)
        S = np.sqrt(spec)
        cent = librosa.feature.spectral_centroid(S=S, sr=sr, n_fft=FRAME_LEN)[0]
        roll = librosa.feature.spectral_rolloff(S=S, sr=sr, n_fft=FRAME_LEN, roll_percent=0.85)[0]
        flat = librosa.feature.spectral_flatness(S=S)[0]
        raw["centroid_hz"] = float(np.median(cent[active]))
        raw["rolloff_hz"] = float(np.median(roll[active]))
        raw["flatness"] = float(np.median(flat[active]))
        total_e = spec.sum(axis=0) + eps
        low_e = spec[(freqs >= 100) & (freqs < 500)].sum(axis=0)
        high_e = spec[(freqs >= 2500) & (freqs <= 8000)].sum(axis=0)
        raw["low_band_ratio"] = float(np.mean(low_e[active] / total_e[active]))

        # --- オンセット密度（発話の勢い）
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LEN)
        onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=HOP_LEN)
        active_sec = max(active.sum() * HOP_LEN / sr, 0.2)
        raw["onset_rate"] = float(len(onsets) / active_sec)

        # --- 自己相関による周期性（HNR）と有声フレーム厳格判定
        ac = np.fft.irfft(spec, n=FRAME_LEN * 2, axis=0)[:FRAME_LEN]
        ac0 = ac[0] + eps
        lag_min, lag_max = int(sr / FMAX), int(sr / FMIN)
        r_max = np.clip(ac[lag_min:lag_max].max(axis=0) / ac0, 1e-4, 0.9999)
        voiced = active & (r_max > 0.55) & (rms_db > np.percentile(rms_db[active], 25))
        if voiced.sum() < 3:
            voiced = active & (r_max >= np.percentile(r_max[active], 50))
        hnr = 10 * np.log10(r_max / (1 - r_max))
        raw["hnr_db"] = float(np.median(hnr[voiced]))
        aper = 1.0 - r_max
        raw["breath_ratio"] = float(np.mean((high_e[voiced] / total_e[voiced]) * (0.5 + aper[voiced])))

        # --- F0（YIN）とオクターブジャンプ除去
        f0 = librosa.yin(y, fmin=FMIN, fmax=FMAX, sr=sr, frame_length=FRAME_LEN, hop_length=HOP_LEN)
        m = min(len(f0), n_frames)
        f0, v = f0[:m], voiced[:m]
        f0v = f0[v]
        if len(f0v) >= 3:
            f0_med = float(np.median(f0v))
            v_clean = v & (np.abs(12 * np.log2(f0 / (f0_med + eps))) <= 6.0)
            v_use = v_clean if v_clean.sum() >= 3 else v
            f0_use = f0[v_use]
            st = 12 * np.log2(f0_use / 100.0)
            raw["f0_median_hz"] = float(np.median(f0_use))
            raw["f0_std_st"] = float(np.std(st))
            q75, q25 = np.percentile(st, [75, 25])
            raw["f0_iqr_st"] = float(q75 - q25)
            # 移動中央値フィルタ（窓幅5）によるイントネーションと微細揺らぎ（f0_delta_st / Shimmer）の分離
            if len(f0_use) >= 5:
                f0_smooth = median_filter(f0_use, size=5, mode="nearest")
            else:
                f0_smooth = np.full_like(f0_use, float(np.median(f0_use)))
            raw["f0_delta_st"] = float(np.median(np.abs(12 * np.log2((f0_use + eps) / (f0_smooth + eps)))))

            rms_v = rms[:m][v_use]
            if len(rms_v) >= 5:
                rms_smooth = median_filter(rms_v, size=5, mode="nearest")
            else:
                rms_smooth = np.full_like(rms_v, float(np.median(rms_v)))
            raw["shimmer"] = float(np.median(np.abs(rms_v - rms_smooth) / (rms_smooth + eps)))

            # 語尾スロープ（後半 40% の有声フレーム, semitone/sec, -10.0〜+10.0 にクリップ）
            idx = np.where(v_use)[0]
            tail = idx[int(len(idx) * 0.6):]
            if len(tail) >= 3:
                t_sec = tail * HOP_LEN / sr
                st_tail = 12 * np.log2(f0[tail] / 100.0)
                slope = float(np.polyfit(t_sec, st_tail, 1)[0])
                raw["f0_slope_st"] = float(np.clip(slope, -10.0, 10.0))

        for k, val in raw.items():
            if val is None or math.isnan(val) or math.isinf(val):
                raw[k] = self.default_baseline.get(k, 0.0)
        return raw

    def compute_z_vector(
        self,
        raw: Dict[str, Any],
        baseline: Optional[Dict[str, float]] = None,
        scales: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        測定済みの棒読みベースライン（self.baseline）またはプロトタイプ辞書の baseline と scales を基準として
        jitter を除く 15 項目の正規化ベクトル z（clip_z_range にクリップ）を算出する。
        """
        self._load_prototypes()
        b = baseline if baseline is not None else (self.baseline if self.baseline else self.proto_baseline)
        sc = scales if scales is not None else self.proto_scales
        clip_lo, clip_hi = self.clip_z_range
        z_vec: Dict[str, float] = {}
        for k in PROTO_FEATURE_KEYS:
            b_val = float(b.get(k, self.baseline.get(k, self.proto_baseline.get(k, DEFAULT_BASELINE.get(k, 0.0)))))
            sc_val = float(sc.get(k, self.proto_scales.get(k, DEFAULT_SCALES.get(k, 1.0))) or 1.0)
            x_val = float(raw.get(k, b_val))
            if k == "f0_median_hz":
                z_raw = (12.0 * math.log2(max(x_val, 1e-6) / max(b_val, 1e-6))) / sc_val
            elif k == "breath_ratio":
                z_raw = math.log10(max(x_val, 1e-6) / max(b_val, 1e-6)) / sc_val
            else:
                z_raw = (x_val - b_val) / sc_val
            if math.isnan(z_raw) or math.isinf(z_raw):
                z_raw = 0.0
            z_vec[k] = float(np.clip(z_raw, clip_lo, clip_hi))
        return z_vec

    def _s(self, raw: Dict[str, float], key: str, base: Dict[str, float], positive: bool = True,
           scale_key: Optional[str] = None, value: Optional[float] = None) -> float:
        """棒読みベースライン基準値=50点、基準±scale で 0/100 点に正規化"""
        sc = float(self.proto_scales.get(scale_key or key, self.scales.get(scale_key or key, 1.0)) or 1.0)
        if value is not None:
            z_val = float(value) / sc
        else:
            x = float(raw.get(key, 0.0))
            b_val = float(
                base.get(
                    key,
                    self.baseline.get(
                        key, self.proto_baseline.get(key, self.default_baseline.get(key, 0.0))
                    ),
                )
            )
            if key == "f0_median_hz":
                z_val = (12.0 * math.log2(max(x, 1e-6) / max(b_val, 1e-6))) / sc
            elif key == "breath_ratio":
                z_val = math.log10(max(x, 1e-6) / max(b_val, 1e-6)) / sc
            else:
                z_val = (x - b_val) / sc

        signed_z = z_val if positive else -z_val
        s = 50.0 + signed_z * 50.0
        return 50.0 if (math.isnan(s) or math.isinf(s)) else float(np.clip(s, 0.0, 100.0))

    def normalize_7_features(
        self, raw: Dict[str, float], baseline: Optional[Dict[str, float]] = None,
        sense_emotion: Optional[str] = None,
    ) -> Dict[str, Any]:
        """音響特徴を 0〜100 点に正規化（jitter を除外、測定済み棒読みベースライン self.baseline を最優先で使用）"""
        self._load_prototypes()
        b = baseline if baseline is not None else (self.baseline if self.baseline else self.proto_baseline)
        s = lambda k, pos=True: self._s(raw, k, b, pos)  # noqa: E731

        arousal = 0.40 * s("rms_p90_db") + 0.20 * s("centroid_hz") + 0.20 * s("onset_rate") + 0.20 * s("f0_std_st")
        dominance = 0.35 * s("rms_p90_db") + 0.25 * s("low_band_ratio") + 0.20 * s("hnr_db") + 0.20 * s("f0_delta_st", False)
        valence = 0.35 * s("rolloff_hz") + 0.30 * s("centroid_hz") + 0.20 * s("hnr_db") + 0.15 * s("flatness", False)
        emo_tag = str(sense_emotion).upper().strip() if sense_emotion else ""
        if emo_tag:
            valence += SENSE_VALENCE_BIAS.get(emo_tag, 0.0)
        valence = float(np.clip(valence, 0.0, 100.0))

        breathiness = 0.5 * s("hnr_db", False) + 0.5 * s("breath_ratio")
        shimmer = s("shimmer")
        rel_st = 12 * math.log2(max(raw.get("f0_median_hz", 86.2), 1.0) / max(b.get("f0_median_hz", 86.2), 1.0))
        pitch_level = self._s(raw, "", b, True, scale_key="f0_median_hz", value=rel_st)
        # 語尾ピッチスロープをベースラインとの相対比較で算出
        contour = self._s(raw, "f0_slope_st", b, True, scale_key="f0_slope_st")
        pitch = 0.6 * pitch_level + 0.4 * contour

        # プロトタイプ類似度計算用の 15次元正規化ベクトル z（測定済み baseline 基準）
        z_vec = self.compute_z_vector(raw, baseline=b)

        clip = lambda v: round(float(np.clip(v, 0.0, 100.0)), 1)  # noqa: E731
        return {
            "arousal": clip(arousal),
            "dominance": clip(dominance),
            "valence": clip(valence),
            "breathiness": clip(breathiness),
            "shimmer": clip(shimmer),
            "pitch": clip(pitch),
            # 内訳（UI 非表示・感情計算用）
            "_pitch_level": clip(pitch_level),
            "_contour": clip(contour),
            "_is_silent": float(raw.get("_is_silent", 0.0)),
            "_sense_emotion": emo_tag,
            "_z": z_vec,
            "_raw": {k: float(v) for k, v in raw.items() if k != "jitter" and isinstance(v, (int, float))},
        }

    def compute_baseline_deltas(
        self, raw: Dict[str, float], baseline: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """棒読みベースライン（self.baseline）に対する物理音響特徴の相対変化量（Δ）を算出する"""
        b = baseline if baseline is not None else (self.baseline if self.baseline else self.default_baseline)

        def _r(k: str) -> float:
            return float(raw.get(k, self.default_baseline.get(k, 0.0)))

        def _b(k: str) -> float:
            return float(b.get(k, self.baseline.get(k, self.default_baseline.get(k, 0.0))))

        rms_raw, rms_base = _r("rms_p90_db"), _b("rms_p90_db")
        peak_raw, peak_base = _r("peak_db"), _b("peak_db")
        f0_raw, f0_base = _r("f0_median_hz"), _b("f0_median_hz")
        f0_std_raw, f0_std_base = _r("f0_std_st"), _b("f0_std_st")
        f0_slope_raw = _r("f0_slope_st")
        cent_raw, cent_base = _r("centroid_hz"), _b("centroid_hz")
        hnr_raw, hnr_base = _r("hnr_db"), _b("hnr_db")
        breath_raw, breath_base = _r("breath_ratio"), _b("breath_ratio")
        shimmer_raw = _r("shimmer")
        onset_raw = _r("onset_rate")

        delta_pitch_st = 12.0 * math.log2(max(f0_raw, 1e-6) / max(f0_base, 1e-6))

        deltas: Dict[str, Any] = {
            "delta_rms_db": round(rms_raw - rms_base, 2),
            "delta_peak_db": round(peak_raw - peak_base, 2),
            "delta_pitch_st": round(delta_pitch_st, 2),
            "f0_std_st": round(f0_std_raw, 2),
            "delta_f0_std_st": round(f0_std_raw - f0_std_base, 2),
            "f0_slope_st": round(f0_slope_raw, 2),
            "delta_centroid_hz": round(cent_raw - cent_base, 2),
            "hnr_db": round(hnr_raw, 2),
            "delta_hnr_db": round(hnr_raw - hnr_base, 2),
            "breath_ratio": round(float(breath_raw), 4),
            "breath_ratio_Multiple": round(float(breath_raw) / max(float(breath_base), 1e-4), 2),
            "breath_ratio_fold": round(float(breath_raw) / max(float(breath_base), 1e-4), 2),
            "shimmer": round(float(shimmer_raw), 4),
            "onset_rate": round(onset_raw, 2),
            "is_calibrated": bool(int(self.baseline.get("samples_count", 0) or 0) > 0),
            "is_silent": bool(float(raw.get("_is_silent", 0.0)) >= 0.5),
        }
        deltas["prompt_summary_ja"] = self.format_deltas_for_prompt(deltas)
        return deltas

    def format_deltas_for_prompt(
        self, deltas: Dict[str, Any], features_7: Optional[Dict[str, float]] = None
    ) -> str:
        """compute_baseline_deltas() の結果を LLM 向けの日本語物理音響サマリーテキスト（箇条書き）に整形する（客観的差分数値のみを提示）"""
        if deltas.get("is_silent", False):
            return "- 音声状態: 無音または極小音量（発話なし）"

        calib_str = "測定済み個人基準（棒読みキャリブレーション済）" if deltas.get("is_calibrated") else "既定基準（未キャリブレーション）"
        d_rms = float(deltas.get("delta_rms_db", 0.0))
        d_pitch = float(deltas.get("delta_pitch_st", 0.0))
        f0_std = float(deltas.get("f0_std_st", 0.0))
        d_f0_std = float(deltas.get("delta_f0_std_st", 0.0))
        slope = float(deltas.get("f0_slope_st", 0.0))
        d_cent = float(deltas.get("delta_centroid_hz", 0.0))
        hnr = float(deltas.get("hnr_db", 0.0))
        d_hnr = float(deltas.get("delta_hnr_db", 0.0))
        breath_mult = float(deltas.get("breath_ratio_Multiple", 1.0))
        shimmer = float(deltas.get("shimmer", 0.0))
        onset = float(deltas.get("onset_rate", 0.0))

        lines = [
            f"- 比較基準: {calib_str}",
            f"- 声量変化 (ΔRMS): {d_rms:+.2f} dB / ピーク差 (ΔPeak): {float(deltas.get('delta_peak_db', 0.0)):+.2f} dB",
            f"- ピッチ変化 (ΔPitch): {d_pitch:+.2f} 半音（平常基準との高低差）",
            f"- 抑揚の広がり (F0 SD): {f0_std:.2f} 半音 (平常差 {d_f0_std:+.2f} 半音)",
            f"- 語尾ピッチスロープ: {slope:+.2f} 半音/秒（正=語尾上がり, 負=語尾下がり）",
            f"- 声のスペクトル重心変化 (ΔCentroid): {d_cent:+.1f} Hz",
            f"- 声の周期性と息成分: HNR {hnr:.2f} dB (平常差 {d_hnr:+.2f} dB), 息成分倍率 {breath_mult:.2f}倍",
            f"- 声の微細な揺らぎ (Shimmer): {shimmer:.4f}",
            f"- 発話アタック密度 (Onset): {onset:.2f} 回/秒",
        ]
        if features_7:
            lines.append(
                f"- 総合指標参考値 (0-100): 熱量(Arousal)={features_7.get('arousal', 50.0)}, "
                f"力強さ(Dominance)={features_7.get('dominance', 50.0)}, "
                f"明るさ(Valence)={features_7.get('valence', 50.0)}, "
                f"吐息感(Breathiness)={features_7.get('breathiness', 50.0)}"
            )
        return "\n".join(lines)

    def compute_12_emotions(
        self, f7: Dict[str, Any], sense_emotion: Optional[str] = None
    ) -> Dict[str, float]:
        """
        storyweaver_emotion_prototypes.json に基づく完全プロトタイプ類似度方式（Gaussian Similarity）による感情スコア算出:
        - 入力音声の正規化ベクトル z（jitter を除く15項目）と各感情の重心ベクトル proto[e]["centroid_z"] との
          重み付きユークリッド距離 dist_sq = sum(w[k] * (z[k] - proto[k])^2) / sum(w[k]) を計算
        - 公式: score = 100.0 * np.math.exp(-alpha * dist_sq)
        - SenseVoice 感情タグバイアス（SENSE_VALENCE_BIAS）が渡された場合は対応感情に +5.0 点ボーナスを加算し 0〜100 にクリップ
        """
        self._load_prototypes()
        if float(f7.get("_is_silent", 0.0)) >= 0.5:
            # 無音ガード時は serene が確実に1位、ニュアンス修飾は未発動となる安全スコアを返却
            return {
                "joy": 50.0,
                "burning": 50.0,
                "sorrow": 50.0,
                "surprise_fear": 50.0,
                "confident": 50.0,
                "serene": 52.0,
                "sultry_modifier": 17.5,
                "bashful_modifier": 20.0,
            }

        # 入力から15次元正規化ベクトル z（jitter除外）を取得または算出
        clip_lo, clip_hi = self.clip_z_range
        if isinstance(f7.get("_z"), dict):
            z: Dict[str, float] = {
                k: float(np.clip(float(v), clip_lo, clip_hi))
                for k, v in f7["_z"].items()
                if k in PROTO_FEATURE_KEYS
            }
        elif isinstance(f7.get("_raw"), dict):
            z = self.compute_z_vector(f7["_raw"])
        else:
            # 生特徴量辞書または z ベクトル辞書が直接渡された場合の自動判別
            is_raw_dict = (
                float(f7.get("centroid_hz", 0.0) or 0.0) > 20.0
                or float(f7.get("f0_median_hz", 0.0) or 0.0) > 20.0
                or float(f7.get("rms_p90_db", 0.0) or 0.0) < -5.0
            )
            if is_raw_dict:
                z = self.compute_z_vector(f7)
            else:
                z = {
                    k: float(np.clip(float(f7.get(k, 0.0)), clip_lo, clip_hi))
                    for k in PROTO_FEATURE_KEYS
                    if k in f7
                }

        all_emotion_keys = (*PRIMARY_EMOTION_KEYS, *MODIFIER_EMOTION_KEYS)
        raw_scores: Dict[str, float] = {}
        for emo_key in all_emotion_keys:
            proto_entry = self.prototypes.get(emo_key, {})
            proto_z = proto_entry.get("centroid_z", {}) if isinstance(proto_entry, dict) else {}
            valid_keys = [
                k
                for k in PROTO_FEATURE_KEYS
                if k in proto_z and k in z and float(self.feature_weights.get(k, 1.0)) > 0.0
            ]
            if valid_keys:
                w_sum = sum(float(self.feature_weights.get(k, 1.0)) for k in valid_keys)
                dist_sq = (
                    sum(
                        float(self.feature_weights.get(k, 1.0)) * ((z[k] - float(proto_z[k])) ** 2)
                        for k in valid_keys
                    )
                    / w_sum
                )
                score = 100.0 * np.math.exp(-self.alpha * dist_sq)
            else:
                score = 0.0
            raw_scores[emo_key] = float(score)

        # SenseVoice 感情タグバイアス（SENSE_VALENCE_BIAS）が渡された場合、対応感情に軽微なボーナス（+5.0点）を加算
        emo_tag = str(sense_emotion or f7.get("_sense_emotion", "")).upper().strip()
        if emo_tag and emo_tag in SENSE_VALENCE_BIAS and emo_tag in SENSE_EMOTION_BONUS:
            target_emo, bonus = SENSE_EMOTION_BONUS[emo_tag]
            if target_emo in raw_scores:
                raw_scores[target_emo] += float(bonus)

        return {k: round(float(np.clip(v, 0.0, 100.0)), 1) for k, v in raw_scores.items()}

    def generate_prompts(
        self,
        emotions: Dict[str, float],
        arousal: float = 50.0,
        is_silent: bool = False,
    ) -> Tuple[str, str, Dict[str, Any], Dict[str, Any]]:
        """
        2階層方式によるプロンプト生成:
        - primary_emotion: 基本6感情の中で最もスコアが高い1つを選出（相反する基本表情の同時ブレンドを防止）
        - 主感情の重み w1: Arousal に連動して w1 = round(min(1.20, max(0.85, 0.85 + (arousal / 100.0) * 0.35)), 2)
          （無音ガード時は serene 固定・w1 = 0.85）
        - secondary_emotion: ニュアンス修飾（sultry_modifier, bashful_modifier）のうち高い方が 60.0 点以上の場合のみ発動し、
          w2 = round(min(0.95, max(0.65, 0.65 + ((mod_score - 60.0) / 40.0) * 0.30)), 2) でブレンド。
          60.0 点未満（未発動）時は none_modifier を返却し、Base/FD ともに主感情タグのみを出力。
        """
        emotions_def = self.config.get("emotions", {})

        def _d(k: str, s: float, info: Dict[str, Any], w: float, f: str, l: str) -> Dict[str, Any]:
            return {
                "id": k,
                "name_ja": info.get("name_ja", k),
                "score": round(float(s), 1),
                "icon": info.get("icon", "✨"),
                "weight": round(float(w), 2),
                "face_tags": f,
                "lighting_tags": l,
            }

        # 無音・極小音声ガード時: 常に基本感情 serene・ニュアンス修飾なし・重み 0.85
        if is_silent:
            k1 = "serene"
            s1 = float(emotions.get("serene", 52.0))
            w1 = 0.85
            e1 = emotions_def.get(k1, {})
            f1, l1 = e1.get("face_tags", ""), e1.get("lighting_tags", "")
            base_parts = [f"({t}:{w1})" for t in (f1, l1) if t]
            fd_parts = [f"({f1}:{w1})"] if f1 else []
            top1 = _d(k1, s1, e1, w1, f1, l1)
            top2 = _d("none_modifier", 0.0, NONE_MODIFIER_DEF, 0.0, "", "")
            return (", ".join(base_parts), ", ".join(fd_parts), top1, top2)

        # 第1階層: 基本6感情の中から最高スコア1つを選出
        primary_candidates = [
            (k, float(emotions.get(k, 0.0))) for k in PRIMARY_EMOTION_KEYS if k in emotions
        ]
        if not primary_candidates:
            primary_candidates = [("serene", 52.0)]
        primary_ranked = sorted(primary_candidates, key=lambda x: x[1], reverse=True)
        k1, s1 = primary_ranked[0]
        w1 = round(min(1.20, max(0.85, 0.85 + (float(arousal) / 100.0) * 0.35)), 2)

        e1 = emotions_def.get(k1, {})
        f1, l1 = e1.get("face_tags", ""), e1.get("lighting_tags", "")

        # 第2階層: ニュアンス修飾2種のうち高い方が 60.0 点以上の場合のみ発動
        mod_candidates = [
            (k, float(emotions.get(k, 0.0))) for k in MODIFIER_EMOTION_KEYS if k in emotions
        ]
        mod_ranked = sorted(mod_candidates, key=lambda x: x[1], reverse=True) if mod_candidates else []

        if mod_ranked and mod_ranked[0][1] >= MODIFIER_THRESHOLD:
            k2, mod_score = mod_ranked[0]
            w2 = round(min(0.95, max(0.65, 0.65 + ((mod_score - 60.0) / 40.0) * 0.30)), 2)
            e2 = emotions_def.get(k2, {})
            f2, l2 = e2.get("face_tags", ""), e2.get("lighting_tags", "")
            base_parts = [f"({t}:{w})" for t, w in [(f1, w1), (l1, w1), (f2, w2), (l2, w2)] if t]
            fd_parts = [f"({t}:{w})" for t, w in [(f1, w1), (f2, w2)] if t]
            top2 = _d(k2, mod_score, e2, w2, f2, l2)
        else:
            base_parts = [f"({t}:{w1})" for t in (f1, l1) if t]
            fd_parts = [f"({f1}:{w1})"] if f1 else []
            top2 = _d("none_modifier", 0.0, NONE_MODIFIER_DEF, 0.0, "", "")

        top1 = _d(k1, s1, e1, w1, f1, l1)
        return (", ".join(base_parts), ", ".join(fd_parts), top1, top2)

    # ------------------------------------------------------------ pipeline
    def analyze_signal(self, audio: np.ndarray, sr: int = TARGET_SR,
                       sense_emotion: Optional[str] = None) -> Dict[str, Any]:
        t0 = time.time()
        raw = self.extract_raw_features(audio, sr)
        is_silent = float(raw.get("_is_silent", 0.0)) >= 0.5
        f7_all = self.normalize_7_features(raw, sense_emotion=sense_emotion)
        e12 = self.compute_12_emotions(f7_all, sense_emotion=sense_emotion)
        prompt_base, prompt_fd, top1, top2 = self.generate_prompts(
            e12, arousal=f7_all["arousal"], is_silent=is_silent
        )
        f7 = {k: v for k, v in f7_all.items() if not k.startswith("_")}
        return {
            "primary_emotion": top1,
            "secondary_emotion": top2,
            "expression_state": top1["id"],
            "expression_prompt": prompt_base,
            "expression_prompt_fd": prompt_fd,
            "raw_features": {k: round(float(v), 4) for k, v in raw.items()},
            "baseline_deltas": self.compute_baseline_deltas(raw),
            "features_7": f7,
            "emotions_12": e12,
            "analysis_time_sec": round(time.time() - t0, 3),
        }

    def analyze(self, wav_input: Union[bytes, str, Path, np.ndarray],
                sense_emotion: Optional[str] = None) -> Dict[str, Any]:
        """WAVバイト列、ファイルパス、または波形配列からの完全解析
        sense_emotion: SenseVoice 感情タグ（HAPPY/SAD/...）を Valence 補助バイアス・感情加算として任意指定"""
        audio, sr = self._read_audio(wav_input)
        return self.analyze_signal(audio, sr, sense_emotion=sense_emotion)

    def calibrate_baseline(
        self,
        wav_inputs: List[Union[bytes, str, Path, np.ndarray]],
        mode: str = "normal",
    ) -> Dict[str, Any]:
        """3点アンカーキャリブレーション（normal: 50点基準＋アンカーリセット / power: 上限アンカー / whisper: 下限・吐息アンカー）"""
        if not wav_inputs:
            raise ValueError("1つ以上の音声サンプルが必要です")
        mode_key = (mode or "normal").strip().lower()
        if mode_key not in ("normal", "power", "whisper"):
            raise ValueError(f"無効なキャリブレーションモードです: {mode}")

        collected: Dict[str, List[float]] = {k: [] for k in DEFAULT_BASELINE}
        for item in wav_inputs:
            audio, sr = self._read_audio(item)
            raw = self.extract_raw_features(audio, sr)
            for k in collected:
                collected[k].append(raw[k])
        raw_means: Dict[str, Any] = {k: round(float(np.mean(v)), 4) for k, v in collected.items()}
        clamped_means: Dict[str, Any] = self._clamp_baseline_dict(raw_means)
        now_iso = datetime.now().isoformat()

        if mode_key == "normal":
            new_baseline: Dict[str, Any] = dict(clamped_means)
            new_baseline["engine"] = ENGINE_ID
            new_baseline["calibrated_at"] = now_iso
            new_baseline["samples_count"] = len(wav_inputs)
            new_baseline["anchors"] = {"power": None, "whisper": None}
        else:
            new_baseline = dict(self._clamp_baseline_dict({**self.default_baseline, **self.baseline}))
            new_baseline["engine"] = ENGINE_ID
            new_baseline["calibrated_at"] = now_iso
            new_baseline["samples_count"] = max(int(new_baseline.get("samples_count", 0) or 0), 1)
            anchors = dict(new_baseline.get("anchors") or {"power": None, "whisper": None})
            anchors.setdefault("power", None)
            anchors.setdefault("whisper", None)
            anchor_entry = dict(clamped_means)
            anchor_entry["calibrated_at"] = now_iso
            anchors[mode_key] = anchor_entry
            new_baseline["anchors"] = anchors

        with open(self.baseline_path, "w", encoding="utf-8") as f:
            json.dump(new_baseline, f, ensure_ascii=False, indent=2)
        self.baseline = self._clamp_baseline_dict({**self.default_baseline, **new_baseline})
        log.info("ベースライン登録完了 (mode=%s): %s (%d サンプル)", mode_key, self.baseline_path.name, len(wav_inputs))
        return self.baseline


# ---------------------------------------------------------------------------
# シングルトンインスタンス保持
# ---------------------------------------------------------------------------
_ANALYZER_INSTANCE: Optional[VoiceEmoAnalyzer] = None


def get_voice_emo_analyzer(device: str = "cpu") -> VoiceEmoAnalyzer:
    global _ANALYZER_INSTANCE
    if _ANALYZER_INSTANCE is None:
        _ANALYZER_INSTANCE = VoiceEmoAnalyzer(device=device)
    return _ANALYZER_INSTANCE
