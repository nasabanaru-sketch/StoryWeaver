"""
test_api_integration.py
FastAPI サーバー (server.py) の新設・拡張エンドポイント統合テスト
1. /api/voice_emo_baseline
2. /api/calibrate_voice_emo
3. /api/analyze_audio (standard モード)
4. /api/config (detailed_12 への切り替え)
5. /api/analyze_audio (detailed_12 モード: 文字起こし + 7基礎指標 + 12感情 + Base/FDプロンプト)
"""

import json
import sys
import time
from pathlib import Path

# UTF-8 出力
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests

BASE_URL = "http://127.0.0.1:8000"
TEST_AUDIO_DIR = Path(__file__).resolve().parent / "test_assets" / "synthetic_voice"
AUDIO_A = TEST_AUDIO_DIR / "voice_A_standard.wav"
AUDIO_B = TEST_AUDIO_DIR / "voice_B_breathy_slow.wav"


def run_tests():
    print("=================================================================")
    print("StoryWeaver Live: 12感情 API 統合テスト")
    print("=================================================================")

    # 1. ヘルスチェック
    print("\n[Test 1] サーバーヘルスチェック...")
    r = requests.get(f"{BASE_URL}/api/health", timeout=10)
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print("  -> OK:", r.json())

    # 2. GET /api/voice_emo_baseline
    print("\n[Test 2] GET /api/voice_emo_baseline...")
    r = requests.get(f"{BASE_URL}/api/voice_emo_baseline", timeout=5)
    assert r.status_code == 200, f"Get baseline failed: {r.status_code}"
    data = r.json()
    assert "baseline" in data
    print("  -> OK: baseline keys count =", len(data["baseline"]))

    # 3. POST /api/calibrate_voice_emo
    print("\n[Test 3] POST /api/calibrate_voice_emo (voice_A)...")
    with open(AUDIO_A, "rb") as f:
        files = {"audio_file": ("test_calib.wav", f, "audio/wav")}
        r = requests.post(f"{BASE_URL}/api/calibrate_voice_emo", files=files, timeout=15)
    assert r.status_code == 200, f"Calibrate failed: {r.status_code} - {r.text}"
    calib_res = r.json()
    assert calib_res.get("status") == "ok"
    assert "baseline" in calib_res
    print("  -> OK: calibrated samples =", calib_res["baseline"].get("samples_count"))

    # 4. POST /api/analyze_audio (standard モード)
    print("\n[Test 4] POST /api/analyze_audio (standard モード)...")
    # まず standard に確実に設定
    requests.put(f"{BASE_URL}/api/config", json={"emotion_mode": "standard"}, timeout=5)
    with open(AUDIO_A, "rb") as f:
        files = {"audio_file": ("test_std.wav", f, "audio/wav")}
        r = requests.post(f"{BASE_URL}/api/analyze_audio", files=files, timeout=15)
    assert r.status_code == 200, f"Analyze standard failed: {r.status_code} - {r.text}"
    res_std = r.json()
    assert res_std.get("emotion_mode") == "standard"
    assert "expression_state" in res_std
    assert "recognized_text" in res_std
    print("  -> OK (standard): expression_state =", res_std["expression_state"], ", text =", repr(res_std["recognized_text"]))

    # 5. モード切替: PUT /api/config -> detailed_12
    print("\n[Test 5] PUT /api/config (emotion_mode -> detailed_12)...")
    r = requests.put(f"{BASE_URL}/api/config", json={"emotion_mode": "detailed_12"}, timeout=5)
    assert r.status_code == 200, f"Config update failed: {r.status_code}"
    cfg = r.json()["config"]
    assert cfg.get("emotion_mode") == "detailed_12"
    print("  -> OK: emotion_mode is now", cfg.get("emotion_mode"))

    # 6. POST /api/analyze_audio (detailed_12 モード)
    print("\n[Test 6] POST /api/analyze_audio (detailed_12 モード: voice_B)...")
    with open(AUDIO_B, "rb") as f:
        files = {"audio_file": ("test_det.wav", f, "audio/wav")}
        r = requests.post(f"{BASE_URL}/api/analyze_audio", files=files, timeout=15)
    assert r.status_code == 200, f"Analyze detailed failed: {r.status_code} - {r.text}"
    res_det = r.json()
    assert res_det.get("emotion_mode") == "detailed_12"
    assert "primary_emotion" in res_det
    assert "secondary_emotion" in res_det
    assert "features_7" in res_det
    assert "emotions_12" in res_det
    assert "expression_prompt" in res_det
    assert "expression_prompt_fd" in res_det

    top1 = res_det["primary_emotion"]
    top2 = res_det["secondary_emotion"]
    print(f"  -> OK (detailed_12):")
    print(f"     Top-1 感情: {top1.get('icon')} {top1.get('name_ja')} ({top1.get('score')} pt)")
    print(f"     Top-2 感情: {top2.get('icon')} {top2.get('name_ja')} ({top2.get('score')} pt)")
    print(f"     Base プロンプト: {res_det['expression_prompt'][:70]}...")
    print(f"     FD   プロンプト: {res_det['expression_prompt_fd'][:70]}...")
    print(f"     解析時間: {res_det.get('analysis_time_sec')}秒")

    # 7. 元の standard モードに復帰
    print("\n[Test 7] PUT /api/config (emotion_mode -> standard に戻す)...")
    requests.put(f"{BASE_URL}/api/config", json={"emotion_mode": "standard"}, timeout=5)
    print("  -> OK: restored to standard")

    print("\n=================================================================")
    print("API 統合テストがすべて正常に合格しました！ (ALL API TESTS PASSED)")
    print("=================================================================")


if __name__ == "__main__":
    run_tests()
