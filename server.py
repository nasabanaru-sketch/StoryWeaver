"""
StoryWeaver Live - Phase 3: FastAPI 2 段階エンドポイント
server.py

  POST /api/analyze_face   : 顔画像 -> ComfyUI /free -> VLM 外見抽出 (keep_alive:0)
  POST /api/generate_scene : 16kHz mono WAV -> SenseVoice(CPU) -> プロンプト統合 -> ComfyUI -> PNG

起動例:
  uvicorn server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import base64
import copy
import io
import json
import logging
import random
import re
import shutil
import sys
import time
import uuid
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Phase 1-A / 1-B の検証済みロジックを流用
from verify_step1_vlm import call_ollama_vlm, get_gpu_vram_mb, rule_based_transform
from verify_step1_sensevoice import (
    compute_rms_p90,
    determine_expression_category,
    extract_emotion_tag,
)
from voice_emo_analyzer import get_voice_emo_analyzer

BASE_DIR = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("storyweaver")

# ---------------------------------------------------------------------------
# 設定読み込み
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "BURNING_DB_THRESHOLD": -12.0,
    "OLLAMA_URL": "http://localhost:11434/api/generate",
    "OLLAMA_MODEL": "gemma4:e2b",
    "OLLAMA_TIMEOUT_SEC": 30,
    "OLLAMA_WARMUP_TIMEOUT_SEC": 120,
    "COMFYUI_URL": "http://localhost:8188",
    "COMFYUI_TIMEOUT_SEC": 500,
    "COMFYUI_INPUT_DIR": r"C:\pinokio\api\comfy.git\app\input",
    "WORKFLOW_PATH": "storyweaver_anime_api.json",
    "PRESETS_PATH": "presets.json",
    "OUTPUT_CARDS_DIR": "outputs/cards",
    "TEMP_AUDIO_DIR": "tmp_audio",
    "SENSEVOICE_MODEL": "iic/SenseVoiceSmall",
    "VRAM_STANDBY_MAX_MB": 8192,
    "VRAM_FREE_POLL_TIMEOUT_SEC": 10,
    "VRAM_FREE_STRICT": False,
    "SESSION_TTL_SEC": 900,
    "ANALYZE_WAIT_TIMEOUT_SEC": 120,
    "emotion_mode": "standard",
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    p = BASE_DIR / "config.json"
    if p.is_file():
        with open(p, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else BASE_DIR / p


CFG = load_config()
COMFY_URL = CFG["COMFYUI_URL"].rstrip("/")
COMFY_INPUT_DIR = _resolve(CFG["COMFYUI_INPUT_DIR"])
CARDS_DIR = _resolve(CFG["OUTPUT_CARDS_DIR"])
TEMP_AUDIO_DIR = _resolve(CFG["TEMP_AUDIO_DIR"])
FILE_PREFIX = "sw_"

with open(_resolve(CFG["PRESETS_PATH"]), "r", encoding="utf-8") as _f:
    PRESETS = {s["id"]: s for s in json.load(_f)["scenes"]}

QUALITY_TAGS = "masterpiece, best quality, very aesthetic, absurdres"
NEG_BASE = (
    "nsfw, lowres, (bad), text, error, fewer, extra, missing, worst quality, jpeg artifacts, "
    "low quality, watermark, unfinished, displeasing, oldest, early, chromatic aberration, "
    "signature, extra digits, artistic error, username, scan, [abstract], photorealistic, realistic, 3d"
)

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ALLOWED_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


# ---------------------------------------------------------------------------
# セッション管理
# ---------------------------------------------------------------------------
@dataclass
class Session:
    session_id: str
    image_path: Path
    created_at: float = field(default_factory=time.time)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    status: str = "analyzing"  # analyzing / ready / failed
    error_code: int = 500
    error_detail: str = ""
    result: dict = field(default_factory=dict)


SESSIONS: dict[str, Session] = {}
SENSEVOICE_MODEL = None
SENSEVOICE_LOCK = asyncio.Lock()
COMFY_LOCK = asyncio.Lock()  # 画像生成は同時1本のみ（VRAM スパイク防止）
BG_TASKS: set[asyncio.Task] = set()


def _safe_unlink(p: Optional[Path]) -> None:
    try:
        if p is not None and p.exists():
            p.unlink()
    except Exception as e:
        log.warning("一時ファイル削除失敗 %s: %s", p, e)


def discard_session(session_id: str) -> None:
    sess = SESSIONS.pop(session_id, None)
    if sess:
        _safe_unlink(sess.image_path)
        if not sess.done.is_set():
            sess.status = "failed"
            sess.error_detail = sess.error_detail or "SESSION_DISCARDED"
            sess.done.set()


async def session_reaper() -> None:
    """TTL を超えたセッションと一時画像を定期破棄する"""
    ttl = CFG["SESSION_TTL_SEC"]
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for sid in [s for s, v in SESSIONS.items() if now - v.created_at > ttl]:
            log.info("TTL 超過のセッションを破棄: %s", sid)
            discard_session(sid)


def sweep_stale_files() -> None:
    """起動時: 前回異常終了で残った一時ファイルを掃除"""
    for p in COMFY_INPUT_DIR.glob(f"{FILE_PREFIX}*") if COMFY_INPUT_DIR.is_dir() else []:
        _safe_unlink(p)
    if TEMP_AUDIO_DIR.is_dir():
        for p in TEMP_AUDIO_DIR.glob("*"):
            _safe_unlink(p)


# ---------------------------------------------------------------------------
# ウォームアップ / lifespan
# ---------------------------------------------------------------------------
def _ollama_warmup() -> None:
    try:
        t0 = time.perf_counter()
        r = requests.post(
            CFG["OLLAMA_URL"],
            json={"model": CFG["OLLAMA_MODEL"], "prompt": "ok", "stream": False, "keep_alive": 0},
            timeout=CFG["OLLAMA_WARMUP_TIMEOUT_SEC"],
        )
        log.info("Ollama ウォームアップ完了 HTTP %s (%.1fs)", r.status_code, time.perf_counter() - t0)
    except Exception as e:
        log.warning("Ollama ウォームアップ失敗（継続）: %s", e)


def _load_sensevoice():
    import os
    os.environ["MODELSCOPE_OFFLINE"] = "1"
    from funasr import AutoModel

    model_target = CFG["SENSEVOICE_MODEL"]
    # ローカルパス文字列またはパスが存在する場合はその絶対パスを利用
    local_p = Path(model_target)
    if not local_p.exists():
        # デフォルトキャッシュパスの探索
        default_cache = Path.home() / ".cache" / "modelscope" / "models" / "iic--SenseVoiceSmall" / "snapshots" / "master"
        if default_cache.exists():
            model_target = str(default_cache)
    else:
        model_target = str(local_p.resolve())

    return AutoModel(model=model_target, device="cpu", disable_update=True, log_level="ERROR")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global SENSEVOICE_MODEL
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    sweep_stale_files()

    log.info("SenseVoiceSmall を CPU でロード中...")
    SENSEVOICE_MODEL = await asyncio.to_thread(_load_sensevoice)
    log.info("SenseVoiceSmall ロード完了")

    log.info("VoiceEmoAnalyzer (12感情・色気モデル) を CPU でロード＆ウォームアップ中...")
    voice_analyzer = get_voice_emo_analyzer(device="cpu")
    await asyncio.to_thread(voice_analyzer.warmup)
    log.info("VoiceEmoAnalyzer ウォームアップ完了")

    warm = asyncio.create_task(asyncio.to_thread(_ollama_warmup))
    reaper = asyncio.create_task(session_reaper())
    BG_TASKS.update({warm, reaper})
    try:
        yield
    finally:
        reaper.cancel()
        for sid in list(SESSIONS):
            discard_session(sid)
        sweep_stale_files()


app = FastAPI(title="StoryWeaver Live API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# ComfyUI ヘルパ
# ---------------------------------------------------------------------------
def comfy_free_and_wait_vram() -> None:
    """ComfyUI のキャッシュを解放し、待機 VRAM が規定値以下になるまで待つ"""
    try:
        r = requests.post(
            f"{COMFY_URL}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=15,
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
    except Exception as e:
        raise HTTPException(503, f"COMFYUI_UNAVAILABLE: /free failed ({e})")

    limit = CFG["VRAM_STANDBY_MAX_MB"]
    deadline = time.time() + CFG["VRAM_FREE_POLL_TIMEOUT_SEC"]
    used = get_gpu_vram_mb()
    while used > limit and time.time() < deadline:
        time.sleep(0.5)
        used = get_gpu_vram_mb()
    if used < 0:
        log.warning("VRAM を取得できませんでした (nvidia-smi 不可)")
    elif used > limit:
        msg = f"待機 VRAM {used}MB が閾値 {limit}MB を下回りません"
        if CFG["VRAM_FREE_STRICT"]:
            raise HTTPException(503, f"VRAM_NOT_RELEASED: {msg}")
        log.warning(msg)
    else:
        log.info("ComfyUI /free 後の VRAM: %sMB (<= %sMB)", used, limit)


def build_workflow(image_filename: str, pos_base: str, neg_base: str, pos_fd: str) -> dict:
    with open(_resolve(CFG["WORKFLOW_PATH"]), "r", encoding="utf-8") as f:
        wf = json.load(f)
    wf = copy.deepcopy(wf)
    try:
        wf["12"]["inputs"]["image"] = image_filename
        wf["5"]["inputs"]["text"] = pos_base
        wf["6"]["inputs"]["text"] = neg_base
        wf["32"]["inputs"]["text"] = pos_fd
        seed = random.randint(0, 2**53 - 1)
        wf["2"]["inputs"]["seed"] = seed
        wf["20"]["inputs"]["seed"] = seed
    except KeyError as e:
        raise HTTPException(500, f"WORKFLOW_INVALID: node/key {e} not found")
    return wf


def comfy_run(workflow: dict) -> bytes:
    """ComfyUI にワークフローを送信し、完成画像のバイト列を返す（タイムアウト付き）"""
    timeout = CFG["COMFYUI_TIMEOUT_SEC"]
    try:
        r = requests.post(
            f"{COMFY_URL}/prompt",
            json={"prompt": workflow, "client_id": f"sw-{uuid.uuid4().hex[:8]}"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise HTTPException(503, f"COMFYUI_UNAVAILABLE: {e}")
    if r.status_code != 200:
        raise HTTPException(502, f"COMFYUI_REJECTED: HTTP {r.status_code} {r.text[:300]}")
    try:
        prompt_id = r.json()["prompt_id"]
    except Exception:
        raise HTTPException(502, "COMFYUI_BAD_RESPONSE: prompt_id missing")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.5)
        try:
            h = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
            hist = h.json().get(prompt_id) if h.status_code == 200 else None
        except (requests.RequestException, ValueError):
            hist = None
        if not hist:
            continue
        status = hist.get("status", {})
        if status.get("status_str") == "error":
            raise HTTPException(502, "COMFYUI_EXECUTION_ERROR")
        for node_out in hist.get("outputs", {}).values():
            for img in node_out.get("images", []):
                if img.get("type") == "output":
                    v = requests.get(
                        f"{COMFY_URL}/view",
                        params={
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""),
                            "type": "output",
                        },
                        timeout=30,
                    )
                    if v.status_code != 200 or not v.content:
                        raise HTTPException(502, "COMFYUI_VIEW_FAILED")
                    return v.content
        if status.get("completed"):
            raise HTTPException(502, "COMFYUI_NO_OUTPUT_IMAGE")

    try:
        requests.post(f"{COMFY_URL}/interrupt", timeout=5)
    except requests.RequestException:
        pass
    raise HTTPException(504, f"COMFYUI_TIMEOUT: {timeout}s 超過")


# ---------------------------------------------------------------------------
# 音声検証
# ---------------------------------------------------------------------------
def validate_wav_16k_mono_pcm16(data: bytes) -> None:
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise HTTPException(415, "UNSUPPORTED_AUDIO: WAV (RIFF/WAVE) ではありません")
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            ch, rate, width, comp = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getcomptype()
    except (wave.Error, EOFError) as e:
        raise HTTPException(415, f"UNSUPPORTED_AUDIO: WAV 解析失敗 ({e})")
    if comp != "NONE" or width != 2 or ch != 1 or rate != 16000:
        raise HTTPException(
            415,
            f"UNSUPPORTED_AUDIO: 16kHz モノラル 16bit PCM のみ対応 (ch={ch}, rate={rate}, bits={width * 8}, comp={comp})",
        )


# ---------------------------------------------------------------------------
# POST /api/analyze_face
# ---------------------------------------------------------------------------
def _analyze_blocking(sess: Session) -> None:
    comfy_free_and_wait_vram()
    try:
        res = call_ollama_vlm(
            sess.image_path,
            model=CFG["OLLAMA_MODEL"],
            ollama_url=CFG["OLLAMA_URL"],
            timeout=CFG["OLLAMA_TIMEOUT_SEC"],
        )
    except requests.Timeout:
        raise HTTPException(504, "OLLAMA_TIMEOUT")
    except requests.RequestException as e:
        raise HTTPException(503, f"OLLAMA_UNAVAILABLE: {e}")
    except RuntimeError as e:
        raise HTTPException(502, f"OLLAMA_ERROR: {e}")

    validated = res["validated"]
    if validated is None:
        raise HTTPException(502, f"VLM_SCHEMA_ERROR: {res['validation_error']}")
    if not validated.face_detected:
        raise HTTPException(422, "FACE_NOT_DETECTED")

    traits, neg_bias, warnings = rule_based_transform(validated)
    raw_vlm = validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
    sess.result = {
        "session_id": sess.session_id,
        "image_filename": sess.image_path.name,
        "face_detected": True,
        "gender_tag": validated.gender_tag,
        "physical_traits": traits,
        "negative_hair_bias": neg_bias,
        "vlm_extraction": raw_vlm,
        "vlm_metrics": {
            "wall_time_ms": res["wall_time_ms"],
            "load_duration_ms": res["load_duration_ms"],
            "eval_duration_ms": res["eval_duration_ms"],
            "vram_used_mb": res["vram_used_mb"],
            "expression_warnings": warnings,
        },
    }


@app.post("/api/analyze_face")
async def analyze_face(face_image: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    sid = session_id or uuid.uuid4().hex[:12]
    if not SESSION_ID_RE.match(sid):
        raise HTTPException(400, "INVALID_SESSION_ID")
    if sid in SESSIONS:
        raise HTTPException(409, "SESSION_ALREADY_EXISTS")

    ext = Path(face_image.filename or "").suffix.lower()
    if ext not in ALLOWED_IMG_EXT:
        ext = ".jpg"
    data = await face_image.read()
    if not data:
        raise HTTPException(400, "EMPTY_IMAGE")

    COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    img_path = COMFY_INPUT_DIR / f"{FILE_PREFIX}{sid}{ext}"
    sess = Session(session_id=sid, image_path=img_path)
    SESSIONS[sid] = sess
    try:
        img_path.write_bytes(data)
        await asyncio.to_thread(_analyze_blocking, sess)
        sess.status = "ready"
        return sess.result
    except HTTPException as e:
        log.warning("analyze_face HTTP %s: %s", e.status_code, e.detail)
        sess.status, sess.error_code, sess.error_detail = "failed", e.status_code, str(e.detail)
        discard_session(sid)  # 画像削除 + 待機中 generate を解放
        raise
    except Exception as e:
        log.exception("analyze_face 予期せぬエラー")
        sess.status, sess.error_code, sess.error_detail = "failed", 500, f"INTERNAL_ERROR: {e}"
        discard_session(sid)
        raise HTTPException(500, f"INTERNAL_ERROR: {e}")
    finally:
        sess.done.set()


# ---------------------------------------------------------------------------
# POST /api/generate_scene
# ---------------------------------------------------------------------------
def _strip_gender(traits: str, gender: str) -> str:
    items = [t.strip() for t in traits.split(",") if t.strip() and t.strip() != gender]
    return ", ".join(items)


def _infer_emotion(wav_path: Path) -> tuple[str, float, str, str]:
    rms_p90, _, _ = compute_rms_p90(wav_path)
    res = SENSEVOICE_MODEL.generate(input=str(wav_path), cache={}, language="auto", use_itn=True)
    raw = ""
    if isinstance(res, list) and res:
        raw = res[0].get("text", "")
    elif isinstance(res, dict):
        raw = res.get("text", "")
    emotion = extract_emotion_tag(raw)
    category, expr, _ = determine_expression_category(emotion, rms_p90, CFG["BURNING_DB_THRESHOLD"])
    return category, rms_p90, expr, emotion


TAG_RE = re.compile(r"<\|.*?\|>")


def clean_sensevoice_text(text: str) -> str:
    cleaned = TAG_RE.sub("", text)
    return cleaned.strip()


@app.get("/api/presets")
async def get_presets():
    return {"scenes": list(PRESETS.values())}


@app.put("/api/presets")
async def update_presets(payload: dict = Body(...)):
    global PRESETS
    scenes = payload.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        raise HTTPException(400, "scenes list is required")
    for s in scenes:
        if not isinstance(s, dict) or not s.get("id") or not s.get("name"):
            raise HTTPException(400, "invalid scene format: 'id' and 'name' are required")
    presets_file = _resolve(CFG["PRESETS_PATH"])
    with open(presets_file, "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes}, f, ensure_ascii=False, indent=2)
    PRESETS = {s["id"]: s for s in scenes}
    log.info("プリセットを更新しました (%d 件)", len(scenes))
    return {"status": "ok", "scenes": scenes}


@app.get("/api/config")
async def get_config():
    return CFG


@app.put("/api/config")
async def update_config(payload: dict = Body(...)):
    global CFG
    if not isinstance(payload, dict):
        raise HTTPException(400, "config object required")
    for k, v in payload.items():
        if k in CFG:
            if isinstance(CFG[k], float) and isinstance(v, (int, float)):
                CFG[k] = float(v)
            elif isinstance(CFG[k], int) and isinstance(v, (int, float)):
                CFG[k] = int(v)
            elif isinstance(CFG[k], bool) and isinstance(v, bool):
                CFG[k] = v
            else:
                CFG[k] = v
    config_file = BASE_DIR / "config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(CFG, f, ensure_ascii=False, indent=2)
    log.info("設定を更新しました: %s", payload)
    return {"status": "ok", "config": CFG}


@app.get("/api/voice_emo_baseline")
async def get_voice_emo_baseline():
    analyzer = get_voice_emo_analyzer()
    return {"baseline": analyzer.baseline}


@app.post("/api/calibrate_voice_emo")
async def calibrate_voice_emo(audio_file: UploadFile = File(...)):
    wav_path: Optional[Path] = None
    try:
        audio = await audio_file.read()
        validate_wav_16k_mono_pcm16(audio)
        TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        wav_path = TEMP_AUDIO_DIR / f"calib_{uuid.uuid4().hex}.wav"
        wav_path.write_bytes(audio)

        analyzer = get_voice_emo_analyzer()
        new_baseline = await asyncio.to_thread(analyzer.calibrate_baseline, [wav_path])
        return {"status": "ok", "baseline": new_baseline}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("calibrate_voice_emo エラー")
        raise HTTPException(500, f"CALIBRATION_FAILED: {e}")
    finally:
        _safe_unlink(wav_path)


@app.post("/api/analyze_audio")
async def analyze_audio(audio_file: UploadFile = File(...)):
    wav_path: Optional[Path] = None
    try:
        audio = await audio_file.read()
        validate_wav_16k_mono_pcm16(audio)
        TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        wav_path = TEMP_AUDIO_DIR / f"{uuid.uuid4().hex}.wav"
        wav_path.write_bytes(audio)

        # 1) SenseVoiceSmall による文字起こし（常に実行）
        async with SENSEVOICE_LOCK:
            rms_p90, _, _ = compute_rms_p90(wav_path)
            res = SENSEVOICE_MODEL.generate(input=str(wav_path), cache={}, language="auto", use_itn=True)
            raw = ""
            if isinstance(res, list) and res:
                raw = res[0].get("text", "")
            elif isinstance(res, dict):
                raw = res.get("text", "")
            recognized_text = clean_sensevoice_text(raw)
            sense_emo = extract_emotion_tag(raw)

        # 2) 感情判定モードの分岐
        emotion_mode = CFG.get("emotion_mode", "standard")

        if emotion_mode == "detailed_12":
            # 12感情・色気スコア分析 (wav2vec2 + openSMILE)
            analyzer = get_voice_emo_analyzer()
            res_emo = await asyncio.to_thread(analyzer.analyze, wav_path)
            top1 = res_emo["primary_emotion"]
            top2 = res_emo["secondary_emotion"]

            return {
                "emotion_mode": "detailed_12",
                "recognized_text": recognized_text,
                "emotion": top1["name_ja"],
                "rms_db": rms_p90,
                "expression_state": top1["id"],
                "expression_prompt": res_emo["expression_prompt"],
                "expression_prompt_fd": res_emo["expression_prompt_fd"],
                "primary_emotion": top1,
                "secondary_emotion": top2,
                "features_7": res_emo["features_7"],
                "emotions_12": res_emo["emotions_12"],
                "analysis_time_sec": res_emo["analysis_time_sec"],
            }
        else:
            # 従来の SenseVoice 5段階判定
            category, expr, _ = determine_expression_category(
                sense_emo, rms_p90, CFG["BURNING_DB_THRESHOLD"]
            )
            return {
                "emotion_mode": "standard",
                "recognized_text": recognized_text,
                "emotion": sense_emo,
                "rms_db": rms_p90,
                "expression_state": category,
                "expression_prompt": expr,
                "expression_prompt_fd": expr,
            }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("analyze_audio 予期せぬエラー")
        raise HTTPException(500, f"INTERNAL_ERROR: {e}")
    finally:
        _safe_unlink(wav_path)


@app.post("/api/generate_scene")
async def generate_scene(
    audio_file: Optional[UploadFile] = File(None),
    scene_id: str = Form(...),
    session_id: str = Form(...),
    final_script_text: Optional[str] = Form(None),
    expression_prompt: Optional[str] = Form(None),
    expression_prompt_fd: Optional[str] = Form(None),
    expression_state: Optional[str] = Form(None),
    emotion: Optional[str] = Form(None),
    rms_db: Optional[float] = Form(None),
):
    wav_path: Optional[Path] = None
    consume = False
    try:
        # 1) 音声フォーマット検証 (音声ファイルが送信されている場合)
        if audio_file is not None:
            audio = await audio_file.read()
            validate_wav_16k_mono_pcm16(audio)
            TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            wav_path = TEMP_AUDIO_DIR / f"{uuid.uuid4().hex}.wav"
            wav_path.write_bytes(audio)
        elif not expression_prompt:
            raise HTTPException(400, "audio_file または expression_prompt の指定が必要です")

        if scene_id not in PRESETS:
            raise HTTPException(404, f"SCENE_NOT_FOUND: {scene_id}")
        if not SESSION_ID_RE.match(session_id):
            raise HTTPException(400, "INVALID_SESSION_ID")
        preset = PRESETS[scene_id]

        # 2) analyze の完了待機
        sess = SESSIONS.get(session_id)
        if sess is None:
            raise HTTPException(404, "SESSION_NOT_FOUND")
        try:
            await asyncio.wait_for(sess.done.wait(), timeout=CFG["ANALYZE_WAIT_TIMEOUT_SEC"])
        except asyncio.TimeoutError:
            discard_session(session_id)
            raise HTTPException(504, "ANALYZE_WAIT_TIMEOUT")
        if sess.status != "ready":
            raise HTTPException(sess.error_code if sess.error_code else 409, sess.error_detail or "SESSION_NOT_READY")

        consume = True  # ここから先は成否にかかわらずセッションを使い切る

        # 3) 感情・声量
        expr_fd = None
        if expression_prompt:
            expr = expression_prompt
            expr_fd = expression_prompt_fd or expr
            category = expression_state or "BURNING"
            rms_val = rms_db if rms_db is not None else 0.0
            emo_val = emotion or "NEUTRAL"
        else:
            if CFG.get("emotion_mode", "standard") == "detailed_12":
                voice_analyzer = get_voice_emo_analyzer()
                res_emo = await asyncio.to_thread(voice_analyzer.analyze, wav_path)
                expr = res_emo["expression_prompt"]
                expr_fd = res_emo["expression_prompt_fd"]
                category = res_emo["primary_emotion"]["id"]
                emo_val = res_emo["primary_emotion"]["name_ja"]
                async with SENSEVOICE_LOCK:
                    rms_val, _, _ = compute_rms_p90(wav_path)
            else:
                async with SENSEVOICE_LOCK:
                    category, rms_val, expr, emo_val = await asyncio.to_thread(_infer_emotion, wav_path)
                    expr_fd = expr

        # 4) プロンプト統合 (README §3.3 / FaceDetailer 案B 表情専用注入)
        gender = sess.result["gender_tag"]
        traits = _strip_gender(sess.result["physical_traits"], gender)
        neg_bias = sess.result["negative_hair_bias"]
        pos_base = ", ".join(
            p for p in [gender, "solo", traits, expr, preset["scene_prompt"], QUALITY_TAGS] if p
        )
        neg_base = f"{neg_bias}, {NEG_BASE}" if neg_bias else NEG_BASE
        pos_fd = f"{gender}, solo, close-up, face focus, {expr_fd}, detailed anime eyes, {QUALITY_TAGS}"

        # 5) ComfyUI 生成
        workflow = build_workflow(sess.image_path.name, pos_base, neg_base, pos_fd)
        async with COMFY_LOCK:
            png = await asyncio.to_thread(comfy_run, workflow)

        CARDS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CARDS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{session_id}_{scene_id}.png"
        out_path.write_bytes(png)
        script_to_return = final_script_text.strip() if (final_script_text and final_script_text.strip()) else preset["script_text"]
        log.info("カード保存: %s (emotion=%s/%s, rms=%.1fdB)", out_path.name, emo_val, category, rms_val)

        return {
            "imageBase64": base64.b64encode(png).decode("ascii"),
            "emotion": category,
            "rms_db": rms_val,
            "script_text": script_to_return,
            "final_prompt": pos_base,
            "expression_prompt_fd": expr_fd,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("generate_scene 予期せぬエラー")
        raise HTTPException(500, f"INTERNAL_ERROR: {e}")
    finally:
        _safe_unlink(wav_path)  # 一時音声は必ず削除
        # 1 セッション 1 生成: 成功/失敗にかかわらず顔画像とセッションを破棄
        if consume:
            discard_session(session_id)


@app.post("/api/generate_custom")
async def generate_custom(
    face_image: Optional[UploadFile] = File(None),
    image_filename: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    pos_base: str = Form(...),
    neg_base: str = Form(...),
    pos_fd: str = Form(...),
    scene_id: Optional[str] = Form("custom"),
    script_text: Optional[str] = Form(""),
):
    """作りこみワークベンチ用: 編集済みプロンプト3系統をComfyUIへ注入し生成"""
    temp_target_path: Optional[Path] = None
    target_img_filename: str = ""

    try:
        # 画像の特定: アップロードされた画像、または既存セッション/入力画像
        if face_image is not None:
            data = await face_image.read()
            if not data:
                raise HTTPException(400, "EMPTY_IMAGE")
            ext = Path(face_image.filename or "").suffix.lower()
            if ext not in ALLOWED_IMG_EXT:
                ext = ".jpg"
            sid = session_id or uuid.uuid4().hex[:12]
            COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)
            temp_target_path = COMFY_INPUT_DIR / f"{FILE_PREFIX}wb_{sid}{ext}"
            temp_target_path.write_bytes(data)
            target_img_filename = temp_target_path.name
        elif image_filename:
            target_img_filename = image_filename
            full_p = COMFY_INPUT_DIR / image_filename
            if not full_p.is_file():
                # test_assets/faces などにある場合のコピー
                src_test = BASE_DIR / "test_assets" / "faces" / image_filename
                if src_test.is_file():
                    COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_test, full_p)
                else:
                    raise HTTPException(404, f"IMAGE_NOT_FOUND: {image_filename}")
        elif session_id and session_id in SESSIONS:
            sess = SESSIONS[session_id]
            target_img_filename = sess.image_path.name
            if not sess.image_path.is_file():
                raise HTTPException(404, "SESSION_IMAGE_MISSING")
        else:
            raise HTTPException(400, "face_image, image_filename, または有効な session_id が必要です")

        log.info(
            "generate_custom 開始: img=%s, pos_base_len=%d, neg_len=%d, fd_len=%d",
            target_img_filename,
            len(pos_base),
            len(neg_base),
            len(pos_fd),
        )

        workflow = build_workflow(target_img_filename, pos_base, neg_base, pos_fd)
        async with COMFY_LOCK:
            png = await asyncio.to_thread(comfy_run, workflow)

        CARDS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_scene = re.sub(r"[^A-Za-z0-9_-]", "_", scene_id or "custom")
        out_filename = f"{timestamp_str}_workbench_{safe_scene}.png"
        out_path = CARDS_DIR / out_filename
        out_path.write_bytes(png)
        log.info("generate_custom 完了・保存: %s", out_path.name)

        return {
            "status": "ok",
            "imageBase64": base64.b64encode(png).decode("ascii"),
            "saved_filename": out_filename,
            "saved_path": str(out_path),
            "script_text": script_text or "",
            "pos_base": pos_base,
            "neg_base": neg_base,
            "pos_fd": pos_fd,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("generate_custom 予期せぬエラー")
        raise HTTPException(500, f"INTERNAL_ERROR: {e}")
    finally:
        # アップロードされた画像が一時生成されたものであれば削除
        if temp_target_path is not None:
            _safe_unlink(temp_target_path)


@app.get("/api/health")
async def health():
    return {"status": "ok", "sessions": len(SESSIONS), "sensevoice_loaded": SENSEVOICE_MODEL is not None}


# ---------------------------------------------------------------------------
# 静的ファイル配信 (UI)
# ---------------------------------------------------------------------------
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {"message": "StoryWeaver Live API is running. UI under /static/"}


@app.get("/workbench")
async def workbench():
    wb_file = STATIC_DIR / "workbench.html"
    if wb_file.is_file():
        return FileResponse(wb_file)
    return {"message": "Workbench UI under /static/workbench.html"}


