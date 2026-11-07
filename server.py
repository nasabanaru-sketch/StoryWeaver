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

import cv2
import numpy as np
from PIL import Image, ImageOps
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
from qwen2_audio_hybrid import (
    get_ollama_model_status,
    get_qwen2_audio_analyzer,
    preload_ollama_model,
    unload_ollama_model,
)

BASE_DIR = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("storyweaver")

# ---------------------------------------------------------------------------
# 設定読み込み
# ---------------------------------------------------------------------------
ALLOWED_EMOTION_MODES = ("standard", "detailed_12", "qwen2_audio_hybrid")

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
    "CAPTURED_FACES_DIR": "outputs/captured_faces",
    "TEMP_AUDIO_DIR": "tmp_audio",
    "SENSEVOICE_MODEL": "iic/SenseVoiceSmall",
    "VRAM_STANDBY_MAX_MB": 8192,
    "VRAM_FREE_POLL_TIMEOUT_SEC": 10,
    "VRAM_FREE_STRICT": False,
    "SESSION_TTL_SEC": 900,
    "ANALYZE_WAIT_TIMEOUT_SEC": 120,
    "emotion_mode": "standard",
    "QWEN2_AUDIO_MODEL": "Qwen/Qwen2-Audio-7B-Instruct",
    "QWEN2_AUDIO_AUTO_UNLOAD": True,
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
CAPTURED_FACES_DIR = _resolve(CFG["CAPTURED_FACES_DIR"])
TEMP_AUDIO_DIR = _resolve(CFG["TEMP_AUDIO_DIR"])
FILE_PREFIX = "sw_"

with open(_resolve(CFG["PRESETS_PATH"]), "r", encoding="utf-8") as _f:
    PRESETS = {}
    for _s in json.load(_f)["scenes"]:
        _s.setdefault("scene_neg_prompt", "")
        PRESETS[_s["id"]] = _s

QUALITY_TAGS = "masterpiece, best quality, very aesthetic, absurdres"
NEG_BASE = (
    "nsfw, lowres, (bad), text, error, fewer, extra, missing, worst quality, jpeg artifacts, "
    "low quality, watermark, unfinished, displeasing, oldest, early, chromatic aberration, "
    "signature, extra digits, artistic error, username, scan, [abstract], photorealistic, realistic, 3d"
)

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ALLOWED_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

AVAILABLE_WORKFLOWS = [
    {
        "filename": "storyweaver_anime_api.json",
        "label": "標準 (FaceDetailer あり / 30+20 steps)",
        "has_fd": True,
    },
    {
        "filename": "storyweaver_anime_nofd_api.json",
        "label": "高速 (FaceDetailer なし / 30 steps)",
        "has_fd": False,
    },
]
ALLOWED_WORKFLOW_FILES = {w["filename"] for w in AVAILABLE_WORKFLOWS}


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
    prompt_cache: dict = field(default_factory=dict)


SESSIONS: dict[str, Session] = {}
SENSEVOICE_MODEL = None
SENSEVOICE_LOCK = asyncio.Lock()
QWEN2_LOCK = asyncio.Lock()  # Qwen2-Audio のロード・推論・アンロード排他制御
COMFY_LOCK = asyncio.Lock()  # 画像生成は同時1本のみ（VRAM スパイク防止）
BG_TASKS: set[asyncio.Task] = set()


def unload_qwen2_audio_if_loaded() -> dict:
    """Qwen2-Audio が VRAM 上にロードされている場合、即座にアンロードして VRAM を解放する"""
    try:
        qwen_analyzer = get_qwen2_audio_analyzer(
            model_id=CFG.get("QWEN2_AUDIO_MODEL", DEFAULT_CONFIG["QWEN2_AUDIO_MODEL"])
        )
        if qwen_analyzer.is_loaded or qwen_analyzer.model is not None or qwen_analyzer.processor is not None:
            info = qwen_analyzer.unload_model()
            log.info(
                "unload_qwen2_audio_if_loaded: VRAM 解放完了 (%.1f MB -> %.1f MB)",
                info.get("vram_before_mb", 0.0),
                info.get("vram_after_mb", 0.0),
            )
            return info
        return {
            "was_loaded": False,
            "vram_before_mb": qwen_analyzer.get_vram_used_mb(),
            "vram_after_mb": qwen_analyzer.get_vram_used_mb(),
        }
    except Exception as e:
        log.warning("unload_qwen2_audio_if_loaded 実行中に警告: %s", e)
        return {"was_loaded": False, "error": str(e)}


def unload_ollama_if_loaded() -> dict:
    """Ollama (Gemma 4 e2b) が VRAM 上にロードされている場合、keep_alive=0 で即座にアンロードする"""
    try:
        return unload_ollama_model(
            ollama_url=CFG.get("OLLAMA_URL", DEFAULT_CONFIG["OLLAMA_URL"]),
            ollama_model=CFG.get("OLLAMA_MODEL", DEFAULT_CONFIG["OLLAMA_MODEL"]),
        )
    except Exception as e:
        log.warning("unload_ollama_if_loaded 実行中に警告: %s", e)
        return {"was_loaded": False, "error": str(e)}


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
    """起動時: 前回異常終了で残った一時ファイルを掃除（sw_crop_ は保持）"""
    for p in COMFY_INPUT_DIR.glob(f"{FILE_PREFIX}*") if COMFY_INPUT_DIR.is_dir() else []:
        if p.name.startswith("sw_crop_"):
            continue
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
    CAPTURED_FACES_DIR.mkdir(parents=True, exist_ok=True)
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
        unload_qwen2_audio_if_loaded()
        unload_ollama_if_loaded()
        for sid in list(SESSIONS):
            discard_session(sid)
        sweep_stale_files()


app = FastAPI(title="StoryWeaver Live API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# ComfyUI ヘルパ
# ---------------------------------------------------------------------------
def comfy_free_and_wait_vram() -> None:
    """ComfyUI のキャッシュを解放し、待機 VRAM が規定値以下になるまで待つ
    （※ Qwen2-Audio や Ollama がスタンバイ常駐中の場合は、それらの使用 VRAM 分を許容閾値に加算する）
    """
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

    qwen_vram_mb = 0.0
    ollama_vram_mb = 0.0
    try:
        qwen_analyzer = get_qwen2_audio_analyzer(
            model_id=CFG.get("QWEN2_AUDIO_MODEL", DEFAULT_CONFIG["QWEN2_AUDIO_MODEL"])
        )
        qwen_vram_mb = float(qwen_analyzer.get_vram_used_mb())
    except Exception:
        pass
    try:
        ol_st = get_ollama_model_status(
            CFG.get("OLLAMA_URL"), CFG.get("OLLAMA_MODEL"), timeout_sec=2
        )
        ollama_vram_mb = float(ol_st.get("vram_used_mb", 0.0))
    except Exception:
        pass

    limit = CFG["VRAM_STANDBY_MAX_MB"] + qwen_vram_mb + ollama_vram_mb
    deadline = time.time() + CFG["VRAM_FREE_POLL_TIMEOUT_SEC"]
    used = get_gpu_vram_mb()
    while used > limit and time.time() < deadline:
        time.sleep(0.5)
        used = get_gpu_vram_mb()
    if used < 0:
        log.warning("VRAM を取得できませんでした (nvidia-smi 不可)")
    elif used > limit:
        msg = f"待機 VRAM {used}MB が閾値 {limit:.0f}MB を下回りません"
        if CFG["VRAM_FREE_STRICT"]:
            raise HTTPException(503, f"VRAM_NOT_RELEASED: {msg}")
        log.warning(msg)
    else:
        log.info(
            "ComfyUI /free 後の VRAM: %sMB (<= %.0fMB [base=%s + qwen=%.0f + ollama=%.0f])",
            used,
            limit,
            CFG["VRAM_STANDBY_MAX_MB"],
            qwen_vram_mb,
            ollama_vram_mb,
        )


def build_workflow(
    image_filename: str,
    pos_base: str,
    neg_base: str,
    pos_fd: str = "",
    workflow_filename: Optional[str] = None,
) -> dict:
    target_wf = workflow_filename or CFG["WORKFLOW_PATH"]
    if target_wf not in ALLOWED_WORKFLOW_FILES:
        raise HTTPException(400, f"INVALID_WORKFLOW_FILE: {target_wf}")
    wf_path = _resolve(target_wf)
    if not wf_path.is_file():
        raise HTTPException(404, f"WORKFLOW_FILE_NOT_FOUND: {target_wf}")
    with open(wf_path, "r", encoding="utf-8") as f:
        wf = json.load(f)
    wf = copy.deepcopy(wf)
    try:
        wf["12"]["inputs"]["image"] = image_filename
        wf["5"]["inputs"]["text"] = pos_base
        wf["6"]["inputs"]["text"] = neg_base
        if "32" in wf:
            wf["32"]["inputs"]["text"] = pos_fd
        seed = random.randint(0, 2**53 - 1)
        wf["2"]["inputs"]["seed"] = seed
        if "20" in wf:
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
# 顔画像クロップ（頭頂部の髪〜肩）
# ---------------------------------------------------------------------------
def crop_head_and_shoulders(image_bytes: bytes, ext: str = ".jpg") -> bytes:
    """カメラ撮影画像から顔を検出し、頭頂部の髪から肩までが収まる正方形にクロップする。
    未検出時は短辺中央正方形クロップにフォールバック。1024px を超える場合はリサイズ。
    """
    pil_img = Image.open(io.BytesIO(image_bytes))
    pil_img = ImageOps.exif_transpose(pil_img)
    pil_img = pil_img.convert("RGB")
    img_w, img_h = pil_img.size

    np_img = np.array(pil_img)
    gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60),
    )

    if len(faces) > 0:
        faces_sorted = sorted(faces, key=lambda f: int(f[2]) * int(f[3]), reverse=True)
        x, y, w, h = faces_sorted[0]
        cx = x + w * 0.5
        cy = y + h * 0.45
        side = int(max(w, h) * 2.2)
        side = min(side, img_w, img_h)
        x1 = int(round(cx - side / 2))
        y1 = int(round(cy - side / 2))
        x1 = max(0, min(x1, img_w - side))
        y1 = max(0, min(y1, img_h - side))
        cropped = pil_img.crop((x1, y1, x1 + side, y1 + side))
        log.info(
            "crop_head_and_shoulders: 顔検出 (w=%d, h=%d) -> crop side=%d (x1=%d, y1=%d)",
            w, h, side, x1, y1,
        )
    else:
        side = min(img_w, img_h)
        x1 = int(round((img_w - side) / 2))
        y1 = int(round((img_h - side) / 2))
        x1 = max(0, min(x1, img_w - side))
        y1 = max(0, min(y1, img_h - side))
        cropped = pil_img.crop((x1, y1, x1 + side, y1 + side))
        log.info(
            "crop_head_and_shoulders: 顔未検出のため中央クロップへフォールバック (side=%d, x1=%d, y1=%d)",
            side, x1, y1,
        )

    if cropped.width > 1024 or cropped.height > 1024:
        cropped = cropped.resize((1024, 1024), Image.Resampling.LANCZOS)

    out_buf = io.BytesIO()
    fmt = ext.lower().lstrip(".")
    if fmt in ["jpg", "jpeg"]:
        cropped.save(out_buf, format="JPEG", quality=95)
    elif fmt == "png":
        cropped.save(out_buf, format="PNG")
    elif fmt == "webp":
        cropped.save(out_buf, format="WEBP", quality=95)
    else:
        cropped.save(out_buf, format="JPEG", quality=95)

    return out_buf.getvalue()


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
    # Step 1 でスタンバイした Qwen2-Audio はアンロードせず維持し、
    # Gemma 4 e2b も Step 3 の音声感情分析が終わるまで VRAM に保持する (keep_alive="15m")
    try:
        res = call_ollama_vlm(
            sess.image_path,
            model=CFG["OLLAMA_MODEL"],
            ollama_url=CFG["OLLAMA_URL"],
            timeout=CFG["OLLAMA_TIMEOUT_SEC"],
            keep_alive="15m",
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
    cropped_data = crop_head_and_shoulders(data, ext)

    COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    img_path = COMFY_INPUT_DIR / f"{FILE_PREFIX}{sid}{ext}"
    sess = Session(session_id=sid, image_path=img_path)
    SESSIONS[sid] = sess
    try:
        img_path.write_bytes(cropped_data)
        await asyncio.to_thread(_analyze_blocking, sess)
        sess.result["cropped_image_base64"] = base64.b64encode(cropped_data).decode("ascii")
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


SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


@app.post("/api/capture_cropped_face")
async def capture_cropped_face(
    face_image: UploadFile = File(...),
):
    """カメラ撮影画像を頭髪〜肩の正方形にクロップし、CAPTURED_FACES_DIR と COMFY_INPUT_DIR の両方に保存・プレビュー返却する"""
    data = await face_image.read()
    if not data:
        raise HTTPException(400, "EMPTY_IMAGE")

    try:
        cropped_bytes = crop_head_and_shoulders(data, ".jpg")
    except Exception as e:
        log.exception("capture_cropped_face クロップ失敗")
        raise HTTPException(400, f"IMAGE_PROCESSING_FAILED: {e}")

    CAPTURED_FACES_DIR.mkdir(parents=True, exist_ok=True)
    COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    created_at = now.isoformat(timespec="seconds")
    filename = f"sw_crop_{timestamp_str}_{uuid.uuid4().hex[:6]}.jpg"

    saved_path = CAPTURED_FACES_DIR / filename
    saved_path.write_bytes(cropped_bytes)
    shutil.copy2(saved_path, COMFY_INPUT_DIR / filename)

    b64_str = base64.b64encode(cropped_bytes).decode("ascii")
    log.info("撮影顔画像保存 (CAPTURED_FACES_DIR & COMFY_INPUT_DIR): %s", filename)
    return {
        "status": "ok",
        "image_filename": filename,
        "cropped_image_base64": b64_str,
        "created_at": created_at,
    }


@app.get("/api/captured_faces")
async def list_captured_faces():
    """CAPTURED_FACES_DIR 内のクロップ済み画像ファイル一覧（新しい順、最大30件）を返す"""
    CAPTURED_FACES_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        p for p in CAPTURED_FACES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_IMG_EXT
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for p in files[:30]:
        mtime_iso = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        items.append({
            "image_filename": p.name,
            "url": f"/api/captured_faces/{p.name}",
            "created_at": mtime_iso,
        })
    return {"status": "ok", "faces": items}


@app.get("/api/captured_faces/{filename}")
async def get_captured_face(filename: str):
    """指定されたクロップ済み画像ファイルを FileResponse で返す（パストラバーサル防止検証付き）"""
    if not SAFE_FILENAME_RE.match(filename) or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "INVALID_FILENAME")
    target = (CAPTURED_FACES_DIR / filename).resolve()
    if target.parent != CAPTURED_FACES_DIR.resolve() or not target.is_file():
        raise HTTPException(404, "CAPTURED_FACE_NOT_FOUND")
    return FileResponse(target)


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
        s.setdefault("scene_neg_prompt", "")
        if not isinstance(s["scene_neg_prompt"], str):
            s["scene_neg_prompt"] = str(s["scene_neg_prompt"] or "")
    presets_file = _resolve(CFG["PRESETS_PATH"])
    with open(presets_file, "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes}, f, ensure_ascii=False, indent=2)
    PRESETS = {s["id"]: s for s in scenes}
    log.info("プリセットを更新しました (%d 件)", len(scenes))
    return {"status": "ok", "scenes": scenes}


@app.get("/api/workflows")
async def get_workflows():
    workflows = []
    for item in AVAILABLE_WORKFLOWS:
        wf_path = _resolve(item["filename"])
        workflows.append({**item, "exists": wf_path.is_file()})
    return {
        "workflows": workflows,
        "current_workflow": CFG.get("WORKFLOW_PATH", "storyweaver_anime_api.json"),
    }


@app.get("/api/config")
async def get_config():
    return CFG


@app.put("/api/config")
async def update_config(payload: dict = Body(...)):
    global CFG
    if not isinstance(payload, dict):
        raise HTTPException(400, "config object required")
    if "WORKFLOW_PATH" in payload:
        wf_val = payload["WORKFLOW_PATH"]
        if not isinstance(wf_val, str) or wf_val not in ALLOWED_WORKFLOW_FILES:
            raise HTTPException(400, f"INVALID_WORKFLOW_FILE: {wf_val}")
    if "emotion_mode" in payload:
        em_val = payload["emotion_mode"]
        if not isinstance(em_val, str) or em_val not in ALLOWED_EMOTION_MODES:
            raise HTTPException(
                400,
                f"INVALID_EMOTION_MODE: emotion_mode は {ALLOWED_EMOTION_MODES} のいずれかを指定してください (指定値: {em_val})",
            )
    for k, v in payload.items():
        if k in CFG:
            if isinstance(CFG[k], float) and isinstance(v, (int, float)):
                CFG[k] = float(v)
            elif isinstance(CFG[k], int) and not isinstance(CFG[k], bool) and isinstance(v, (int, float)):
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


@app.get("/api/qwen2_audio/status")
async def get_qwen2_audio_status():
    """Qwen2-Audio および Ollama (Gemma 4 e2b) モデルのロード状態・VRAM 使用状況を返す"""
    qwen_analyzer = get_qwen2_audio_analyzer(
        model_id=CFG.get("QWEN2_AUDIO_MODEL", DEFAULT_CONFIG["QWEN2_AUDIO_MODEL"])
    )
    ol_st = await asyncio.to_thread(
        get_ollama_model_status,
        CFG.get("OLLAMA_URL", DEFAULT_CONFIG["OLLAMA_URL"]),
        CFG.get("OLLAMA_MODEL", DEFAULT_CONFIG["OLLAMA_MODEL"]),
        3,
    )
    return {
        "status": "ok",
        "model_id": qwen_analyzer.model_id,
        "is_loaded": qwen_analyzer.is_loaded,
        "vram_used_mb": qwen_analyzer.get_vram_used_mb(),
        "ollama_model": CFG.get("OLLAMA_MODEL", DEFAULT_CONFIG["OLLAMA_MODEL"]),
        "ollama_loaded": bool(ol_st.get("is_loaded", False)),
        "ollama_vram_used_mb": float(ol_st.get("vram_used_mb", 0.0)),
        "gpu_vram_total_used_mb": get_gpu_vram_mb(),
        "auto_unload": bool(CFG.get("QWEN2_AUDIO_AUTO_UNLOAD", True)),
        "emotion_mode": CFG.get("emotion_mode", "standard"),
    }


@app.post("/api/qwen2_audio/unload")
async def unload_qwen2_audio_endpoint():
    """手動で Qwen2-Audio（および待機中の Ollama）モデルをアンロードし VRAM を解放する"""
    async with QWEN2_LOCK:
        info = await asyncio.to_thread(unload_qwen2_audio_if_loaded)
        ollama_info = await asyncio.to_thread(unload_ollama_if_loaded)
    qwen_analyzer = get_qwen2_audio_analyzer(
        model_id=CFG.get("QWEN2_AUDIO_MODEL", DEFAULT_CONFIG["QWEN2_AUDIO_MODEL"])
    )
    return {
        "status": "ok",
        "model_id": qwen_analyzer.model_id,
        "is_loaded": qwen_analyzer.is_loaded,
        "ollama_loaded": False,
        "ollama_unload": ollama_info,
        **info,
        "gpu_vram_total_used_mb": get_gpu_vram_mb(),
    }


@app.post("/api/models/standby")
async def standby_models_endpoint():
    """Step 1（シーン選択画面）の手動ボタン用：
    ComfyUI の待機 VRAM を解放した上で、Gemma 4 e2b (Ollama) と Qwen2-Audio (4bit) を事前に VRAM へロードする
    """
    t0 = time.time()
    qwen_analyzer = get_qwen2_audio_analyzer(
        model_id=CFG.get("QWEN2_AUDIO_MODEL", DEFAULT_CONFIG["QWEN2_AUDIO_MODEL"])
    )

    def _standby_blocking() -> dict:
        # 1) 前回の画像生成で残っている ComfyUI のモデルを VRAM から解放
        _try_comfy_free_for_qwen2()
        # 2) Gemma 4 e2b (Ollama) を VRAM にプリロード (keep_alive="15m")
        ol_res = preload_ollama_model(
            ollama_url=CFG.get("OLLAMA_URL", DEFAULT_CONFIG["OLLAMA_URL"]),
            ollama_model=CFG.get("OLLAMA_MODEL", DEFAULT_CONFIG["OLLAMA_MODEL"]),
            keep_alive="15m",
            timeout_sec=int(CFG.get("OLLAMA_WARMUP_TIMEOUT_SEC", 120)),
        )
        # 3) Qwen2-Audio (4bit) を VRAM にロード
        qwen_analyzer.ensure_loaded()
        ol_st = get_ollama_model_status(
            CFG.get("OLLAMA_URL", DEFAULT_CONFIG["OLLAMA_URL"]),
            CFG.get("OLLAMA_MODEL", DEFAULT_CONFIG["OLLAMA_MODEL"]),
            timeout_sec=3,
        )
        return {
            "ollama_res": ol_res,
            "ollama_status": ol_st,
        }

    async with QWEN2_LOCK:
        res_info = await asyncio.to_thread(_standby_blocking)

    ol_st = res_info["ollama_status"]
    ol_res = res_info["ollama_res"]
    elapsed_sec = round(time.time() - t0, 2)
    ollama_loaded = bool(ol_st.get("is_loaded", False) or ol_res.get("ok", False))
    log.info(
        "POST /api/models/standby 完了: elapsed=%.2fs, gemma_loaded=%s, qwen2_loaded=%s, total_vram=%.1fMB",
        elapsed_sec,
        ollama_loaded,
        qwen_analyzer.is_loaded,
        get_gpu_vram_mb(),
    )
    return {
        "status": "ok",
        "elapsed_sec": elapsed_sec,
        "ollama_model": CFG.get("OLLAMA_MODEL", DEFAULT_CONFIG["OLLAMA_MODEL"]),
        "ollama_loaded": ollama_loaded,
        "ollama_vram_used_mb": float(ol_st.get("vram_used_mb", 0.0)),
        "model_id": qwen_analyzer.model_id,
        "is_loaded": qwen_analyzer.is_loaded,
        "vram_used_mb": qwen_analyzer.get_vram_used_mb(),
        "gpu_vram_total_used_mb": get_gpu_vram_mb(),
    }


def _try_comfy_free_for_qwen2() -> None:
    """Qwen2-Audio 推論前に ComfyUI が保持している VRAM の解放を試みる（ComfyUI未起動時は警告ログのみで継続）"""
    try:
        comfy_free_and_wait_vram()
    except Exception as e:
        log.warning("Qwen2-Audio 推論前の ComfyUI /free スキップ（未起動または応答なし）: %s", e)


CALIBRATED_SAMPLES_DIR = BASE_DIR / "test_assets" / "calibrated_samples"
VALID_CALIBRATION_MODES = ("normal", "power", "whisper")


@app.get("/api/voice_emo_baseline")
async def get_voice_emo_baseline():
    analyzer = get_voice_emo_analyzer()
    b = dict(analyzer.baseline)
    anchors = b.get("anchors") if isinstance(b.get("anchors"), dict) else {"power": None, "whisper": None}
    b["anchors"] = {"power": anchors.get("power"), "whisper": anchors.get("whisper")}
    b["anchors_status"] = {
        "normal": bool(b.get("samples_count", 0)),
        "power": isinstance(anchors.get("power"), dict),
        "whisper": isinstance(anchors.get("whisper"), dict),
    }
    return {"baseline": b}


@app.post("/api/calibrate_voice_emo")
async def calibrate_voice_emo(
    audio_file: UploadFile = File(...),
    mode: str = Form("normal"),
):
    wav_path: Optional[Path] = None
    try:
        mode_key = (mode or "normal").strip().lower()
        if mode_key not in VALID_CALIBRATION_MODES:
            raise HTTPException(
                400,
                f"INVALID_CALIBRATION_MODE: mode は {VALID_CALIBRATION_MODES} のいずれかを指定してください (指定値: {mode})",
            )

        audio = await audio_file.read()
        validate_wav_16k_mono_pcm16(audio)
        TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        wav_path = TEMP_AUDIO_DIR / f"calib_{mode_key}_{uuid.uuid4().hex}.wav"
        wav_path.write_bytes(audio)

        # 実音声検証用として test_assets/calibrated_samples/latest_{mode}.wav にもコピー保存
        CALIBRATED_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        saved_sample_path = CALIBRATED_SAMPLES_DIR / f"latest_{mode_key}.wav"
        saved_sample_path.write_bytes(audio)

        analyzer = get_voice_emo_analyzer()

        def _run_calib():
            y, sr = analyzer._read_audio(wav_path)
            raw = analyzer.extract_raw_features(y, sr)
            updated = analyzer.calibrate_baseline([wav_path], mode=mode_key)
            return raw, updated

        raw_feat, new_baseline = await asyncio.to_thread(_run_calib)
        b = dict(new_baseline)
        anchors = b.get("anchors") if isinstance(b.get("anchors"), dict) else {"power": None, "whisper": None}
        b["anchors"] = {"power": anchors.get("power"), "whisper": anchors.get("whisper")}
        b["anchors_status"] = {
            "normal": bool(b.get("samples_count", 0)),
            "power": isinstance(anchors.get("power"), dict),
            "whisper": isinstance(anchors.get("whisper"), dict),
        }
        return {
            "status": "ok",
            "mode": mode_key,
            "saved_sample": str(saved_sample_path.relative_to(BASE_DIR)),
            "raw_features": {k: round(float(v), 4) for k, v in raw_feat.items()},
            "baseline": b,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("calibrate_voice_emo エラー")
        raise HTTPException(500, f"CALIBRATION_FAILED: {e}")
    finally:
        _safe_unlink(wav_path)


@app.post("/api/analyze_audio")
async def analyze_audio(
    audio_file: UploadFile = File(...),
    custom_system_prompt: Optional[str] = Form(None),
    custom_instruction: Optional[str] = Form(None),
):
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

        if emotion_mode == "qwen2_audio_hybrid":
            # Qwen2-Audio-7B-Instruct (4bit) + 物理音響変化ハイブリッド分析
            await asyncio.to_thread(_try_comfy_free_for_qwen2)
            qwen_analyzer = get_qwen2_audio_analyzer(
                model_id=CFG.get("QWEN2_AUDIO_MODEL", DEFAULT_CONFIG["QWEN2_AUDIO_MODEL"])
            )
            async with QWEN2_LOCK:
                res_emo = await asyncio.to_thread(
                    qwen_analyzer.analyze_hybrid,
                    wav_path,
                    recognized_text,
                    sense_emo,
                    custom_system_prompt,
                    custom_instruction,
                )
            top1 = res_emo["primary_emotion"]
            top2 = res_emo["secondary_emotion"]

            return {
                "emotion_mode": "qwen2_audio_hybrid",
                "recognized_text": recognized_text,
                "emotion": top1["name_ja"],
                "rms_db": rms_p90,
                "expression_state": top1["id"],
                "expression_prompt": res_emo["expression_prompt"],
                "expression_prompt_fd": res_emo["expression_prompt_fd"],
                "primary_emotion": top1,
                "secondary_emotion": top2,
                "raw_features": res_emo.get("raw_features", {}),
                "features_7": res_emo["features_7"],
                "emotions_12": res_emo["emotions_12"],
                "baseline_deltas": res_emo.get("baseline_deltas", {}),
                "qwen2_perception_en": res_emo.get("qwen2_perception_en", ""),
                "semantic_bridge": res_emo.get("semantic_bridge", {}),
                "semantic_bridge_en": res_emo.get("semantic_bridge_en", ""),
                "overall_impression_en": res_emo.get("overall_impression_en", ""),
                "acting_comment_ja": res_emo.get("acting_comment_ja", ""),
                "detected_nuance_short": res_emo.get("detected_nuance_short", ""),
                "vram_used_mb": res_emo.get("vram_used_mb", 0.0),
                "analysis_time_sec": res_emo["analysis_time_sec"],
            }
        elif emotion_mode == "detailed_12":
            # 12感情・音響物理特徴分析 (librosa/scipy/numpy・商用可) + SenseVoice 感情を Valence 補助に使用
            analyzer = get_voice_emo_analyzer()
            res_emo = await asyncio.to_thread(analyzer.analyze, wav_path, sense_emo)
            # 音声認識完了後に Step 2 から保持していた Gemma 4 e2b を VRAM から解放
            await asyncio.to_thread(unload_ollama_if_loaded)
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
                "raw_features": res_emo.get("raw_features", {}),
                "baseline_deltas": res_emo.get("baseline_deltas", {}),
                "features_7": res_emo["features_7"],
                "emotions_12": res_emo["emotions_12"],
                "analysis_time_sec": res_emo["analysis_time_sec"],
            }
        else:
            # 従来の SenseVoice 5段階判定
            category, expr, _ = determine_expression_category(
                sense_emo, rms_p90, CFG["BURNING_DB_THRESHOLD"]
            )
            # 音声認識完了後に Step 2 から保持していた Gemma 4 e2b を VRAM から解放
            await asyncio.to_thread(unload_ollama_if_loaded)
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
            current_emo_mode = CFG.get("emotion_mode", "standard")
            if current_emo_mode == "qwen2_audio_hybrid":
                async with SENSEVOICE_LOCK:
                    rms_val, _, _ = compute_rms_p90(wav_path)
                    sv_res = SENSEVOICE_MODEL.generate(input=str(wav_path), cache={}, language="auto", use_itn=True)
                    raw_sv = ""
                    if isinstance(sv_res, list) and sv_res:
                        raw_sv = sv_res[0].get("text", "")
                    elif isinstance(sv_res, dict):
                        raw_sv = sv_res.get("text", "")
                    rec_text = clean_sensevoice_text(raw_sv)
                    sense_emo = extract_emotion_tag(raw_sv)
                await asyncio.to_thread(_try_comfy_free_for_qwen2)
                qwen_analyzer = get_qwen2_audio_analyzer(
                    model_id=CFG.get("QWEN2_AUDIO_MODEL", DEFAULT_CONFIG["QWEN2_AUDIO_MODEL"])
                )
                async with QWEN2_LOCK:
                    res_emo = await asyncio.to_thread(
                        qwen_analyzer.analyze_hybrid,
                        wav_path,
                        rec_text,
                        sense_emo,
                    )
                expr = res_emo["expression_prompt"]
                expr_fd = res_emo["expression_prompt_fd"]
                category = res_emo["primary_emotion"]["id"]
                emo_val = res_emo["primary_emotion"]["name_ja"]
            elif current_emo_mode == "detailed_12":
                async with SENSEVOICE_LOCK:
                    _, rms_val, _, sense_emo = await asyncio.to_thread(_infer_emotion, wav_path)
                voice_analyzer = get_voice_emo_analyzer()
                res_emo = await asyncio.to_thread(voice_analyzer.analyze, wav_path, sense_emo)
                expr = res_emo["expression_prompt"]
                expr_fd = res_emo["expression_prompt_fd"]
                category = res_emo["primary_emotion"]["id"]
                emo_val = res_emo["primary_emotion"]["name_ja"]
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
        scene_neg = preset.get("scene_neg_prompt", "").strip()
        neg_base = ", ".join(p for p in [neg_bias, scene_neg, NEG_BASE] if p)
        pos_fd = f"{gender}, solo, close-up, face focus, {expr_fd}, detailed anime eyes, {QUALITY_TAGS}"

        # 5) ComfyUI 生成 (直前に Qwen2-Audio および未解放の Gemma 4 e2b を確実にアンロードして VRAM 11〜12GB を確保)
        async with QWEN2_LOCK:
            await asyncio.to_thread(unload_qwen2_audio_if_loaded)
            await asyncio.to_thread(unload_ollama_if_loaded)
        workflow = build_workflow(sess.image_path.name, pos_base, neg_base, pos_fd)
        async with COMFY_LOCK:
            png = await asyncio.to_thread(comfy_run, workflow)

        CARDS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CARDS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{session_id}_{scene_id}.png"
        out_path.write_bytes(png)
        script_to_return = final_script_text.strip() if (final_script_text and final_script_text.strip()) else preset["script_text"]
        log.info("カード保存: %s (emotion=%s/%s, rms=%.1fdB)", out_path.name, emo_val, category, rms_val)

        # 再生成用にプロンプトキャッシュを保持
        sess.prompt_cache = {
            "pos_base": pos_base,
            "neg_base": neg_base,
            "pos_fd": pos_fd,
            "scene_id": scene_id,
            "script_to_return": script_to_return,
            "category": category,
            "emo_val": emo_val,
            "rms_val": rms_val,
            "expr_fd": expr_fd,
        }

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
        # 注意: 再生成と履歴確認を可能にするため、ここでの即時セッション破棄は行わない。
        # 体験終了（リセット）時または TTL (15分) 到達時に discard_session が実行される。


@app.post("/api/regenerate_card")
async def regenerate_card(session_id: str = Form(...)):
    """同じ顔画像・設定のまま、新規ランダムSEEDでイラストを再生成する"""
    if not SESSION_ID_RE.match(session_id):
        raise HTTPException(400, "INVALID_SESSION_ID")
    sess = SESSIONS.get(session_id)
    if sess is None:
        raise HTTPException(404, "SESSION_NOT_FOUND: セッションが存在しないか有効期限が切れています")
    if not sess.prompt_cache:
        raise HTTPException(400, "NO_PROMPT_CACHE: 先に generate_scene を実行してください")
    if not sess.image_path.is_file():
        raise HTTPException(404, "FACE_IMAGE_NOT_FOUND: 顔画像が存在しません")

    cache = sess.prompt_cache
    pos_base = cache["pos_base"]
    neg_base = cache["neg_base"]
    pos_fd = cache.get("pos_fd", "")
    scene_id = cache.get("scene_id", "scene")
    category = cache.get("category", "BURNING")
    rms_val = cache.get("rms_val", 0.0)
    script_to_return = cache.get("script_to_return", "")
    expr_fd = cache.get("expr_fd", "")
    emo_val = cache.get("emo_val", "NEUTRAL")

    try:
        # 直前に Qwen2-Audio および未解放の Gemma 4 e2b を確実にアンロードして VRAM を確保
        async with QWEN2_LOCK:
            await asyncio.to_thread(unload_qwen2_audio_if_loaded)
            await asyncio.to_thread(unload_ollama_if_loaded)

        workflow = build_workflow(sess.image_path.name, pos_base, neg_base, pos_fd)
        async with COMFY_LOCK:
            png = await asyncio.to_thread(comfy_run, workflow)

        CARDS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CARDS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{session_id}_{scene_id}_regen.png"
        out_path.write_bytes(png)
        log.info("カード再生成保存: %s (emotion=%s/%s)", out_path.name, emo_val, category)

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
        log.exception("regenerate_card 予期せぬエラー")
        raise HTTPException(500, f"INTERNAL_ERROR: {e}")


@app.post("/api/discard_session")
async def discard_session_endpoint(session_id: str = Form(...)):
    """来場者の体験終了時にセッションと一時ファイルを明示的に破棄する"""
    if not SESSION_ID_RE.match(session_id):
        raise HTTPException(400, "INVALID_SESSION_ID")
    discard_session(session_id)
    log.info("明示的なセッション破棄完了: %s", session_id)
    return {"status": "ok", "session_id": session_id}


@app.post("/api/generate_custom")
async def generate_custom(
    face_image: Optional[UploadFile] = File(None),
    image_filename: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    pos_base: str = Form(...),
    neg_base: str = Form(...),
    pos_fd: str = Form(""),
    workflow_path: Optional[str] = Form(None),
    scene_id: Optional[str] = Form("custom"),
    script_text: Optional[str] = Form(""),
    auto_crop: bool = Form(True),
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
            if auto_crop:
                data = crop_head_and_shoulders(data, ext)
            sid = session_id or uuid.uuid4().hex[:12]
            COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)
            temp_target_path = COMFY_INPUT_DIR / f"{FILE_PREFIX}wb_{sid}{ext}"
            temp_target_path.write_bytes(data)
            target_img_filename = temp_target_path.name
        elif image_filename:
            if not SAFE_FILENAME_RE.match(image_filename) or ".." in image_filename or "/" in image_filename or "\\" in image_filename:
                raise HTTPException(400, "INVALID_IMAGE_FILENAME")
            target_img_filename = image_filename
            full_p = COMFY_INPUT_DIR / image_filename
            if not full_p.is_file():
                # CAPTURED_FACES_DIR または test_assets/faces から探して COMFY_INPUT_DIR にコピー
                src_captured = CAPTURED_FACES_DIR / image_filename
                src_test = BASE_DIR / "test_assets" / "faces" / image_filename
                if src_captured.is_file():
                    COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_captured, full_p)
                elif src_test.is_file():
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

        used_wf = workflow_path or CFG["WORKFLOW_PATH"]
        log.info(
            "generate_custom 開始: img=%s, wf=%s, pos_base_len=%d, neg_len=%d, fd_len=%d",
            target_img_filename,
            used_wf,
            len(pos_base),
            len(neg_base),
            len(pos_fd),
        )

        workflow = build_workflow(
            target_img_filename,
            pos_base,
            neg_base,
            pos_fd,
            workflow_filename=workflow_path,
        )
        # ComfyUI 実行直前に Qwen2-Audio および未解放の Gemma 4 e2b をアンロードして VRAM を確保
        async with QWEN2_LOCK:
            await asyncio.to_thread(unload_qwen2_audio_if_loaded)
            await asyncio.to_thread(unload_ollama_if_loaded)
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
            "workflow_path": workflow_path or CFG["WORKFLOW_PATH"],
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


