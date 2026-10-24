"""
StoryWeaver Live - Phase 3 Gate 3 自動検証スクリプト
verify_step3_api.py

前提: `uvicorn server:app --port 8000` と ComfyUI / Ollama が起動済み。

  ① 正常系 2 段階通信
  ② analyze 完了前の generate 同時呼び出し待機
  ③ 顔未検出 422 / 非 WAV 415
  ④ 一時ファイルのリークなし
  ⑤ 連続 2 回実行時の VRAM ピーク <= 14.5GB

使用例:
  python verify_step3_api.py --face test_assets/faces/koji-bose.jpg \
      --noface test_assets/faces/test_noface.jpg --audio test_assets/audio/01_shout.wav
"""

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

LOG_PATH = Path("verify_step3_api.log")
RESULTS: dict[str, tuple[bool, str]] = {}


def out(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def vram_mb() -> float:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return float(r.stdout.strip().split("\n")[0])
    except Exception:
        return -1.0


class VramSampler:
    def __init__(self, interval: float = 0.5):
        self.interval, self.peak, self._stop = interval, 0.0, threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            self.peak = max(self.peak, vram_mb())
            time.sleep(self.interval)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        self._t.join(timeout=2)


def analyze(base, face: Path, sid=None, timeout=120):
    data = {"session_id": sid} if sid else {}
    with open(face, "rb") as f:
        return requests.post(f"{base}/api/analyze_face", files={"face_image": (face.name, f, "image/jpeg")},
                             data=data, timeout=timeout)


def generate(base, audio: Path | None, sid, scene="scene_01", timeout=560, raw: bytes | None = None, name="a.wav"):
    content = raw if raw is not None else audio.read_bytes()
    return requests.post(f"{base}/api/generate_scene",
                         files={"audio_file": (name, content, "audio/wav")},
                         data={"scene_id": scene, "session_id": sid}, timeout=timeout)


def record(key, ok, detail):
    RESULTS[key] = (ok, detail)
    out(f"[{'PASS' if ok else 'FAIL'}] {key}: {detail}")


def snapshot(input_dir: Path, tmp_dir: Path):
    a = {p.name for p in input_dir.glob("sw_*")} if input_dir.is_dir() else set()
    b = {p.name for p in tmp_dir.glob("*")} if tmp_dir.is_dir() else set()
    return a, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--face", required=True)
    ap.add_argument("--noface", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--vram-limit-mb", type=float, default=14848.0)  # 14.5GB
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    face, noface, audio = Path(args.face), Path(args.noface), Path(args.audio)
    for p in (face, noface, audio):
        if not p.is_file():
            out(f"[ERROR] ファイルが存在しません: {p}")
            sys.exit(2)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parent
    input_dir = Path(cfg["COMFYUI_INPUT_DIR"])
    tmp_dir = Path(cfg["TEMP_AUDIO_DIR"])
    tmp_dir = tmp_dir if tmp_dir.is_absolute() else root / tmp_dir

    out("=" * 70)
    out(f"Gate 3 検証開始 base={base}")
    try:
        requests.get(f"{base}/api/health", timeout=5).raise_for_status()
    except Exception as e:
        out(f"[ERROR] サーバーに接続できません: {e}")
        sys.exit(2)

    before = snapshot(input_dir, tmp_dir)

    # ① 正常系
    try:
        sid = f"t1{uuid.uuid4().hex[:6]}"
        t0 = time.time()
        ra = analyze(base, face, sid)
        assert ra.status_code == 200, f"analyze HTTP {ra.status_code}: {ra.text[:200]}"
        rg = generate(base, audio, sid)
        assert rg.status_code == 200, f"generate HTTP {rg.status_code}: {rg.text[:200]}"
        j = rg.json()
        assert len(j.get("imageBase64", "")) > 1000, "imageBase64 が空/小さすぎる"
        for k in ("emotion", "rms_db", "script_text", "final_prompt"):
            assert k in j, f"レスポンスに {k} なし"
        record("①正常系2段階通信", True, f"{time.time() - t0:.1f}s emotion={j['emotion']} rms={j['rms_db']}")
    except Exception as e:
        record("①正常系2段階通信", False, str(e))

    # ② 競合安全
    try:
        sid = f"t2{uuid.uuid4().hex[:6]}"
        res = {}

        def do_analyze():
            res["a"] = analyze(base, face, sid)

        def do_generate():
            res["g"] = generate(base, audio, sid)

        ta = threading.Thread(target=do_analyze)
        ta.start()
        time.sleep(1.0)  # analyze 実行中に generate を投入
        t0 = time.time()
        tg = threading.Thread(target=do_generate)
        tg.start()
        still_running = ta.is_alive()
        ta.join()
        tg.join()
        assert still_running, "generate 投入時点で analyze が既に完了（待機を検証できず）"
        assert res["a"].status_code == 200, f"analyze HTTP {res['a'].status_code}"
        assert res["g"].status_code == 200, f"generate HTTP {res['g'].status_code}: {res['g'].text[:200]}"
        record("②競合安全", True, f"analyze 実行中に generate 投入 -> 待機後 200 ({time.time() - t0:.1f}s)")
    except Exception as e:
        record("②競合安全", False, str(e))

    # ③ 異常系
    try:
        r422 = analyze(base, noface, f"t3{uuid.uuid4().hex[:6]}")
        assert r422.status_code == 422, f"顔未検出で HTTP {r422.status_code}"
        assert r422.json().get("detail") == "FACE_NOT_DETECTED", f"detail={r422.json()}"
        # セッションが生成に進まないこと
        sid_nf = f"t3n{uuid.uuid4().hex[:5]}"
        analyze(base, noface, sid_nf)
        rg = generate(base, audio, sid_nf)
        assert rg.status_code != 200, "顔未検出セッションで generate が成功してしまった"

        sid_ok = f"t3b{uuid.uuid4().hex[:5]}"
        assert analyze(base, face, sid_ok).status_code == 200, "415 検証用 analyze 失敗"
        r415 = generate(base, None, sid_ok, raw=b"this is not a wav file" * 10, name="bad.wav")
        assert r415.status_code == 415, f"非 WAV で HTTP {r415.status_code}"
        # 後始末: 415 後もセッションは残るため正常 generate で使い切る
        generate(base, audio, sid_ok)
        record("③異常系(422/415)", True, f"422 FACE_NOT_DETECTED, noface generate={rg.status_code}, 非WAV 415")
    except Exception as e:
        record("③異常系(422/415)", False, str(e))

    # ⑤ 連続2回 VRAM（④より先に実施して全処理後にリーク確認）
    try:
        with VramSampler() as vs:
            s1 = f"t5a{uuid.uuid4().hex[:5]}"
            assert analyze(base, face, s1).status_code == 200, "1回目 analyze 失敗"
            assert generate(base, audio, s1).status_code == 200, "1回目 generate 失敗"
            # 1回目完了直後に 2回目 analyze
            s2 = f"t5b{uuid.uuid4().hex[:5]}"
            assert analyze(base, face, s2).status_code == 200, "2回目 analyze 失敗"
            assert generate(base, audio, s2).status_code == 200, "2回目 generate 失敗"
        peak = vs.peak
        ok = 0 < peak <= args.vram_limit_mb
        record("⑤連続2回VRAMピーク", ok, f"peak={peak:.0f}MB (limit {args.vram_limit_mb:.0f}MB)")
    except Exception as e:
        record("⑤連続2回VRAMピーク", False, str(e))

    # ④ リーク確認
    time.sleep(2.0)
    after = snapshot(input_dir, tmp_dir)
    leaked_img, leaked_aud = after[0] - before[0], after[1] - before[1]
    health = requests.get(f"{base}/api/health", timeout=5).json()
    ok = not leaked_img and not leaked_aud and health.get("sessions", -1) == 0
    record("④一時ファイルリークなし", ok,
           f"残留画像={sorted(leaked_img)} 残留音声={sorted(leaked_aud)} 残セッション={health.get('sessions')}")

    out("=" * 70)
    out("Gate 3 サマリー")
    for k, (ok, d) in RESULTS.items():
        out(f"  {'☑' if ok else '☐'} {k}: {d}")
    all_ok = len(RESULTS) == 5 and all(v[0] for v in RESULTS.values())
    out("総合: " + ("ALL PASS" if all_ok else "FAIL あり"))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
