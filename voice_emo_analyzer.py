"""
voice_emo_analyzer.py
3次元感情モデル (wav2vec2-msp-dim) + openSMILE eGeMAPSv02 による
「12感情・色気スコア算出＆Animagine XLプロンプト合成」コアモジュール

StoryWeaver Live 統合用
- 原則 CPU 推論 (device="cpu") により VRAM 増分 0MB を維持
- FaceDetailer 案B (Node 5: Base用 / Node 32: FD表情専用) に適合
"""

import io
import json
import logging
import math
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import opensmile
import soundfile as sf
import torch
import torch.nn as nn
from transformers import Wav2Vec2Processor
from transformers.models.wav2vec2.modeling_wav2vec2 import (
    Wav2Vec2Model,
    Wav2Vec2PreTrainedModel,
)

log = logging.getLogger("storyweaver.voice_emo")
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "voice_emo_config.json"
BASELINE_PATH = BASE_DIR / "voice_emo_baseline.json"


# ---------------------------------------------------------------------------
# audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim カスタムクラス定義
# ---------------------------------------------------------------------------
class RegressionHead(nn.Module):
    """Classification/Regression head for continuous VAD output."""

    def __init__(self, config):
        super().__init__()
        num_targets = (
            getattr(config, "num_targets", None)
            or getattr(config, "num_labels", None)
            or len(config.id2label)
        )
        self.dense = nn.Linear(config.hidden_size, config.hidden_size)
        self.dropout = nn.Dropout(config.final_dropout)
        self.out_proj = nn.Linear(config.hidden_size, num_targets)

    def forward(self, features, **kwargs):
        x = features
        x = self.dropout(x)
        x = self.dense(x)
        x = torch.tanh(x)
        x = self.dropout(x)
        x = self.out_proj(x)
        return x


class EmotionModel(Wav2Vec2PreTrainedModel):
    """Speech emotion continuous VAD model."""

    def __init__(self, config):
        super().__init__(config)
        self.config = config
        self.wav2vec2 = Wav2Vec2Model(config)
        self.classifier = RegressionHead(config)
        self.post_init()

    def forward(self, input_values):
        outputs = self.wav2vec2(input_values)
        hidden_states = outputs[0]
        hidden_states = torch.mean(hidden_states, dim=1)
        logits = self.classifier(hidden_states)
        return logits


# ---------------------------------------------------------------------------
# コアアナライザークラス
# ---------------------------------------------------------------------------
class VoiceEmoAnalyzer:
    """音声感情・音響特徴量アナライザー"""

    def __init__(
        self,
        config_path: Union[str, Path] = CONFIG_PATH,
        baseline_path: Union[str, Path] = BASELINE_PATH,
        device: str = "cpu",
    ):
        self.config_path = Path(config_path)
        self.baseline_path = Path(baseline_path)
        self.device = torch.device(device)

        self.config = self._load_json(self.config_path)
        self.baseline = self._load_baseline()

        self.processor: Optional[Wav2Vec2Processor] = None
        self.model: Optional[EmotionModel] = None
        self.smile: Optional[opensmile.Smile] = None
        self.is_loaded = False

    def _load_json(self, path: Path) -> dict:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_baseline(self) -> dict:
        if self.baseline_path.is_file():
            try:
                with open(self.baseline_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.warning("ベースライン読み込み失敗、デフォルト値を使用: %s", e)
        return dict(self.config.get("default_baseline", {}))

    def load_model(self) -> None:
        """モデルおよび openSMILE のロード"""
        if self.is_loaded:
            return

        model_name = self.config.get(
            "model_name", "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"
        )
        log.info("VoiceEmoAnalyzer: モデルロード中 (%s, device=%s)", model_name, self.device)
        t0 = time.time()

        self.processor = Wav2Vec2Processor.from_pretrained(model_name)
        self.model = EmotionModel.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

        self.smile = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.Functionals,
        )

        self.is_loaded = True
        log.info("VoiceEmoAnalyzer: ロード完了 (%.2f 秒)", time.time() - t0)

    def warmup(self) -> None:
        """推論ウォームアップ"""
        if not self.is_loaded:
            self.load_model()
        dummy_audio = np.zeros(16000 * 3, dtype=np.float32)
        _ = self.analyze_signal(dummy_audio, 16000)
        log.info("VoiceEmoAnalyzer: ウォームアップ完了")

    def _read_audio(self, wav_input: Union[bytes, str, Path, np.ndarray]) -> Tuple[np.ndarray, int]:
        """各種入力を 16kHz float32 モノラル配列に正規化"""
        if isinstance(wav_input, np.ndarray):
            audio = wav_input.astype(np.float32)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            return audio, 16000

        if isinstance(wav_input, bytes):
            bio = io.BytesIO(wav_input)
            data, sr = sf.read(bio, dtype="float32")
        else:
            p = Path(wav_input)
            data, sr = sf.read(p, dtype="float32")

        if data.ndim > 1:
            data = data.mean(axis=1)
        return data, sr

    def extract_raw_features(self, audio: np.ndarray, sr: int = 16000) -> Dict[str, float]:
        """openSMILE および wav2vec2 からの生特徴量抽出"""
        if not self.is_loaded:
            self.load_model()

        duration_sec = float(len(audio)) / float(sr) if sr > 0 else 0.0

        # 1) wav2vec2 continuous VAD 推論
        with torch.no_grad():
            inp = torch.tensor(audio, dtype=torch.float32).unsqueeze(0).to(self.device)
            # 無音対策
            if torch.all(inp == 0):
                vad = [0.5, 0.5, 0.5]
            else:
                logits = self.model(inp)
                vad = logits.squeeze(0).cpu().tolist()

        # id2label: {0: 'arousal', 1: 'dominance', 2: 'valence'}
        arousal_raw = float(vad[0]) if len(vad) > 0 else 0.5
        dominance_raw = float(vad[1]) if len(vad) > 1 else 0.5
        valence_raw = float(vad[2]) if len(vad) > 2 else 0.5

        # 2) openSMILE eGeMAPSv02 特徴量抽出
        try:
            df = self.smile.process_signal(audio, sr)
        except Exception as e:
            log.warning("openSMILE 処理エラー: %s", e)
            df = None

        def _get_val(col_name: str, fallback: float) -> float:
            if df is not None and col_name in df.columns:
                v = df[col_name].values[0]
                if v is not None and not math.isnan(v) and not math.isinf(v):
                    return float(v)
            return fallback

        def_base = self.config.get("default_baseline", {})
        h1_h2 = _get_val("logRelF0-H1-H2_sma3nz_amean", def_base.get("logRelF0-H1-H2", -5.0))
        hnr = _get_val("HNRdBACF_sma3nz_amean", def_base.get("HNRdBACF", 12.0))
        alpha = _get_val("alphaRatioV_sma3nz_amean", def_base.get("alphaRatioV", -15.0))
        hammarberg = _get_val("hammarbergIndexV_sma3nz_amean", def_base.get("hammarbergIndexV", 18.0))
        peaks_sec = _get_val("loudnessPeaksPerSec", def_base.get("loudnessPeaksPerSec", 3.0))
        jitter = _get_val("jitterLocal_sma3nz_amean", def_base.get("jitterLocal", 0.02))
        shimmer = _get_val("shimmerLocaldB_sma3nz_amean", def_base.get("shimmerLocaldB", 0.8))

        return {
            "valence": valence_raw,
            "arousal": arousal_raw,
            "dominance": dominance_raw,
            "logRelF0-H1-H2": h1_h2,
            "HNRdBACF": hnr,
            "alphaRatioV": alpha,
            "hammarbergIndexV": hammarberg,
            "loudnessPeaksPerSec": peaks_sec,
            "duration_sec": duration_sec,
            "jitterLocal": jitter,
            "shimmerLocaldB": shimmer,
        }

    def normalize_7_features(
        self, raw: Dict[str, float], baseline: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """7つの基礎指標を 0〜100 点に正規化 (棒読み基準 = 50点)"""
        base = baseline or self.baseline
        scales = self.config.get("scales", {})

        def _calc_score(raw_val: float, base_key: str, positive: bool = True) -> float:
            b_val = base.get(base_key, self.config.get("default_baseline", {}).get(base_key, 0.0))
            scale = scales.get(base_key, 1.0)
            if scale <= 1e-6:
                scale = 1.0
            diff = (raw_val - b_val) if positive else (b_val - raw_val)
            score = 50.0 + (diff / scale) * 50.0
            if math.isnan(score) or math.isinf(score):
                return 50.0
            return float(np.clip(score, 0.0, 100.0))

        # 1) Valence
        val_score = _calc_score(raw["valence"], "valence", positive=True)

        # 2) Arousal
        aro_score = _calc_score(raw["arousal"], "arousal", positive=True)

        # 3) Dominance
        dom_score = _calc_score(raw["dominance"], "dominance", positive=True)

        # 4) Breathiness: H1-H2 (高=息漏れ) + HNR (低=息成分多い)
        b_h1h2 = _calc_score(raw["logRelF0-H1-H2"], "logRelF0-H1-H2", positive=True)
        b_hnr = _calc_score(raw["HNRdBACF"], "HNRdBACF", positive=False)
        breathiness = float(np.clip(0.5 * b_h1h2 + 0.5 * b_hnr, 0.0, 100.0))

        # 5) Softness: AlphaRatio (低=穏やか) + Hammarberg (高=高域エネルギー穏やか)
        s_alpha = _calc_score(raw["alphaRatioV"], "alphaRatioV", positive=False)
        s_hammar = _calc_score(raw["hammarbergIndexV"], "hammarbergIndexV", positive=True)
        softness = float(np.clip(0.5 * s_alpha + 0.5 * s_hammar, 0.0, 100.0))

        # 6) Slowness: 発話長 (長=ゆったり) + PeaksPerSec (低=ゆったり)
        sl_dur = _calc_score(raw["duration_sec"], "duration_sec", positive=True)
        sl_peaks = _calc_score(raw["loudnessPeaksPerSec"], "loudnessPeaksPerSec", positive=False)
        slowness = float(np.clip(0.5 * sl_dur + 0.5 * sl_peaks, 0.0, 100.0))

        # 7) Tremor: Jitter (高=揺らぎ) + Shimmer (高=揺らぎ)
        t_jit = _calc_score(raw["jitterLocal"], "jitterLocal", positive=True)
        t_shim = _calc_score(raw["shimmerLocaldB"], "shimmerLocaldB", positive=True)
        tremor = float(np.clip(0.5 * t_jit + 0.5 * t_shim, 0.0, 100.0))

        return {
            "valence": round(val_score, 1),
            "arousal": round(aro_score, 1),
            "dominance": round(dom_score, 1),
            "breathiness": round(breathiness, 1),
            "softness": round(softness, 1),
            "slowness": round(slowness, 1),
            "tremor": round(tremor, 1),
        }

    def compute_12_emotions(self, f7: Dict[str, float]) -> Dict[str, float]:
        """voice_emo.md §5(2) に完全準拠した12感情スコア計算 (0〜100点)"""
        val = f7["valence"]
        aro = f7["arousal"]
        dom = f7["dominance"]
        bre = f7["breathiness"]
        sof = f7["softness"]
        slo = f7["slowness"]
        tre = f7["tremor"]

        # 12感情計算式
        raw_emotions = {
            # 1. 色気・官能 (Sensuality)
            "sensuality": 0.45 * bre + 0.30 * slo + 0.25 * (100.0 - abs(aro - 40.0)),
            # 2. 愛情・親愛 (Affection)
            "affection": 0.35 * val + 0.30 * bre + 0.20 * sof + 0.15 * aro,
            # 3. 慈愛・優しさ (Benevolence)
            "benevolence": 0.35 * sof + 0.30 * val + 0.20 * slo + 0.15 * (100.0 - aro),
            # 4. 自愛・陶酔 (Self-Love)
            "self_love": 0.30 * val + 0.30 * dom + 0.25 * slo + 0.15 * (100.0 - aro),
            # 5. 歓喜・喜び (Joy)
            "joy": 0.40 * val + 0.40 * aro + 0.20 * dom,
            # 6. 楽しさ・無邪気 (Amusement)
            "amusement": 0.40 * val + 0.30 * aro + 0.30 * (100.0 - slo),
            # 7. 哀しみ・憂愁 (Sorrow)
            "sorrow": (
                0.30 * (100.0 - val)
                + 0.25 * (100.0 - aro)
                + 0.25 * (100.0 - dom)
                + 0.20 * tre
            ),
            # 8. 恥じらい・照れ (Bashfulness)
            "bashfulness": 0.35 * bre + 0.30 * (100.0 - dom) + 0.20 * tre + 0.15 * sof,
            # 9. 激しい怒り (Rage)
            "rage": (
                0.35 * (100.0 - val)
                + 0.35 * aro
                + 0.20 * dom
                + 0.10 * (100.0 - sof)
            ),
            # 10. 憎しみ・怨念 (Hatred)
            "hatred": (
                0.40 * (100.0 - val)
                + 0.25 * dom
                + 0.20 * (100.0 - sof)
                + 0.15 * (100.0 - aro)
            ),
            # 11. 軽蔑・冷酷 (Contempt)
            "contempt": (
                0.30 * (100.0 - val)
                + 0.30 * dom
                + 0.20 * (100.0 - aro)
                + 0.20 * (100.0 - bre)
            ),
            # 12. 恐怖・怯え (Fear)
            "fear": (
                0.30 * (100.0 - val)
                + 0.30 * aro
                + 0.20 * (100.0 - dom)
                + 0.20 * tre
            ),
        }

        # 0〜100 クリップ
        res = {}
        for k, v in raw_emotions.items():
            clipped = float(np.clip(v, 0.0, 100.0))
            res[k] = round(clipped, 1)
        return res

    def generate_prompts(
        self, emotions: Dict[str, float]
    ) -> Tuple[str, str, Dict[str, Any], Dict[str, Any]]:
        """
        上位2感情を抽出し、Animagine XL 3.1 適合の Base 用および FD 用プロンプトを生成
        重み: round(0.85 + (score / 100) * 0.35, 2) [最大 1.20]
        """
        emotions_def = self.config.get("emotions", {})

        # スコア降順ソート
        sorted_emotions = sorted(emotions.items(), key=lambda x: x[1], reverse=True)
        top1_key, top1_score = sorted_emotions[0]
        top2_key, top2_score = sorted_emotions[1]

        def _calc_weight(score: float) -> float:
            w = round(0.85 + (score / 100.0) * 0.35, 2)
            return min(1.20, max(0.85, w))

        w1 = _calc_weight(top1_score)
        w2 = _calc_weight(top2_score)

        e1_info = emotions_def.get(top1_key, {})
        e2_info = emotions_def.get(top2_key, {})

        f_tags1 = e1_info.get("face_tags", "")
        l_tags1 = e1_info.get("lighting_tags", "")
        f_tags2 = e2_info.get("face_tags", "")
        l_tags2 = e2_info.get("lighting_tags", "")

        # Base 用プロンプト (Node 5: 表情 + 照明)
        base_parts = []
        if f_tags1:
            base_parts.append(f"({f_tags1}:{w1})")
        if l_tags1:
            base_parts.append(f"({l_tags1}:{w1})")
        if f_tags2:
            base_parts.append(f"({f_tags2}:{w2})")
        if l_tags2:
            base_parts.append(f"({l_tags2}:{w2})")
        prompt_base = ", ".join(base_parts)

        # FD 用プロンプト (Node 32: FaceDetailer 表情のみ)
        fd_parts = []
        if f_tags1:
            fd_parts.append(f"({f_tags1}:{w1})")
        if f_tags2:
            fd_parts.append(f"({f_tags2}:{w2})")
        prompt_fd = ", ".join(fd_parts)

        top1_dict = {
            "id": top1_key,
            "name_ja": e1_info.get("name_ja", top1_key),
            "score": top1_score,
            "icon": e1_info.get("icon", "✨"),
            "weight": w1,
            "face_tags": f_tags1,
            "lighting_tags": l_tags1,
        }
        top2_dict = {
            "id": top2_key,
            "name_ja": e2_info.get("name_ja", top2_key),
            "score": top2_score,
            "icon": e2_info.get("icon", "✨"),
            "weight": w2,
            "face_tags": f_tags2,
            "lighting_tags": l_tags2,
        }

        return prompt_base, prompt_fd, top1_dict, top2_dict

    def analyze_signal(self, audio: np.ndarray, sr: int = 16000) -> Dict[str, Any]:
        """波形配列に対する完全パイプライン解析"""
        t0 = time.time()
        raw = self.extract_raw_features(audio, sr)
        f7 = self.normalize_7_features(raw)
        e12 = self.compute_12_emotions(f7)
        prompt_base, prompt_fd, top1, top2 = self.generate_prompts(e12)
        elapsed = round(time.time() - t0, 3)

        return {
            "primary_emotion": top1,
            "secondary_emotion": top2,
            "expression_state": top1["id"],
            "expression_prompt": prompt_base,
            "expression_prompt_fd": prompt_fd,
            "raw_features": raw,
            "features_7": f7,
            "emotions_12": e12,
            "analysis_time_sec": elapsed,
        }

    def analyze(self, wav_input: Union[bytes, str, Path, np.ndarray]) -> Dict[str, Any]:
        """WAVバイト列、ファイルパス、または波形配列からの完全解析"""
        audio, sr = self._read_audio(wav_input)
        return self.analyze_signal(audio, sr)

    def calibrate_baseline(
        self, wav_inputs: List[Union[bytes, str, Path, np.ndarray]]
    ) -> Dict[str, Any]:
        """
        棒読み音声サンプルから7基礎特徴量の平均を算出し、
        voice_emo_baseline.json を更新・保存する
        """
        if not wav_inputs:
            raise ValueError("1つ以上の音声サンプルが必要です")

        collected: Dict[str, List[float]] = {
            "valence": [],
            "arousal": [],
            "dominance": [],
            "logRelF0-H1-H2": [],
            "HNRdBACF": [],
            "alphaRatioV": [],
            "hammarbergIndexV": [],
            "loudnessPeaksPerSec": [],
            "duration_sec": [],
            "jitterLocal": [],
            "shimmerLocaldB": [],
        }

        for item in wav_inputs:
            audio, sr = self._read_audio(item)
            raw = self.extract_raw_features(audio, sr)
            for k in collected.keys():
                collected[k].append(raw[k])

        new_baseline = {}
        for k, vals in collected.items():
            new_baseline[k] = round(float(np.mean(vals)), 4)

        new_baseline["calibrated_at"] = datetime.now().isoformat()
        new_baseline["samples_count"] = len(wav_inputs)

        with open(self.baseline_path, "w", encoding="utf-8") as f:
            json.dump(new_baseline, f, ensure_ascii=False, indent=2)

        self.baseline = new_baseline
        log.info("ベースライン登録完了: %s (%d サンプル)", self.baseline_path.name, len(wav_inputs))
        return new_baseline


# ---------------------------------------------------------------------------
# シングルトンインスタンス保持
# ---------------------------------------------------------------------------
_ANALYZER_INSTANCE: Optional[VoiceEmoAnalyzer] = None


def get_voice_emo_analyzer(device: str = "cpu") -> VoiceEmoAnalyzer:
    global _ANALYZER_INSTANCE
    if _ANALYZER_INSTANCE is None:
        _ANALYZER_INSTANCE = VoiceEmoAnalyzer(device=device)
    return _ANALYZER_INSTANCE
