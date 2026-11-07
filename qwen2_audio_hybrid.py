"""
qwen2_audio_hybrid.py
2-Step ハイブリッド音声感情・演技ニュアンス分析モジュール
- Step 1 (聴覚知覚): Qwen/Qwen2-Audio-7B-Instruct (Apache-2.0・4bit量子化) による音声の感情・発声スタイル読み取り (英語)
- 中間層 (Semantic Bridge): librosa 物理音響特徴と個人ベースライン差分 (baseline_deltas) の英語意味ラベル変換
- Step 2 (論理統合・採点): Ollama (gemma4:e2b, JSON Schema 0〜5整数採点 × 20) による8感情採点

設計方針:
- RTX 3080 Laptop (VRAM 16GB) 環境で ComfyUI / Ollama と共存するため、Qwen2-Audio は bitsandbytes NF4 4bit 量子化でロード
- Step 1 推論の裏で Ollama (gemma4:e2b) を非同期プリロードし、Step 2 完了と同時に keep_alive=0 で Ollama VRAM を即時解放
- ComfyUI 画像生成前に Qwen2-Audio の VRAM を即時解放する unload_model() と、推論時に自動再ロードする ensure_loaded() を実装
- 台本セリフの「言葉の意味」への引っ張られを厳禁とし、実際の声のトーンとベースラインからの物理変化量のみで8感情（基本6＋修飾2）を採点
- 万が一の通信例外時は voice_emo_analyzer のプロトタイプ類似度スコアへシームレスにフォールバック
"""

import concurrent.futures
import gc
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import librosa
import numpy as np
import requests

from voice_emo_analyzer import (
    MODIFIER_EMOTION_KEYS,
    PRIMARY_EMOTION_KEYS,
    TARGET_SR,
    VoiceEmoAnalyzer,
    get_voice_emo_analyzer,
)

log = logging.getLogger("storyweaver.qwen2_audio_hybrid")

DEFAULT_MODEL_ID = "Qwen/Qwen2-Audio-7B-Instruct"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "gemma4:e2b"
DEFAULT_OLLAMA_TIMEOUT_SEC = 30

ALL_EMOTION_KEYS: Tuple[str, ...] = (*PRIMARY_EMOTION_KEYS, *MODIFIER_EMOTION_KEYS)

SYSTEM_PROMPT = """あなたはプロの音響心理学者・声優演技ディレクターAIです。
入力された「16kHz音声波形（正規化済み）」と「棒読み基準（平常発声）からの客観的物理変化データ」を統合分析し、発話者の「実際の声のトーン・表情・ニュアンス」から感情・声質スコア（各0〜100点）と演技講評を純粋なJSONオブジェクトで出力してください。

【採点の大原則】
1. セリフテキストの意味（台本上の言葉）から感情を推測することは厳禁です。必ず発話者の「声のトーン、響き、息遣い、抑揚」を聴いて評価してください。
2. 物理変化データ（ΔRMS, ΔPitch, 語尾スロープ, 息倍率等）は平常との客観的な差分です。特定の数値だけで機械的に判断せず、波形から聴こえる実際の演技表現と照らし合わせて総合解釈してください。
   - 例：ピッチが高くても、語尾が力なく下降していたり切ないトーンであれば「哀愁・切なさ（sorrow）」を高く採点してください。
   - 例：声に息が抜ける囁き・ウィスパーや艶っぽさを感じ取った場合は、「色気・吐息（sultry_modifier）」を遠慮なく60〜85点以上で評価してください。
3. すべての感情に似た点数をつけたり、特定の感情（joy や serene など）を無難に高得点固定にすることは禁止です。声の表情に最も合致する感情を高く（75点以上）、相反する感情を低く（30点以下）メリハリをつけて採点してください。

【出力ルール】
- Markdownのコードブロック（```json 等）や解説文は一切出力せず、純粋な JSON オブジェクトのみを出力してください。"""

STEP1_PROMPT = "What is the emotion of the speaker and does the speaker whisper or shout?"

STEP2_TEMPLATE = """You are an expert voice acting director. Based on the Acoustic Perception and Physical Voice Analysis below, evaluate the speaker's emotional expression.

[1. Acoustic Perception (from audio listening)]
{step1_description}

[2. Physical Voice Analysis (compared to the speaker's normal baseline)]
- Vocal Energy & Volume: {semantic_loudness}
- Pitch & Intonation: {semantic_pitch_and_intonation}
- Timbre & Clarity: {semantic_timbre}
- Breathiness / Whisper Check: {semantic_sultry_hint}
- Voice Tremor / Hesitation Check: {semantic_bashful_hint}

[Scoring Rules (0 to 5 Integer Scale)]
Rate each of the 8 categories using ONLY integers from 0 to 5:
- 0 = None (completely absent)
- 1 = Minimal (trace)
- 2 = Mild (weak sub-nuance)
- 3 = Moderate (noticeable secondary emotion)
- 4 = Strong (clear primary emotion or active modifier)
- 5 = Extreme (overwhelmingly dominant emotion or modifier)

IMPORTANT GUIDELINES:
1. Give 4 or 5 ONLY to the 1 or 2 truly dominant emotions that match the Acoustic Perception and Physical Voice Analysis.
2. Give 0 or 1 to all unrelated emotions. At least one primary emotion (joy, burning, sorrow, surprise_fear, confident, or serene) MUST be rated 4 or 5.
3. Distinguishing High Energy (Joy vs Burning):
   - If the voice has High vocal energy / Loud projection AND Wide, dramatic pitch variation (or sounds angry/urgent/aggressive/shouting), rate "burning" 4-5 and keep "joy" 0-1.
   - If the voice has Moderately louder/high energy AND Expressive, lively intonation with Bright timbre (and sounds cheerful/happy/excited), rate "joy" 4-5 and keep "burning" 0-1.
4. Calm / Neutral / Cool vs Sad:
   - If the voice is calm, neutral, flat, composed, or cool without sadness (or Quiet/Normal volume with neutral perception), map it to "serene" or "confident" (rate 4-5) and keep "sorrow" 0-1.
   - If the voice sounds sad, depressed, or sorrowful (or has Very flat, monotone, or depressed intonation with sad perception), rate "sorrow" 4-5.
5. Modifiers (Trigger threshold is 4 or 5):
   - "sultry_modifier": If Breathiness/Whisper Check indicates Strong or Mild breathiness (AND Vocal Energy is Normal or Quiet, NOT High/Moderately louder), you MUST rate "sultry_modifier" 4 or 5. If Vocal Energy is High or Moderately louder, rate "sultry_modifier" 0 or 1.
   - "bashful_modifier": Rate 4 or 5 ONLY when BOTH Voice Tremor Check AND Acoustic Perception explicitly indicate shyness, embarrassment, or flustered hesitation. Otherwise keep "bashful_modifier" at 0 or 1.
"""

STEP2_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_impression_en": {"type": "string"},
        "primary_emotion": {
            "type": "string",
            "enum": ["joy", "burning", "sorrow", "surprise_fear", "confident", "serene"],
        },
        "secondary_emotion": {
            "type": "string",
            "enum": [
                "none",
                "joy",
                "burning",
                "sorrow",
                "surprise_fear",
                "confident",
                "serene",
                "sultry_modifier",
                "bashful_modifier",
            ],
        },
        "joy": {"type": "integer", "minimum": 0, "maximum": 5},
        "burning": {"type": "integer", "minimum": 0, "maximum": 5},
        "sorrow": {"type": "integer", "minimum": 0, "maximum": 5},
        "surprise_fear": {"type": "integer", "minimum": 0, "maximum": 5},
        "confident": {"type": "integer", "minimum": 0, "maximum": 5},
        "serene": {"type": "integer", "minimum": 0, "maximum": 5},
        "sultry_modifier": {"type": "integer", "minimum": 0, "maximum": 5},
        "bashful_modifier": {"type": "integer", "minimum": 0, "maximum": 5},
    },
    "required": [
        "overall_impression_en",
        "primary_emotion",
        "secondary_emotion",
        "joy",
        "burning",
        "sorrow",
        "surprise_fear",
        "confident",
        "serene",
        "sultry_modifier",
        "bashful_modifier",
    ],
}


def _load_ollama_settings() -> Tuple[str, str, int]:
    """config.json から Ollama 接続設定を取得する"""
    cfg_path = Path(__file__).resolve().parent / "config.json"
    url = DEFAULT_OLLAMA_URL
    model = DEFAULT_OLLAMA_MODEL
    timeout_sec = DEFAULT_OLLAMA_TIMEOUT_SEC
    try:
        if cfg_path.is_file():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            url = str(data.get("OLLAMA_URL") or url)
            model = str(data.get("OLLAMA_MODEL") or model)
            timeout_sec = int(data.get("OLLAMA_TIMEOUT_SEC") or timeout_sec)
    except Exception:
        pass
    return url, model, timeout_sec


def _ollama_ps_url(ollama_generate_url: str) -> str:
    """Ollama の /api/generate URL から /api/ps URL を導出する"""
    base = ollama_generate_url.rstrip("/")
    if base.endswith("/api/generate"):
        return base[: -len("/api/generate")] + "/api/ps"
    return base + "/api/ps"


def get_ollama_model_status(
    ollama_url: Optional[str] = None,
    ollama_model: Optional[str] = None,
    timeout_sec: int = 5,
) -> Dict[str, Any]:
    """Ollama (/api/ps) を参照し、指定モデルが VRAM 上にロードされているか・使用 VRAM (MB) を返す"""
    cfg_url, cfg_model, _ = _load_ollama_settings()
    target_url = ollama_url or cfg_url
    target_model = (ollama_model or cfg_model).strip()
    ps_url = _ollama_ps_url(target_url)
    try:
        r = requests.get(ps_url, timeout=timeout_sec)
        if r.status_code == 200:
            models = r.json().get("models", [])
            for m in models:
                m_name = str(m.get("name") or m.get("model") or "").strip()
                if m_name == target_model or m_name.split(":")[0] == target_model.split(":")[0]:
                    size_vram = float(m.get("size_vram") or m.get("size") or 0.0)
                    vram_mb = round(size_vram / (1024.0 * 1024.0), 1)
                    return {
                        "is_loaded": True,
                        "model": m_name,
                        "vram_used_mb": vram_mb,
                    }
        return {"is_loaded": False, "model": target_model, "vram_used_mb": 0.0}
    except Exception as e:
        log.debug("get_ollama_model_status 失敗: %s", e)
        return {"is_loaded": False, "model": target_model, "vram_used_mb": 0.0, "error": str(e)}


def preload_ollama_model(
    ollama_url: Optional[str] = None,
    ollama_model: Optional[str] = None,
    keep_alive: Union[int, str] = "15m",
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    """トークン生成を伴わずに (prompt='') 指定モデルを Ollama の VRAM にプリロードし keep_alive を設定する"""
    cfg_url, cfg_model, _ = _load_ollama_settings()
    target_url = ollama_url or cfg_url
    target_model = ollama_model or cfg_model
    t0 = time.time()
    try:
        r = requests.post(
            target_url,
            json={
                "model": target_model,
                "prompt": "",
                "stream": False,
                "keep_alive": keep_alive,
            },
            timeout=timeout_sec,
        )
        r.raise_for_status()
        elapsed = round(time.time() - t0, 2)
        st = get_ollama_model_status(target_url, target_model)
        log.info(
            "Ollama モデルプリロード完了: model=%s, keep_alive=%s (%.2fs, VRAM=%.1fMB)",
            target_model,
            keep_alive,
            elapsed,
            st.get("vram_used_mb", 0.0),
        )
        return {
            "ok": True,
            "model": target_model,
            "keep_alive": keep_alive,
            "elapsed_sec": elapsed,
            "is_loaded": st.get("is_loaded", True),
            "vram_used_mb": st.get("vram_used_mb", 0.0),
        }
    except Exception as e:
        log.warning("preload_ollama_model 失敗 (%s): %s", target_model, e)
        return {
            "ok": False,
            "model": target_model,
            "error": str(e),
            "elapsed_sec": round(time.time() - t0, 2),
        }


def unload_ollama_model(
    ollama_url: Optional[str] = None,
    ollama_model: Optional[str] = None,
    timeout_sec: int = 15,
) -> Dict[str, Any]:
    """Ollama モデルを keep_alive=0 で即座に VRAM からアンロードする"""
    cfg_url, cfg_model, _ = _load_ollama_settings()
    target_url = ollama_url or cfg_url
    target_model = ollama_model or cfg_model
    try:
        st_before = get_ollama_model_status(target_url, target_model, timeout_sec=3)
        if not st_before.get("is_loaded", False):
            return {"was_loaded": False, "model": target_model, "vram_before_mb": 0.0}
        requests.post(
            target_url,
            json={
                "model": target_model,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            },
            timeout=timeout_sec,
        )
        log.info(
            "Ollama モデルアンロード完了: model=%s (解放前 VRAM: %.1fMB)",
            target_model,
            st_before.get("vram_used_mb", 0.0),
        )
        return {
            "was_loaded": True,
            "model": target_model,
            "vram_before_mb": st_before.get("vram_used_mb", 0.0),
        }
    except Exception as e:
        log.warning("unload_ollama_model 失敗 (%s): %s", target_model, e)
        return {"was_loaded": False, "model": target_model, "error": str(e)}


class Qwen2AudioHybridAnalyzer:
    """Qwen2-Audio-7B-Instruct (4bit) + Semantic Bridge + Gemma 4 e2b ハイブリッド分析クラス"""

    def __init__(self, model_id: str = DEFAULT_MODEL_ID):
        self.model_id = model_id
        self.model: Any = None
        self.processor: Any = None
        self.is_loaded: bool = False
        self._lock = threading.Lock()
        self._bg_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    # ------------------------------------------------------------------
    # GPU / VRAM 管理 (load / ensure_loaded / unload)
    # ------------------------------------------------------------------
    @staticmethod
    def get_vram_used_mb() -> float:
        """現在の PyTorch CUDA 割り当て済み VRAM (MB) を返す"""
        try:
            import torch

            if torch.cuda.is_available():
                return round(float(torch.cuda.memory_allocated()) / (1024.0 * 1024.0), 1)
        except Exception:
            pass
        return 0.0

    def load_model(self) -> None:
        """bitsandbytes 4bit (NF4 / float16 / double_quant) で Qwen2-Audio-7B-Instruct をロード"""
        with self._lock:
            if self.is_loaded and self.model is not None and self.processor is not None:
                return

            t0 = time.time()
            import torch
            from transformers import (
                AutoProcessor,
                BitsAndBytesConfig,
                Qwen2AudioForConditionalGeneration,
            )

            log.info("Qwen2-Audio 4bit モデルをロード中: %s ...", self.model_id)
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA GPU が無効です (torch.cuda.is_available() == False)。"
                    "CPU/RAM への巨大モデル展開を防ぐためロードを中断しました。"
                )
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            self.processor = AutoProcessor.from_pretrained(
                self.model_id,
                trust_remote_code=True,
            )
            self.model = Qwen2AudioForConditionalGeneration.from_pretrained(
                self.model_id,
                quantization_config=bnb_config,
                device_map="auto",
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True,
                trust_remote_code=True,
            )
            self.model.eval()
            self.is_loaded = True
            vram_mb = self.get_vram_used_mb()
            log.info(
                "Qwen2-Audio 4bit ロード完了 (所要 %.2fs / VRAM使用量: %.1f MB)",
                time.time() - t0,
                vram_mb,
            )

    def ensure_loaded(self) -> None:
        """未ロード状態であれば自動的に 4bit モデルをロードする"""
        if not self.is_loaded or self.model is None or self.processor is None:
            self.load_model()

    def unload_model(self) -> Dict[str, Any]:
        """ComfyUI 画像生成前にモデルとプロセッサの参照を破棄し、VRAM を即座に解放する"""
        with self._lock:
            before_mb = self.get_vram_used_mb()
            was_loaded = self.is_loaded or (self.model is not None) or (self.processor is not None)

            if self.model is not None:
                del self.model
                self.model = None
            if self.processor is not None:
                del self.processor
                self.processor = None
            self.is_loaded = False

            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    if hasattr(torch.cuda, "ipc_collect"):
                        torch.cuda.ipc_collect()
            except Exception as e:
                log.warning("CUDA キャッシュ解放中に軽微な例外: %s", e)

            after_mb = self.get_vram_used_mb()
            if was_loaded:
                log.info(
                    "Qwen2-Audio アンロード完了 (VRAM: %.1f MB -> %.1f MB)",
                    before_mb,
                    after_mb,
                )
            return {
                "was_loaded": was_loaded,
                "vram_before_mb": before_mb,
                "vram_after_mb": after_mb,
            }

    # ------------------------------------------------------------------
    # Step 1 音量調整 & Semantic Bridge 構築 & Step 2 (Gemma 4 e2b)
    # ------------------------------------------------------------------
    @staticmethod
    def normalize_for_step1_moderate(audio_16k: np.ndarray, base_rms_db: float = -38.8) -> np.ndarray:
        """
        Step 1 (Qwen2-Audio) 用の控えめな音量調整:
        話者の基準音声 (Base) が -26.0 dBFS 前後になるような控えめなゲイン（上限 +14.0 dB）を適用し、
        ピーク上限 -3.0 dBFS でリミットする。小声・吐息が過増幅で「叫び声」に化けるのを防ぐ。
        """
        target_base_step1_db = -26.0
        speaker_gain_db = max(0.0, min(14.0, target_base_step1_db - float(base_rms_db)))
        speaker_gain_linear = 10.0 ** (speaker_gain_db / 20.0)
        peak_limit_linear = 10.0 ** (-3.0 / 20.0)

        y_scaled = (audio_16k * speaker_gain_linear).astype(np.float32)
        max_abs = float(np.max(np.abs(y_scaled))) if len(y_scaled) > 0 else 0.0
        if max_abs > peak_limit_linear:
            y_scaled = (y_scaled / max_abs * peak_limit_linear).astype(np.float32)
        return y_scaled

    @staticmethod
    def build_semantic_bridge(raw: Dict[str, Any], deltas: Dict[str, Any]) -> Dict[str, str]:
        """物理特徴量とベースライン差分を、汎用的な英語ラベル（セマンティック・ブリッジ）に翻訳する"""
        d_rms = float(deltas.get("delta_rms_db", 0.0))
        d_pitch = float(deltas.get("delta_pitch_st", 0.0))
        d_f0_std = float(deltas.get("delta_f0_std_st", 0.0))
        slope = float(deltas.get("f0_slope_st", 0.0))
        d_cent = float(deltas.get("delta_centroid_hz", 0.0))
        d_hnr = float(deltas.get("delta_hnr_db", 0.0))
        b_mult = float(deltas.get("breath_ratio_Multiple", 1.0))
        b_raw = float(deltas.get("breath_ratio", 0.0))
        shimmer = float(deltas.get("shimmer", 0.0))
        low_band = float(raw.get("low_band_ratio", 0.8))

        # 1. Vocal Energy & Volume
        if d_rms >= 6.0:
            loudness = "High vocal energy / Loud projection"
        elif d_rms >= 2.5:
            loudness = "Moderately louder than baseline"
        elif d_rms > -2.5:
            loudness = "Normal conversational volume (near baseline)"
        else:
            loudness = "Quiet / Soft / Low vocal energy"

        # 2. Pitch & Intonation (using delta_f0_std_st for speaker-independent intonation range)
        is_unvoiced_whisper = (b_mult >= 3.0 and low_band < 0.20)
        if is_unvoiced_whisper:
            pitch_str = "Unvoiced whisper (no fundamental pitch)"
            intonation_str = "Soft whispering contour"
        else:
            if d_pitch >= 3.0:
                pitch_str = "Clearly higher pitch than baseline"
            elif d_pitch >= 1.2:
                pitch_str = "Slightly higher pitch than baseline"
            elif d_pitch > -1.2:
                pitch_str = "Near baseline pitch"
            else:
                pitch_str = "Lower pitch than baseline"

            if d_f0_std >= 1.2:
                intonation_str = "Wide, dramatic pitch variation (much more dynamic than baseline)"
            elif d_f0_std >= 0.0:
                intonation_str = "Expressive, lively intonation (normal to active range)"
            elif d_f0_std > -0.8:
                intonation_str = "Calm, restrained intonation (less pitch movement than baseline)"
            else:
                intonation_str = "Very flat, monotone, or depressed intonation (strongly reduced pitch movement)"

        if slope >= 2.0:
            ending_str = "rising pitch at the end"
        elif slope <= -1.5:
            ending_str = "falling pitch at the end"
        else:
            ending_str = "steady/level ending"

        pitch_and_intonation = f"{pitch_str}; {intonation_str}, with {ending_str}"

        # 3. Timbre & Clarity (delta_centroid_hz)
        if d_cent >= 400.0:
            timbre = "Bright / sharp high-frequency timbre (note: check Acoustic Perception to distinguish cheerful brightness vs loud/whispering air)"
        elif d_cent <= -200.0:
            timbre = "Dark / muffled low-frequency timbre"
        else:
            timbre = "Normal / natural vocal timbre (near baseline)"

        # 4. Breathiness / Whisper Check (sultry_modifier hint)
        if d_rms < 3.0 and b_raw >= 0.015:
            sultry_hint = "Strong breathiness / Whispering or sighing voice detected (high sultry potential)"
        elif d_rms < 3.0 and ((b_raw >= 0.0025 and b_mult >= 2.5) or (b_raw >= 0.0025 and d_hnr <= -3.0)):
            sultry_hint = "Mild breathiness / Soft airy texture (sultry potential)"
        else:
            sultry_hint = "No breathy/whispering quality (clear or loud projected voice)"

        # 5. Voice Tremor / Hesitation Check (bashful_modifier hint)
        if d_rms < 4.0 and not is_unvoiced_whisper and shimmer >= 0.030 and d_pitch >= 1.0:
            bashful_hint = "Subtle voice wavering / possible hesitation (only rate bashful if Acoustic Perception also hears shyness/embarrassment)"
        else:
            bashful_hint = "No bashful tremor detected"

        return {
            "semantic_loudness": loudness,
            "semantic_pitch_and_intonation": pitch_and_intonation,
            "semantic_timbre": timbre,
            "semantic_sultry_hint": sultry_hint,
            "semantic_bashful_hint": bashful_hint,
        }

    @staticmethod
    def format_semantic_bridge_en(sem: Dict[str, str]) -> str:
        """Gemma 4 e2b に渡す物理分析セマンティック・ブリッジの英語テキスト表現を返す"""
        return "\n".join(
            [
                f"- Vocal Energy & Volume: {sem.get('semantic_loudness', '--')}",
                f"- Pitch & Intonation: {sem.get('semantic_pitch_and_intonation', '--')}",
                f"- Timbre & Clarity: {sem.get('semantic_timbre', '--')}",
                f"- Breathiness / Whisper Check: {sem.get('semantic_sultry_hint', '--')}",
                f"- Voice Tremor / Hesitation Check: {sem.get('semantic_bashful_hint', '--')}",
            ]
        )

    @staticmethod
    def _warmup_ollama_bg(ollama_url: str, ollama_model: str, timeout_sec: int = 30) -> None:
        """Qwen2-Audio (Step 1) 推論の裏で、Gemma 4 e2b が未ロードの場合のみ VRAM にプリロードする"""
        try:
            st = get_ollama_model_status(ollama_url, ollama_model, timeout_sec=3)
            if st.get("is_loaded"):
                log.debug("Ollama (%s) は既に VRAM 上に常駐済みのためプリロードをスキップします", ollama_model)
                return
            preload_ollama_model(
                ollama_url=ollama_url,
                ollama_model=ollama_model,
                keep_alive="15m",
                timeout_sec=timeout_sec,
            )
        except Exception as e:
            log.debug("Ollama バックグラウンドプリロード通知 (無視可能): %s", e)

    @staticmethod
    def _run_gemma4_step2(
        prompt: str,
        ollama_url: str,
        ollama_model: str,
        timeout_sec: int = 30,
        unload_after: bool = True,
    ) -> str:
        """Ollama (gemma4:e2b) の JSON Schema モード (think=False) で Step 2 採点を実行する"""
        payload = {
            "model": ollama_model,
            "prompt": prompt,
            "think": False,
            "format": STEP2_JSON_SCHEMA,
            "stream": False,
            "keep_alive": 0 if unload_after else "2m",
            "options": {
                "temperature": 0.0,
            },
        }
        r = requests.post(ollama_url, json=payload, timeout=timeout_sec)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()

    @staticmethod
    def _parse_step2_scores(raw_text: str) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """Step 2 (Gemma 4 e2b) の 0〜5 整数 JSON 出力をパースし、×20 (0〜100点) スコア辞書と生辞書を返す"""
        merged: Dict[str, Any] = json.loads(raw_text) if raw_text else {}
        norm_map = {re.sub(r"[^a-z]", "", str(k).lower()): v for k, v in merged.items()}
        scores_100: Dict[str, float] = {}
        for k in ALL_EMOTION_KEYS:
            nk = re.sub(r"[^a-z]", "", k.lower())
            val_raw = norm_map.get(nk, 0)
            try:
                val = int(round(float(val_raw)))
            except Exception:
                val = 0
            val = max(0, min(5, val))
            scores_100[k] = round(float(val * 20), 1)
        return scores_100, merged

    # ------------------------------------------------------------------
    # メイン推論パイプライン
    # ------------------------------------------------------------------
    def _run_qwen_inference(
        self,
        audio_16k: np.ndarray,
        user_prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Qwen2-Audio-7B-Instruct に 16kHz 音声波形とプロンプトを入力して応答テキストを返す"""
        import torch

        self.ensure_loaded()
        with self._lock:
            sr = TARGET_SR
            if hasattr(self.processor, "feature_extractor") and hasattr(
                self.processor.feature_extractor, "sampling_rate"
            ):
                proc_sr = int(self.processor.feature_extractor.sampling_rate)
                if proc_sr != TARGET_SR:
                    audio_16k = librosa.resample(audio_16k, orig_sr=TARGET_SR, target_sr=proc_sr)
                    sr = proc_sr

            active_system_prompt = (
                system_prompt.strip()
                if system_prompt and system_prompt.strip()
                else SYSTEM_PROMPT
            )
            conversation = [
                {"role": "system", "content": active_system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "audio", "audio_url": "voice_input.wav"},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ]
            chat_text = self.processor.apply_chat_template(
                conversation,
                add_generation_prompt=True,
                tokenize=False,
            )

            # transformers 5.x は audio= を使用（旧版は audios=）
            try:
                inputs = self.processor(
                    text=chat_text,
                    audio=[audio_16k],
                    sampling_rate=sr,
                    return_tensors="pt",
                    padding=True,
                )
                if "input_features" not in inputs:
                    inputs = self.processor(
                        text=chat_text,
                        audios=[audio_16k],
                        sampling_rate=sr,
                        return_tensors="pt",
                        padding=True,
                    )
            except TypeError:
                inputs = self.processor(
                    text=chat_text,
                    audios=[audio_16k],
                    sampling_rate=sr,
                    return_tensors="pt",
                    padding=True,
                )

            target_device = getattr(self.model, "device", None)
            if target_device is not None:
                inputs = {
                    k: (v.to(target_device) if hasattr(v, "to") else v)
                    for k, v in inputs.items()
                }

            with torch.inference_mode():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=128,
                    do_sample=False,
                )

            input_len = inputs["input_ids"].shape[1]
            response_ids = generated_ids[:, input_len:]
            decoded = self.processor.batch_decode(
                response_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            return decoded[0].strip() if decoded else ""

    def analyze_hybrid(
        self,
        wav_input: Union[bytes, str, Path, np.ndarray],
        recognized_text: str = "",
        sense_emotion: str = "",
        custom_system_prompt: Optional[str] = None,
        custom_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        2-Step ハイブリッド音声感情分析を実行する:
        - Step 1: Qwen2-Audio-7B-Instruct (4bit) による英語聴覚知覚
        - Bridge: librosa 物理特徴量とベースライン差分からの英語 Semantic Bridge 構築
        - Step 2: Ollama (gemma4:e2b) による JSON Schema 0〜5整数採点 (×20 で 0〜100点化)
        """
        t0 = time.time()
        analyzer: VoiceEmoAnalyzer = get_voice_emo_analyzer()
        ollama_url, ollama_model, ollama_timeout = _load_ollama_settings()

        # 1. 音声読み込みと librosa 物理特徴・7指標・フォールバック用プロトタイプ感情・ベースライン差分の算出
        audio, sr = analyzer._read_audio(wav_input)
        if sr != TARGET_SR:
            audio_16k = librosa.resample(audio, orig_sr=sr, target_sr=TARGET_SR)
        else:
            audio_16k = audio

        raw = analyzer.extract_raw_features(audio_16k, TARGET_SR)
        is_silent = float(raw.get("_is_silent", 0.0)) >= 0.5
        f7_all = analyzer.normalize_7_features(raw, sense_emotion=sense_emotion)
        f7_dict = {k: v for k, v in f7_all.items() if not k.startswith("_")}
        fallback_emotions = analyzer.compute_12_emotions(f7_all, sense_emotion=sense_emotion)
        baseline_deltas = analyzer.compute_baseline_deltas(raw)
        baseline_deltas["prompt_summary_ja"] = analyzer.format_deltas_for_prompt(
            baseline_deltas, features_7=f7_dict
        )
        raw_features_dict = {k: round(float(v), 4) for k, v in raw.items()}

        sem = self.build_semantic_bridge(raw, baseline_deltas)
        semantic_bridge_en = self.format_semantic_bridge_en(sem)

        # 2. 無音判定時は LLM 推論をスキップして安全フォールバックを即座に返却
        if is_silent:
            prompt_base, prompt_fd, top1, top2 = analyzer.generate_prompts(
                fallback_emotions,
                arousal=f7_dict["arousal"],
                is_silent=True,
            )
            return {
                "emotion_mode": "qwen2_audio_hybrid",
                "primary_emotion": top1,
                "secondary_emotion": top2,
                "expression_state": top1["id"],
                "expression_prompt": prompt_base,
                "expression_prompt_fd": prompt_fd,
                "raw_features": raw_features_dict,
                "features_7": f7_dict,
                "emotions_12": fallback_emotions,
                "baseline_deltas": baseline_deltas,
                "qwen2_perception_en": "Silent / no vocal input detected.",
                "semantic_bridge": sem,
                "semantic_bridge_en": semantic_bridge_en,
                "overall_impression_en": "Silent / calm default expression.",
                "gemma4_raw_response": "",
                "acting_comment_ja": "",
                "detected_nuance_short": "Silent / Calm",
                "qwen_raw_response": "",
                "vram_used_mb": self.get_vram_used_mb(),
                "analysis_time_sec": round(time.time() - t0, 3),
            }

        # 3. Step 1 用の控えめな音量調整（話者の Base RMS を基準に増幅、小声の過増幅を防止）
        base_rms_db = float(
            (analyzer.baseline or analyzer.default_baseline).get("rms_p90_db", -38.8)
        )
        audio_step1 = self.normalize_for_step1_moderate(audio_16k, base_rms_db=base_rms_db)

        # ワークベンチからの Step 1 質問プロンプト指定（旧日本語JSONプロンプトが渡された場合は既定の英語プロンプトを使用）
        step1_question = STEP1_PROMPT
        if custom_system_prompt and custom_system_prompt.strip():
            cand = custom_system_prompt.strip()
            if "0〜100" not in cand and "acting_comment_ja" not in cand:
                step1_question = cand

        # 4. Step 1 (Qwen2-Audio) と並行して Ollama (gemma4:e2b) をバックグラウンドでプリロード
        warmup_future = self._bg_executor.submit(
            self._warmup_ollama_bg, ollama_url, ollama_model, ollama_timeout
        )

        step1_out = ""
        try:
            step1_out = self._run_qwen_inference(
                audio_step1,
                step1_question,
                system_prompt=SYSTEM_PROMPT,
            )
        except Exception as e:
            log.warning("Step 1 (Qwen2-Audio) 推論中に例外が発生しました: %s", e)
            step1_out = "Audio perception unavailable (relying on physical voice analysis)."

        try:
            warmup_future.result(timeout=ollama_timeout)
        except Exception:
            pass

        # 5. Step 2: Ollama (gemma4:e2b) で JSON Schema 0〜5 採点（完了後に keep_alive=0 で即アンロード）
        step2_prompt = STEP2_TEMPLATE.format(
            step1_description=step1_out,
            **sem,
        )
        if custom_instruction and custom_instruction.strip():
            step2_prompt += f"\n\n[Additional Scoring Instruction]\n{custom_instruction.strip()}\n"

        step2_out = ""
        emotions_8_dict: Dict[str, float] = {}
        parsed_step2: Dict[str, Any] = {}
        try:
            step2_out = self._run_gemma4_step2(
                step2_prompt,
                ollama_url=ollama_url,
                ollama_model=ollama_model,
                timeout_sec=ollama_timeout,
                unload_after=True,
            )
            emotions_8_dict, parsed_step2 = self._parse_step2_scores(step2_out)
        except Exception as e:
            log.warning(
                "Step 2 (Ollama %s) 採点中にエラーが発生しました。プロトタイプ類似度スコアへフォールバックします: %s",
                ollama_model,
                e,
            )
            unload_ollama_model(ollama_url=ollama_url, ollama_model=ollama_model)
            for emo_key in ALL_EMOTION_KEYS:
                emotions_8_dict[emo_key] = round(float(fallback_emotions.get(emo_key, 50.0)), 1)

        # 6. Animagine XL 表情プロンプト合成（generate_prompts 再利用で完全互換）
        prompt_base, prompt_fd, top1, top2 = analyzer.generate_prompts(
            emotions_8_dict,
            arousal=f7_dict["arousal"],
            is_silent=False,
        )

        overall_impression_en = str(parsed_step2.get("overall_impression_en") or "").strip()
        if not overall_impression_en:
            overall_impression_en = step1_out

        return {
            "emotion_mode": "qwen2_audio_hybrid",
            "primary_emotion": top1,
            "secondary_emotion": top2,
            "expression_state": top1["id"],
            "expression_prompt": prompt_base,
            "expression_prompt_fd": prompt_fd,
            "raw_features": raw_features_dict,
            "features_7": f7_dict,
            "emotions_12": emotions_8_dict,
            "baseline_deltas": baseline_deltas,
            "qwen2_perception_en": step1_out,
            "semantic_bridge": sem,
            "semantic_bridge_en": semantic_bridge_en,
            "overall_impression_en": overall_impression_en,
            "gemma4_raw_response": step2_out,
            "acting_comment_ja": "",
            "detected_nuance_short": overall_impression_en,
            "qwen_raw_response": step1_out,
            "vram_used_mb": self.get_vram_used_mb(),
            "analysis_time_sec": round(time.time() - t0, 3),
        }

    def analyze(
        self,
        wav_input: Union[bytes, str, Path, np.ndarray],
        recognized_text: str = "",
        sense_emotion: str = "",
    ) -> Dict[str, Any]:
        """analyze_hybrid のエイリアス"""
        return self.analyze_hybrid(
            wav_input=wav_input,
            recognized_text=recognized_text,
            sense_emotion=sense_emotion,
        )


# ---------------------------------------------------------------------------
# シングルトンインスタンス保持
# ---------------------------------------------------------------------------
_HYBRID_INSTANCE: Optional[Qwen2AudioHybridAnalyzer] = None
_HYBRID_LOCK = threading.Lock()


def get_qwen2_audio_analyzer(model_id: str = DEFAULT_MODEL_ID) -> Qwen2AudioHybridAnalyzer:
    """Qwen2AudioHybridAnalyzer のシングルトンインスタンスを返す"""
    global _HYBRID_INSTANCE
    with _HYBRID_LOCK:
        if _HYBRID_INSTANCE is None:
            _HYBRID_INSTANCE = Qwen2AudioHybridAnalyzer(model_id=model_id)
        return _HYBRID_INSTANCE


def get_qwen2_audio_hybrid(model_id: str = DEFAULT_MODEL_ID) -> Qwen2AudioHybridAnalyzer:
    """get_qwen2_audio_analyzer の互換エイリアス"""
    return get_qwen2_audio_analyzer(model_id=model_id)


if __name__ == "__main__":
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Qwen2-Audio (4bit) + Gemma 4 e2b 2-Step ハイブリッド感情分析 CLI 単体テスト"
    )
    parser.add_argument(
        "wav",
        nargs="?",
        default=None,
        help="テストする WAV ファイルパス（省略時は test_assets 内のサンプルまたは合成有声波形を使用）",
    )
    parser.add_argument(
        "--text",
        default="おまえを一口で飲み込んでしまうためだ",
        help="参考セリフ文字列",
    )
    parser.add_argument(
        "--sense-emotion",
        default="NEUTRAL",
        help="SenseVoice 補助感情タグ (HAPPY/SAD/ANGRY/NEUTRAL 等)",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("[CLI Test] Qwen2-Audio (Step 1) + Gemma 4 e2b (Step 2) 2-Step ハイブリッド分析テスト")
    print("=" * 72)

    hybrid_analyzer = get_qwen2_audio_analyzer()
    print(f"[Step 0] 初期 VRAM 使用量: {hybrid_analyzer.get_vram_used_mb():.1f} MB")

    wav_source: Union[Path, np.ndarray]
    if args.wav and Path(args.wav).is_file():
        wav_source = Path(args.wav)
        print(f"[Input] 指定 WAV ファイルを使用: {wav_source}")
    else:
        sample_candidates = [
            Path(__file__).resolve().parent / "test_assets" / "calibrated_samples" / "latest_normal.wav",
            Path(__file__).resolve().parent / "test_assets" / "calibrated_samples" / "latest_power.wav",
            Path(__file__).resolve().parent / "test_assets" / "calibrated_samples" / "latest_whisper.wav",
        ]
        found_wav = next((p for p in sample_candidates if p.is_file()), None)
        if found_wav is not None:
            wav_source = found_wav
            print(f"[Input] 既存サンプル WAV を自動選択: {wav_source}")
        else:
            duration = 2.5
            t = np.linspace(0, duration, int(TARGET_SR * duration), endpoint=False, dtype=np.float32)
            f0_curve = 180.0 + 25.0 * np.sin(2.0 * np.pi * 1.5 * t)
            phase = 2.0 * np.pi * np.cumsum(f0_curve) / TARGET_SR
            synth = (
                0.35 * np.sin(phase)
                + 0.15 * np.sin(2.0 * phase)
                + 0.08 * np.sin(3.0 * phase)
                + 0.02 * np.random.default_rng(42).standard_normal(len(t))
            ).astype(np.float32)
            wav_source = synth
            print(f"[Input] ダミー有声波形を生成 (16kHz, {duration}秒)")

    print("\n--- [Step 1] 4bit 量子化モデルロード (ensure_loaded) ---")
    try:
        hybrid_analyzer.ensure_loaded()
        print(f"ロード状態: is_loaded={hybrid_analyzer.is_loaded} / VRAM={hybrid_analyzer.get_vram_used_mb():.1f} MB")
    except Exception as load_err:
        print(f"[WARN] モデルロード例外（フォールバック経路で継続テストします）: {load_err}")

    print("\n--- [Step 2] 2-Step ハイブリッド推論実行 (analyze_hybrid) ---")
    result = hybrid_analyzer.analyze_hybrid(
        wav_input=wav_source,
        recognized_text=args.text,
        sense_emotion=args.sense_emotion,
    )

    print("\n--- [Step 3] 出力確認 ---")
    print(f"[Step 1: Qwen2-Audio 感情・発声読み取り結果 (qwen2_perception_en)]:\n  {result['qwen2_perception_en']}")
    print(f"\n[Step 2 Input: Gemma 4 e2b 投入物理分析 (semantic_bridge_en)]:\n{result['semantic_bridge_en']}")
    print(f"\n[Step 2 Output: Primary={result['primary_emotion']['id']} ({result['primary_emotion']['score']}pt), Secondary={result['secondary_emotion']['id']} ({result['secondary_emotion']['score']}pt)]")
    print(f"  Scores (0-100): {json.dumps(result['emotions_12'], ensure_ascii=False)}")
    print(f"  Analysis Time: {result['analysis_time_sec']}s / VRAM: {result['vram_used_mb']} MB")

    print("\n--- [Step 4] モデルアンロード・VRAM 解放テスト (unload_model) ---")
    unload_info = hybrid_analyzer.unload_model()
    print(json.dumps(unload_info, ensure_ascii=False, indent=2))
    print("=" * 72)
